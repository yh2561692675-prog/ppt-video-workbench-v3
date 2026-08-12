"""Low-overhead, dependency-free resource sampler for production acceptance.

The sampler intentionally records raw counters as well as calculated rates.  A
later budget policy can therefore choose its own aggregation without losing
evidence.  It does not require psutil: Linux reads ``/proc`` and Windows uses
documented Toolhelp/Process APIs, with inaccessible process metrics represented
as ``null`` rather than guessed values.
"""

from __future__ import annotations

import ctypes
import json
import os
import platform
import shutil
import threading
import time
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Protocol, cast
from uuid import uuid4

_MIN_INTERVAL_SECONDS: Final = 1.0
_MAX_INTERVAL_SECONDS: Final = 5.0
_KIB: Final = 1024


def _utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class ProcessObservation:
    """A single process observation with a PID-reuse-safe instance key."""

    pid: int
    parent_pid: int | None
    executable: str
    instance_start_token: str
    cpu_time_seconds: float | None
    rss_bytes: int | None
    handle_count: int | None
    thread_count: int | None
    read_bytes: int | None
    write_bytes: int | None
    gpu_memory_bytes: int | None = None

    @property
    def instance_key(self) -> str:
        return f"{self.pid}:{self.instance_start_token}"


class ProcessProvider(Protocol):
    """Read an instantaneous process table without exposing OS details."""

    def snapshot(self) -> Iterable[ProcessObservation]: ...


class SystemProcessProvider:
    """Native process provider for the host operating system."""

    def snapshot(self) -> Iterable[ProcessObservation]:
        if os.name == "nt":
            return _windows_snapshot()
        return _procfs_snapshot()


@dataclass(slots=True)
class _ObservedInstance:
    pid: int
    executable: str
    roles: set[str]
    first_seen: str
    last_seen: str
    sample_count: int = 0
    peak_rss_bytes: int | None = None
    peak_cpu_percent: float | None = None
    peak_handles: int | None = None
    peak_threads: int | None = None
    peak_read_bytes: int | None = None
    peak_write_bytes: int | None = None
    peak_gpu_memory_bytes: int | None = None

    def observe(
        self,
        *,
        timestamp: str,
        roles: set[str],
        observation: ProcessObservation,
        cpu_percent: float | None,
    ) -> None:
        self.last_seen = timestamp
        self.roles.update(roles)
        self.sample_count += 1
        self.peak_rss_bytes = _maximum_int(self.peak_rss_bytes, observation.rss_bytes)
        self.peak_cpu_percent = _maximum_float(self.peak_cpu_percent, cpu_percent)
        self.peak_handles = _maximum_int(self.peak_handles, observation.handle_count)
        self.peak_threads = _maximum_int(self.peak_threads, observation.thread_count)
        self.peak_read_bytes = _maximum_int(self.peak_read_bytes, observation.read_bytes)
        self.peak_write_bytes = _maximum_int(self.peak_write_bytes, observation.write_bytes)
        self.peak_gpu_memory_bytes = _maximum_int(
            self.peak_gpu_memory_bytes, observation.gpu_memory_bytes
        )


def _maximum_int(current: int | None, incoming: int | None) -> int | None:
    if incoming is None:
        return current
    if current is None:
        return incoming
    return max(current, incoming)


def _maximum_float(current: float | None, incoming: float | None) -> float | None:
    if incoming is None:
        return current
    if current is None:
        return incoming
    return max(current, incoming)


def _component_role(executable: str) -> str:
    name = Path(executable).name.lower()
    if "ffmpeg" in name or "ffprobe" in name:
        return "ffmpeg"
    if name in {"node", "node.exe"}:
        return "node"
    if name in {"soffice", "soffice.bin", "soffice.exe", "libreoffice"}:
        return "office"
    if name in {"python", "python.exe", "uvicorn", "uvicorn.exe"}:
        return "python"
    return "other"


