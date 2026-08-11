"""No-console desktop supervisor for the packaged loopback Workbench API."""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from contextlib import suppress
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from workbench.desktop.release_slots import ReleaseSlotError, ReleaseSlots

STARTUP_TIMEOUT_SECONDS = 40
STARTUP_ATTEMPTS = 2
MUTEX_ALREADY_EXISTS = 183
_LOCAL_MUTEX_HELD = False


@dataclass(frozen=True)
class InstanceState:
    version: str
    launcher_pid: int
    api_pid: int
    base_url: str
    health_url: str


class LauncherMutex:
    """Serialize start/stop operations, including repeated shortcut clicks."""

    def __init__(self, app_root: Path) -> None:
        self.name = f"Local\\PPTVideoWorkbench-{abs(hash(str(app_root.resolve())))}"
        self.handle: Any | None = None

    def __enter__(self) -> LauncherMutex:
        global _LOCAL_MUTEX_HELD
        if os.name != "nt":
            if _LOCAL_MUTEX_HELD:
                raise ReleaseSlotError("launcher_start_in_progress")
            _LOCAL_MUTEX_HELD = True
            return self
        import ctypes

        self.handle = ctypes.windll.kernel32.CreateMutexW(None, False, self.name)
        if not self.handle:
            raise ReleaseSlotError("launcher_mutex_create_failed")
        if ctypes.windll.kernel32.GetLastError() == MUTEX_ALREADY_EXISTS:
            ctypes.windll.kernel32.CloseHandle(self.handle)
            self.handle = None
            raise ReleaseSlotError("launcher_start_in_progress")
        return self

    def __exit__(self, *_: object) -> None:
        global _LOCAL_MUTEX_HELD
        if self.handle is not None:
            import ctypes

            ctypes.windll.kernel32.ReleaseMutex(self.handle)
            ctypes.windll.kernel32.CloseHandle(self.handle)
        _LOCAL_MUTEX_HELD = False


def _default_app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent.parent
    return Path.cwd() / "app"


def _free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def _get_json(url: str, timeout: float = 2.0) -> dict[str, object] | None:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            if response.status != 200:
                return None
            loaded = json.loads(response.read().decode("utf-8"))
            return loaded if isinstance(loaded, dict) else None
    except (OSError, TimeoutError, ValueError):
        return None


def _state_path(slots: ReleaseSlots) -> Path:
    return slots.state_root / "instance.json"


