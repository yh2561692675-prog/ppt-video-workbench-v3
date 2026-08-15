"""Durable workspace inventory for local model descriptors and installs."""

from __future__ import annotations

import json
import os
from pathlib import Path
from threading import RLock

from .models import LocalModelDescriptorV1, LocalModelRecordV1, ModelRuntimeProbeV1


class ModelRegistryError(RuntimeError):
    pass


class LocalModelRegistry:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.registry_path = self.root / "registry.json"
        self._lock = RLock()
        self._records: dict[tuple[str, str], LocalModelRecordV1] = {}
        self._load()

    def register(
        self,
        descriptor: LocalModelDescriptorV1,
        *,
        record: LocalModelRecordV1 | None = None,
    ) -> LocalModelRecordV1:
        with self._lock:
            key = (descriptor.model_id, descriptor.revision)
            if record is None:
                from .models import ModelInstallRecordV1

                record = LocalModelRecordV1(
                    descriptor=descriptor,
                    install=ModelInstallRecordV1(
                        model_id=descriptor.model_id,
                        revision=descriptor.revision,
                        status="not_installed",
                    ),
                )
            if record.descriptor != descriptor:
                raise ModelRegistryError("record descriptor does not match registered descriptor")
            self._records[key] = record
            self._save()
            return record

    def get(self, model_id: str, revision: str | None = None) -> LocalModelRecordV1:
        with self._lock:
            candidates = [
                record
                for (candidate_id, candidate_revision), record in self._records.items()
                if candidate_id == model_id
                and (revision is None or candidate_revision == revision)
            ]
            if not candidates:
                raise ModelRegistryError("model revision is not registered")
            return sorted(candidates, key=lambda item: item.descriptor.revision)[-1]

    def list(self, *, kind: str | None = None) -> list[LocalModelRecordV1]:
        with self._lock:
            records = list(self._records.values())
        if kind is not None:
            records = [record for record in records if record.descriptor.kind == kind]
        return sorted(
            records,
            key=lambda item: (item.descriptor.model_id, item.descriptor.revision),
        )

    def update(self, record: LocalModelRecordV1) -> LocalModelRecordV1:
        with self._lock:
            key = (record.descriptor.model_id, record.descriptor.revision)
            if key not in self._records:
                raise ModelRegistryError("cannot update an unregistered model")
            self._records[key] = record
            self._save()
            return record

    def set_probe(self, probe: ModelRuntimeProbeV1) -> LocalModelRecordV1:
        record = self.get(probe.model_id, probe.revision)
        return self.update(record.model_copy(update={"last_probe": probe}))

    def activate(self, model_id: str, revision: str) -> LocalModelRecordV1:
        with self._lock:
            target = self.get(model_id, revision)
            if target.install.status not in {"ready", "active"}:
                raise ModelRegistryError("only a ready model can be activated")
            for key, record in list(self._records.items()):
                if record.descriptor.model_id != model_id:
                    continue
                status = "active" if key == (model_id, revision) else (
                    "ready" if record.install.status == "active" else record.install.status
                )
                self._records[key] = record.model_copy(
                    update={"install": record.install.model_copy(update={"status": status})}
                )
            self._save()
            return self._records[(model_id, revision)]

    def remove(self, model_id: str, revision: str) -> None:
        with self._lock:
            record = self.get(model_id, revision)
            if record.install.active_lease_count:
                raise ModelRegistryError("model has active runtime leases")
            if record.install.status == "active":
                raise ModelRegistryError("active model must be rolled back before removal")
            self._records.pop((model_id, revision), None)
            self._save()

    def _load(self) -> None:
        if not self.registry_path.is_file():
            return
        try:
            payload = json.loads(self.registry_path.read_text(encoding="utf-8"))
            records = payload.get("records", [])
            parsed = [LocalModelRecordV1.model_validate(item) for item in records]
        except (OSError, ValueError, TypeError) as error:
            raise ModelRegistryError("model registry is unreadable") from error
        self._records = {
            (item.descriptor.model_id, item.descriptor.revision): item for item in parsed
        }

    def _save(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "records": [record.model_dump(mode="json") for record in self.list()],
        }
        temporary = self.registry_path.with_name(".registry.json.part")
        temporary.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        with temporary.open("r+b") as handle:
            os.fsync(handle.fileno())
        os.replace(temporary, self.registry_path)