class PerformanceSampler:
    """Write a PID-reuse-safe JSONL resource stream and a peak summary.

    ``roots`` names the observed launcher/API/worker processes. Descendants are
    discovered on every sample, so a replacement Node or FFmpeg child remains
    correlated with the acceptance run. A repeated PID with another start token
    becomes a new process instance rather than silently extending old metrics.
    """

    def __init__(
        self,
        output_dir: Path,
        roots: Mapping[str, int],
        *,
        temporary_root: Path,
        interval_seconds: float = _MIN_INTERVAL_SECONDS,
        provider: ProcessProvider | None = None,
        session_id: str | None = None,
    ) -> None:
        if not roots:
            raise ValueError("at least one named root process is required")
        if not _MIN_INTERVAL_SECONDS <= interval_seconds <= _MAX_INTERVAL_SECONDS:
            raise ValueError("interval_seconds must be between 1 and 5")
        if any(not name.strip() or pid <= 0 for name, pid in roots.items()):
            raise ValueError("root names must be non-empty and PIDs must be positive")

        self.output_dir = output_dir.resolve()
        self.roots = dict(roots)
        self.temporary_root = temporary_root.resolve()
        self.interval_seconds = interval_seconds
        self.provider = provider or SystemProcessProvider()
        self.session_id = session_id or (
            f"performance-{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:8]}"
        )
        self.events_path = self.output_dir / f"{self.session_id}.jsonl"
        self.summary_path = self.output_dir / f"{self.session_id}-summary.json"
        self._started_at: str | None = None
        self._stopped_at: str | None = None
        self._events: list[dict[str, object]] = []
        self._active_stages: set[str] = set()
        self._instances: dict[str, _ObservedInstance] = {}
        self._previous_cpu: dict[str, tuple[float, float]] = {}
        self._missing_roots: dict[str, int] = {}
        self._temporary_peaks: dict[str, int | None] = {
            "max_used_bytes": None,
            "max_file_bytes": None,
            "max_file_count": None,
            "min_free_bytes": None,
        }
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Start periodic sampling and write a non-overwriteable session header."""

        with self._lock:
            if self._started_at is not None:
                raise RuntimeError("performance sampler is already running")
            self.output_dir.mkdir(parents=True, exist_ok=True)
            self._write_new_event(
                self.events_path,
                {
                    "type": "session_started",
                    "timestamp": _utc_now(),
                    "session_id": self.session_id,
                    "roots": self.roots,
                    "interval_seconds": self.interval_seconds,
                    "host": _host_profile(),
                    "temporary_root": str(self.temporary_root),
                },
            )
            self._started_at = _utc_now()
        self.sample_once()
        self._thread = threading.Thread(
            target=self._sample_loop,
            name=f"workbench-performance-{self.session_id}",
            daemon=True,
        )
        self._thread.start()

    def record_stage(self, stage: str, event: str) -> None:
        """Record a phase boundary that can be joined with sampling peaks."""

        if not stage.strip():
            raise ValueError("stage must not be empty")
        if event not in {"started", "finished", "checkpoint"}:
            raise ValueError("event must be started, finished or checkpoint")
        with self._lock:
            self._require_started()
            if event == "started":
                self._active_stages.add(stage)
            elif event == "finished":
                self._active_stages.discard(stage)
            self._append_event(
                {
                    "type": "stage",
                    "timestamp": _utc_now(),
                    "stage": stage,
                    "event": event,
                    "active_stages": sorted(self._active_stages),
                }
            )

    def sample_once(self) -> dict[str, object]:
        """Capture one process-tree and temporary-space sample synchronously."""

        with self._lock:
            self._require_started()
            timestamp = _utc_now()
            monotonic_now = time.monotonic()
            observed = list(self.provider.snapshot())
            tree_roles = _tree_roles(observed, self.roots)
            observed_pids = {item.pid for item in observed}
            missing_roots = {
                role: pid for role, pid in self.roots.items() if pid not in observed_pids
            }
            self._missing_roots.update(missing_roots)
            serialized: list[dict[str, object]] = []
            for item in observed:
                roles = tree_roles.get(item.pid)
                if roles is None:
                    continue
                cpu_percent = self._cpu_percent(item, monotonic_now)
                self._record_instance(timestamp, item, roles, cpu_percent)
                serialized.append(
                    {
                        "instance_key": item.instance_key,
                        "pid": item.pid,
                        "parent_pid": item.parent_pid,
                        "executable": item.executable,
                        "roles": sorted(roles),
                        "cpu_time_seconds": item.cpu_time_seconds,
                        "cpu_percent": cpu_percent,
                        "rss_bytes": item.rss_bytes,
                        "handle_count": item.handle_count,
                        "thread_count": item.thread_count,
                        "read_bytes": item.read_bytes,
                        "write_bytes": item.write_bytes,
                        "gpu_memory_bytes": item.gpu_memory_bytes,
                    }
                )
            temporary = _temporary_usage(self.temporary_root)
            self._observe_temporary(temporary)
            event: dict[str, object] = {
                "type": "sample",
                "timestamp": timestamp,
                "active_stages": sorted(self._active_stages),
                "processes": serialized,
                "missing_roots": missing_roots,
                "temporary": temporary,
            }
            self._append_event(event)
            return event

    def stop(self) -> Path:
        """Stop sampling, flush a final sample and atomically publish the summary."""

        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=self.interval_seconds + 1.0)
        with self._lock:
            self._require_started()
            if self._stopped_at is not None:
                return self.summary_path
        self.sample_once()
        with self._lock:
            self._stopped_at = _utc_now()
            self._append_event({"type": "session_finished", "timestamp": self._stopped_at})
            summary = self._summary()
            self._write_new_json(self.summary_path, summary)
            return self.summary_path

    def _sample_loop(self) -> None:
        while not self._stop_event.wait(self.interval_seconds):
            try:
                self.sample_once()
            except (OSError, RuntimeError, ValueError) as error:
                with self._lock:
                    if self._started_at is not None and self._stopped_at is None:
                        self._append_event(
                            {
                                "type": "sampler_error",
                                "timestamp": _utc_now(),
                                "error_type": type(error).__name__,
                                "message": str(error),
                            }
                        )

    def _cpu_percent(self, item: ProcessObservation, monotonic_now: float) -> float | None:
        if item.cpu_time_seconds is None:
            return None
        previous = self._previous_cpu.get(item.instance_key)
        self._previous_cpu[item.instance_key] = (monotonic_now, item.cpu_time_seconds)
        if previous is None:
            return None
        elapsed = monotonic_now - previous[0]
        if elapsed <= 0:
            return None
        return round(max(0.0, item.cpu_time_seconds - previous[1]) / elapsed * 100.0, 3)

    def _record_instance(
        self,
        timestamp: str,
        item: ProcessObservation,
        roles: set[str],
        cpu_percent: float | None,
    ) -> None:
        instance = self._instances.get(item.instance_key)
        if instance is None:
            instance = _ObservedInstance(
                pid=item.pid,
                executable=item.executable,
                roles=set(roles),
                first_seen=timestamp,
                last_seen=timestamp,
            )
            self._instances[item.instance_key] = instance
            self._append_event(
                {
                    "type": "process_observed",
                    "timestamp": timestamp,
                    "instance_key": item.instance_key,
                    "pid": item.pid,
                    "executable": item.executable,
                    "roles": sorted(roles),
                }
            )
        instance.observe(
            timestamp=timestamp,
            roles=roles,
            observation=item,
            cpu_percent=cpu_percent,
        )

    def _observe_temporary(self, temporary: dict[str, int | None]) -> None:
        self._temporary_peaks["max_used_bytes"] = _maximum_int(
            self._temporary_peaks["max_used_bytes"], temporary["used_bytes"]
        )
        self._temporary_peaks["max_file_bytes"] = _maximum_int(
            self._temporary_peaks["max_file_bytes"], temporary["file_bytes"]
        )
        self._temporary_peaks["max_file_count"] = _maximum_int(
            self._temporary_peaks["max_file_count"], temporary["file_count"]
        )
        free = temporary["free_bytes"]
        current = self._temporary_peaks["min_free_bytes"]
        if free is not None and (current is None or free < current):
            self._temporary_peaks["min_free_bytes"] = free

    def _summary(self) -> dict[str, object]:
        component_peaks: dict[str, dict[str, int | float | None]] = {}
        for instance in self._instances.values():
            for role in instance.roles:
                peak = component_peaks.setdefault(
                    role,
                    {
                        "rss_bytes": None,
                        "cpu_percent": None,
                        "handle_count": None,
                        "thread_count": None,
                        "read_bytes": None,
                        "write_bytes": None,
                        "gpu_memory_bytes": None,
                    },
                )
                peak["rss_bytes"] = _maximum_int(
                    cast(int | None, peak["rss_bytes"]), instance.peak_rss_bytes
                )
                peak["cpu_percent"] = _maximum_float(
                    cast(float | None, peak["cpu_percent"]), instance.peak_cpu_percent
                )
                peak["handle_count"] = _maximum_int(
                    cast(int | None, peak["handle_count"]), instance.peak_handles
                )
                peak["thread_count"] = _maximum_int(
                    cast(int | None, peak["thread_count"]), instance.peak_threads
                )
                peak["read_bytes"] = _maximum_int(
                    cast(int | None, peak["read_bytes"]), instance.peak_read_bytes
                )
                peak["write_bytes"] = _maximum_int(
                    cast(int | None, peak["write_bytes"]), instance.peak_write_bytes
                )
                peak["gpu_memory_bytes"] = _maximum_int(
                    cast(int | None, peak["gpu_memory_bytes"]),
                    instance.peak_gpu_memory_bytes,
                )
        stages = [event for event in self._events if event["type"] == "stage"]
        return {
            "schema_version": "1.0",
            "session_id": self.session_id,
            "started_at": self._started_at,
            "finished_at": self._stopped_at,
            "roots": self.roots,
            "roots_not_observed": self._missing_roots,
            "events_path": self.events_path.name,
            "sample_count": sum(1 for event in self._events if event["type"] == "sample"),
            "stage_events": stages,
            "temporary_space_peaks": self._temporary_peaks,
            "component_peaks": component_peaks,
            "process_instances": {
                key: {
                    **asdict(instance),
                    "roles": sorted(instance.roles),
                }
                for key, instance in sorted(self._instances.items())
            },
        }

    def _require_started(self) -> None:
        if self._started_at is None:
            raise RuntimeError("performance sampler has not started")
        if self._stopped_at is not None:
            raise RuntimeError("performance sampler is already stopped")

    def _append_event(self, event: dict[str, object]) -> None:
        self._events.append(event)
        with self.events_path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    @staticmethod
    def _write_new_json(path: Path, value: object) -> None:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)

    @staticmethod
    def _write_new_event(path: Path, value: object) -> None:
        serialized = json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n"
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(serialized)


def _tree_roles(
    observed: list[ProcessObservation], roots: Mapping[str, int]
) -> dict[int, set[str]]:
    by_parent: dict[int, list[ProcessObservation]] = defaultdict(list)
    by_pid = {item.pid: item for item in observed}
    for item in observed:
        if item.parent_pid is not None:
            by_parent[item.parent_pid].append(item)

    result: dict[int, set[str]] = {}
    pending: list[tuple[int, str]] = [
        (pid, role) for role, pid in roots.items() if pid in by_pid
    ]
    while pending:
        pid, inherited_role = pending.pop()
        process = by_pid.get(pid)
        if process is None:
            continue
        roles = result.setdefault(pid, set())
        before = len(roles)
        roles.add(inherited_role)
        roles.add(_component_role(process.executable))
        if len(roles) == before:
            continue
        for child in by_parent.get(pid, []):
            pending.append((child.pid, inherited_role))
    return result


def _temporary_usage(root: Path) -> dict[str, int | None]:
    target = root if root.exists() else root.parent
    try:
        disk = shutil.disk_usage(target)
    except OSError:
        return {
            "total_bytes": None,
            "used_bytes": None,
            "free_bytes": None,
            "file_bytes": None,
            "file_count": None,
        }
    file_bytes: int | None = 0
    file_count: int | None = 0
    if root.is_dir():
        try:
            for path in root.rglob("*"):
                if path.is_file() and file_count is not None and file_bytes is not None:
                    file_count += 1
                    file_bytes += path.stat().st_size
        except OSError:
            file_bytes = None
            file_count = None
    return {
        "total_bytes": disk.total,
        "used_bytes": disk.used,
        "free_bytes": disk.free,
        "file_bytes": file_bytes,
        "file_count": file_count,
    }


def _host_profile() -> dict[str, object]:
    return {
        "platform": platform.platform(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
        "gpu_memory_bytes": None,
        "gpu_probe": "not_available_without_a_vendor_specific_runtime",
    }


def _procfs_snapshot() -> list[ProcessObservation]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    sysconf = cast(Any, os).sysconf
    clock_ticks = int(sysconf("SC_CLK_TCK"))
    observations: list[ProcessObservation] = []
    for directory in proc.iterdir():
        if not directory.name.isdecimal():
            continue
        try:
            observations.append(_read_proc_process(directory, clock_ticks))
        except (OSError, ValueError, IndexError):
            continue
    return observations


def _read_proc_process(directory: Path, clock_ticks: int) -> ProcessObservation:
    stat = (directory / "stat").read_text(encoding="utf-8")
    closing = stat.rfind(")")
    if closing < 0:
        raise ValueError("invalid proc stat")
    fields = stat[closing + 2 :].split()
    parent_pid = int(fields[1])
    cpu_time_seconds = (int(fields[11]) + int(fields[12])) / clock_ticks
    start_token = fields[19]
    status = _read_proc_key_values(directory / "status")
    io = _read_proc_key_values(directory / "io")
    command = (directory / "comm").read_text(encoding="utf-8").strip()
    return ProcessObservation(
        pid=int(directory.name),
        parent_pid=parent_pid or None,
        executable=command,
        instance_start_token=start_token,
        cpu_time_seconds=cpu_time_seconds,
        rss_bytes=_proc_int(status.get("VmRSS"), multiplier=_KIB),
        handle_count=_count_directory(directory / "fd"),
        thread_count=_proc_int(status.get("Threads")),
        read_bytes=_proc_int(io.get("read_bytes")),
        write_bytes=_proc_int(io.get("write_bytes")),
    )


def _read_proc_key_values(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        key, separator, value = line.partition(":")
        if separator:
            values[key] = value.strip()
    return values


def _proc_int(value: str | None, *, multiplier: int = 1) -> int | None:
    if value is None:
        return None
    try:
        return int(value.split()[0]) * multiplier
    except ValueError:
        return None


def _count_directory(path: Path) -> int | None:
    try:
        return sum(1 for _ in path.iterdir())
    except OSError:
        return None


def _windows_snapshot() -> list[ProcessObservation]:
    """Collect Windows metrics using stable documented kernel APIs only."""

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    process_entries = _windows_process_entries(kernel32)
    thread_counts = _windows_thread_counts(kernel32)
    observations: list[ProcessObservation] = []
    for pid, parent_pid, executable in process_entries:
        metrics = _windows_metrics(kernel32, pid)
        observations.append(
            ProcessObservation(
                pid=pid,
                parent_pid=parent_pid or None,
                executable=executable,
                instance_start_token=metrics[0],
                cpu_time_seconds=metrics[1],
                rss_bytes=metrics[2],
                handle_count=metrics[3],
                thread_count=thread_counts.get(pid),
                read_bytes=metrics[4],
                write_bytes=metrics[5],
            )
        )
    return observations


class _ProcessEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("cntUsage", ctypes.c_ulong),
        ("th32ProcessID", ctypes.c_ulong),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", ctypes.c_ulong),
        ("cntThreads", ctypes.c_ulong),
        ("th32ParentProcessID", ctypes.c_ulong),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


class _ThreadEntry32(ctypes.Structure):
    _fields_ = [
        ("dwSize", ctypes.c_ulong),
        ("cntUsage", ctypes.c_ulong),
        ("th32ThreadID", ctypes.c_ulong),
        ("th32OwnerProcessID", ctypes.c_ulong),
        ("tpBasePri", ctypes.c_long),
        ("tpDeltaPri", ctypes.c_long),
        ("dwFlags", ctypes.c_ulong),
    ]


class _FileTime(ctypes.Structure):
    _fields_ = [("dwLowDateTime", ctypes.c_ulong), ("dwHighDateTime", ctypes.c_ulong)]


class _ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
    ]


class _IoCounters(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


def _windows_process_entries(kernel32: Any) -> list[tuple[int, int, str]]:
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return []
    result: list[tuple[int, int, str]] = []
    try:
        entry = _ProcessEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Process32FirstW(snapshot, ctypes.byref(entry)):
            return result
        while True:
            result.append(
                (int(entry.th32ProcessID), int(entry.th32ParentProcessID), entry.szExeFile)
            )
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return result


def _windows_thread_counts(kernel32: Any) -> dict[int, int]:
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000004, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        return {}
    result: dict[int, int] = defaultdict(int)
    try:
        entry = _ThreadEntry32()
        entry.dwSize = ctypes.sizeof(entry)
        if not kernel32.Thread32First(snapshot, ctypes.byref(entry)):
            return dict(result)
        while True:
            result[int(entry.th32OwnerProcessID)] += 1
            entry.dwSize = ctypes.sizeof(entry)
            if not kernel32.Thread32Next(snapshot, ctypes.byref(entry)):
                break
    finally:
        kernel32.CloseHandle(snapshot)
    return dict(result)


def _windows_metrics(
    kernel32: Any, pid: int
) -> tuple[str, float | None, int | None, int | None, int | None, int | None]:
    handle = kernel32.OpenProcess(0x1000 | 0x0400, False, pid)
    if not handle:
        return (f"unavailable-{pid}", None, None, None, None, None)
    try:
        created = _FileTime()
        exited = _FileTime()
        kernel = _FileTime()
        user = _FileTime()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(created),
            ctypes.byref(exited),
            ctypes.byref(kernel),
            ctypes.byref(user),
        ):
            return (f"unavailable-{pid}", None, None, None, None, None)
        created_raw = (int(created.dwHighDateTime) << 32) | int(created.dwLowDateTime)
        kernel_raw = (int(kernel.dwHighDateTime) << 32) | int(kernel.dwLowDateTime)
        user_raw = (int(user.dwHighDateTime) << 32) | int(user.dwLowDateTime)
        cpu_raw = kernel_raw + user_raw
        memory = _ProcessMemoryCounters()
        memory.cb = ctypes.sizeof(memory)
        psapi = ctypes.WinDLL("psapi")
        has_memory = psapi.GetProcessMemoryInfo(handle, ctypes.byref(memory), memory.cb)
        rss = int(memory.WorkingSetSize) if has_memory else None
        handles = ctypes.c_ulong()
        has_handle_count = kernel32.GetProcessHandleCount(handle, ctypes.byref(handles))
        handle_count = int(handles.value) if has_handle_count else None
        io = _IoCounters()
        read = write = None
        if kernel32.GetProcessIoCounters(handle, ctypes.byref(io)):
            read, write = int(io.ReadTransferCount), int(io.WriteTransferCount)
        return (str(created_raw), cpu_raw / 10_000_000, rss, handle_count, read, write)
    finally:
        kernel32.CloseHandle(handle)
