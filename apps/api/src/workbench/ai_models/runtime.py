"""Runtime probes and reference-counted model leases."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from workbench.audio.models import WhisperModelManager

from .manifests import verify_model_install
from .models import LocalModelRecordV1, ModelRuntimeProbeV1
from .registry import LocalModelRegistry


class ModelLease(AbstractContextManager["ModelLease"]):
    def __init__(self, manager: ModelRuntimeManager, record: LocalModelRecordV1) -> None:
        self._manager = manager
        self.record = record
        self._released = False

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        self.release()

    def release(self) -> None:
        if self._released:
            return
        self._released = True
        self._manager._release(self.record)


class ModelRuntimeManager:
    def __init__(self, root: Path, registry: LocalModelRegistry) -> None:
        self.root = root.resolve()
        self.registry = registry

    def model_root(self, model_id: str, revision: str) -> Path:
        return self.root / "artifacts" / model_id / revision

    def probe(
        self,
        model_id: str,
        revision: str | None = None,
        *,
        device: str = "cpu",
    ) -> ModelRuntimeProbeV1:
        record = self.registry.get(model_id, revision)
        started = perf_counter()
        root = self.model_root(record.descriptor.model_id, record.descriptor.revision)
        try:
            verify_model_install(record.descriptor, root)
            manifest_valid = True
        except Exception:
            manifest_valid = False
        if not manifest_valid:
            probe = ModelRuntimeProbeV1(
                model_id=model_id,
                revision=record.descriptor.revision,
                status="missing",
                device="unknown",
                startup_ms=round((perf_counter() - started) * 1000),
                error_code="model_manifest_invalid",
            )
        elif device not in record.descriptor.supported_devices:
            probe = ModelRuntimeProbeV1(
                model_id=model_id,
                revision=record.descriptor.revision,
                status="incompatible",
                device="unknown",
                startup_ms=round((perf_counter() - started) * 1000),
                error_code="device_not_supported",
            )
        else:
            probe = ModelRuntimeProbeV1(
                model_id=model_id,
                revision=record.descriptor.revision,
                status="available",
                device=device,
                startup_ms=round((perf_counter() - started) * 1000),
            )
        self.registry.set_probe(probe)
        return probe

    def acquire(
        self,
        model_id: str,
        revision: str | None = None,
        *,
        device: str = "cpu",
    ) -> ModelLease:
        record = self.registry.get(model_id, revision)
        probe = self.probe(model_id, record.descriptor.revision, device=device)
        if probe.status != "available":
            raise RuntimeError(probe.error_code or "model_runtime_unavailable")
        updated_install = record.install.model_copy(
            update={
                "status": "active",
                "active_lease_count": record.install.active_lease_count + 1,
                "last_probe_at": datetime.now(UTC),
            }
        )
        active = record.model_copy(update={"install": updated_install})
        self.registry.update(active)
        return ModelLease(self, active)

    def _release(self, record: LocalModelRecordV1) -> None:
        current = self.registry.get(record.descriptor.model_id, record.descriptor.revision)
        count = max(0, current.install.active_lease_count - 1)
        updated = current.install.model_copy(
            update={"active_lease_count": count, "status": "ready" if count == 0 else "active"}
        )
        self.registry.update(current.model_copy(update={"install": updated}))


class RegistryWhisperModelManager(WhisperModelManager):
    """Bridge legacy Faster-Whisper callers to the workspace model center.

    Legacy ``settings/asr-models`` remains a read-only fallback so existing
    projects continue to open, while an active AI model-center revision wins
    whenever one is registered for the requested model id.
    """

    def __init__(
        self,
        legacy_root: Path,
        registry: LocalModelRegistry,
        runtime: ModelRuntimeManager,
    ) -> None:
        super().__init__(legacy_root)
        self.registry = registry
        self.runtime = runtime

    def model_path(self, name: str) -> Path:
        record = self._registered(name)
        if record is None:
            return super().model_path(name)
        return self.runtime.model_root(record.descriptor.model_id, record.descriptor.revision)

    def is_available(self, name: str) -> bool:
        record = self._registered(name)
        if record is None:
            return super().is_available(name)
        if record.install.status not in {"ready", "active"}:
            return False
        try:
            verify_model_install(record.descriptor, self.model_path(name))
            return True
        except Exception:
            return False

    def _registered(self, name: str) -> LocalModelRecordV1 | None:
        records = [item for item in self.registry.list() if item.descriptor.model_id == name]
        active = [item for item in records if item.install.status == "active"]
        if active:
            return sorted(active, key=lambda item: item.descriptor.revision)[-1]
        ready = [item for item in records if item.install.status == "ready"]
        return sorted(ready, key=lambda item: item.descriptor.revision)[-1] if ready else None