def _read_state(slots: ReleaseSlots) -> InstanceState | None:
    try:
        raw = json.loads(_state_path(slots).read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        return InstanceState(
            version=str(raw["version"]),
            launcher_pid=int(raw["launcher_pid"]),
            api_pid=int(raw["api_pid"]),
            base_url=str(raw["base_url"]),
            health_url=str(raw["health_url"]),
        )
    except (KeyError, OSError, TypeError, ValueError):
        return None


def _write_state(slots: ReleaseSlots, state: InstanceState) -> None:
    path = _state_path(slots)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".partial")
    temporary.write_text(json.dumps(asdict(state), indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _remove_state(slots: ReleaseSlots) -> None:
    _state_path(slots).unlink(missing_ok=True)


def _healthy(state: InstanceState) -> bool:
    payload = _get_json(state.health_url)
    return payload is not None and payload.get("status") == "ok"


def _process_flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


def _show_failure(message: str) -> None:
    if os.name != "nt":
        return
    with suppress(Exception):
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, "PPT Video Workbench", 0x10)


def _terminate(process: subprocess.Popen[bytes]) -> None:
    with suppress(ProcessLookupError):
        process.terminate()
    with suppress(subprocess.TimeoutExpired):
        process.wait(timeout=5)


def _start_api(slots: ReleaseSlots) -> tuple[InstanceState, subprocess.Popen[bytes]]:
    slot = slots.read_active()
    release_root = slots.resolve(slot)
    executable = release_root / "api" / "workbench.exe"
    web_root = release_root / "web"
    runtime_root = release_root / "runtime"
    if not executable.is_file() or not (web_root / "index.html").is_file():
        raise ReleaseSlotError("launcher_active_release_invalid")
    port = _free_local_port()
    state_root = slots.state_root
    workspace_root = Path(
        os.environ.get("WORKBENCH_WORKSPACE", str(slots.app_root.parent / "workspace-data"))
    ).resolve()
    logs_root = state_root / "logs"
    logs_root.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment.update(
        {
            "WORKBENCH_WORKSPACE": str(workspace_root),
            "WORKBENCH_WEB_ROOT": str(web_root),
            "WORKBENCH_RUNTIME_ROOT": str(runtime_root),
            "WORKBENCH_LOG_ROOT": str(logs_root),
        }
    )
    stdout = (logs_root / "api.stdout.log").open("ab")
    stderr = (logs_root / "api.stderr.log").open("ab")
    process = subprocess.Popen(
        [str(executable), "serve", "--host", "127.0.0.1", "--port", str(port)],
        cwd=executable.parent,
        env=environment,
        stdout=stdout,
        stderr=stderr,
        creationflags=_process_flags(),
    )
    base_url = f"http://127.0.0.1:{port}"
    return (
        InstanceState(
            version=slot.version,
            launcher_pid=os.getpid(),
            api_pid=process.pid,
            base_url=base_url,
            health_url=f"{base_url}/api/health",
        ),
        process,
    )


def _wait_for_health(state: InstanceState, process: subprocess.Popen[bytes]) -> bool:
    deadline = time.monotonic() + STARTUP_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False
        if _healthy(state):
            return True
        time.sleep(0.25)
    return False


def activate(app_root: Path, version: str, release_root: Path) -> int:
    slots = ReleaseSlots(app_root)
    slot = slots.slot_for_release(release_root, version)
    slots.activate(slot)
    return 0


def _start_healthy(slots: ReleaseSlots) -> tuple[InstanceState, subprocess.Popen[bytes]]:
    last_error = "launcher_health_timeout"
    for _ in range(STARTUP_ATTEMPTS):
        state, process = _start_api(slots)
        if _wait_for_health(state, process):
            return state, process
        _terminate(process)
    try:
        slots.rollback()
    except ReleaseSlotError:
        raise ReleaseSlotError(last_error) from None
    state, process = _start_api(slots)
    if _wait_for_health(state, process):
        return state, process
    _terminate(process)
    raise ReleaseSlotError("launcher_previous_release_unhealthy")


def start(app_root: Path, *, open_browser: bool = True) -> int:
    slots = ReleaseSlots(app_root)
    try:
        with LauncherMutex(slots.app_root):
            state = _read_state(slots)
            if state is not None and _healthy(state):
                if open_browser:
                    webbrowser.open(state.base_url)
                return 0
            _remove_state(slots)
            state, process = _start_healthy(slots)
            _write_state(slots, state)
            if open_browser:
                webbrowser.open(state.base_url)
            try:
                return process.wait()
            finally:
                _remove_state(slots)
    except ReleaseSlotError as error:
        if str(error) != "launcher_start_in_progress":
            _show_failure(f"启动失败：{error}")
        raise


def status(app_root: Path) -> int:
    state = _read_state(ReleaseSlots(app_root))
    if state is None or not _healthy(state):
        return 1
    print(json.dumps(asdict(state)))
    return 0


def shutdown(app_root: Path, *, wait: bool = False) -> int:
    slots = ReleaseSlots(app_root)
    state = _read_state(slots)
    if state is None:
        return 0
    _terminate_process(state.api_pid, wait=wait)
    if state.launcher_pid != os.getpid():
        _terminate_process(state.launcher_pid, wait=wait)
    _remove_state(slots)
    return 0


def _terminate_process(pid: int, *, wait: bool) -> None:
    """Stop the packaged API and optionally wait until its process is gone."""
    if os.name == "nt":
        _terminate_windows_process(pid, wait=wait)
        return

    with suppress(ProcessLookupError):
        os.kill(pid, 15)
    if not wait:
        return
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        with suppress(ProcessLookupError):
            os.kill(pid, 0)
            time.sleep(0.1)
            continue
        return
    raise ReleaseSlotError("launcher_shutdown_timeout")


def _terminate_windows_process(pid: int, *, wait: bool) -> None:
    """Use Win32 process handles because ``os.kill(SIGTERM)`` is unreliable here."""
    import ctypes

    process_terminate = 0x0001
    synchronize = 0x00100000
    wait_object_0 = 0x00000000
    wait_timeout = 0x00000102
    error_invalid_parameter = 87
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(process_terminate | synchronize, False, pid)
    if not handle:
        error = kernel32.GetLastError()
        if error == error_invalid_parameter:
            return
        raise ReleaseSlotError(f"launcher_shutdown_open_failed:{error}")
    try:
        if not kernel32.TerminateProcess(handle, 0):
            raise ReleaseSlotError(
                f"launcher_shutdown_terminate_failed:{kernel32.GetLastError()}"
            )
        if not wait:
            return
        result = kernel32.WaitForSingleObject(handle, 10_000)
        if result == wait_timeout:
            raise ReleaseSlotError("launcher_shutdown_timeout")
        if result != wait_object_0:
            raise ReleaseSlotError(f"launcher_shutdown_wait_failed:{result}")
    finally:
        kernel32.CloseHandle(handle)


def diagnostics(app_root: Path) -> int:
    slots = ReleaseSlots(app_root)
    payload: dict[str, object] = {"app_root": str(slots.app_root), "state": None}
    state = _read_state(slots)
    if state is not None:
        payload["state"] = {**asdict(state), "healthy": _healthy(state)}
    try:
        payload["active_release"] = asdict(slots.read_active())
    except ReleaseSlotError as error:
        payload["active_release_error"] = str(error)
    print(json.dumps(payload, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="workbench-launcher")
    parser.add_argument("--app-root", type=Path, default=_default_app_root())
    commands = parser.add_subparsers(dest="command", required=True)
    activate_command = commands.add_parser("activate")
    activate_command.add_argument("--version", required=True)
    activate_command.add_argument("--release-root", type=Path, required=True)
    start_command = commands.add_parser("start")
    start_command.add_argument("--no-browser", action="store_true")
    commands.add_parser("open")
    commands.add_parser("restart")
    commands.add_parser("status")
    shutdown_command = commands.add_parser("shutdown")
    shutdown_command.add_argument("--wait", action="store_true")
    commands.add_parser("diagnostics")
    args = parser.parse_args(argv)
    try:
        if args.command == "activate":
            return activate(args.app_root, args.version, args.release_root)
        if args.command == "start":
            return start(args.app_root, open_browser=not args.no_browser)
        if args.command == "open":
            state = _read_state(ReleaseSlots(args.app_root))
            if state is None or not _healthy(state):
                return start(args.app_root)
            webbrowser.open(state.base_url)
            return 0
        if args.command == "restart":
            shutdown(args.app_root, wait=True)
            return start(args.app_root)
        if args.command == "shutdown":
            return shutdown(args.app_root, wait=args.wait)
        if args.command == "diagnostics":
            return diagnostics(args.app_root)
        return status(args.app_root)
    except ReleaseSlotError as error:
        print(f"WORKBENCH_LAUNCHER=BLOCK reason={error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
