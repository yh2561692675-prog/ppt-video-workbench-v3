"""Atomic local model installation and offline import."""

from __future__ import annotations

import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from .manifests import sha256_file, verify_model_install, write_manifest
from .models import (
    LocalModelDescriptorV1,
    LocalModelRecordV1,
    ModelFileV1,
    ModelInstallRecordV1,
    ModelKind,
)
from .registry import LocalModelRegistry, ModelRegistryError


class ModelProvisionError(RuntimeError):
    pass


class LocalModelProvisioner:
    def __init__(self, root: Path, registry: LocalModelRegistry) -> None:
        self.root = root.resolve()
        self.registry = registry

    def model_root(self, model_id: str, revision: str) -> Path:
        if any(char in model_id for char in "\\/:") or any(
            char in revision for char in "\\/:"
        ):
            raise ModelProvisionError("model identity contains an unsafe path character")
        return self.root / "artifacts" / model_id / revision

    def install_from_directory(
        self,
        descriptor: LocalModelDescriptorV1,
        source_root: Path,
        *,
        attempt_id: uuid.UUID | None = None,
    ) -> LocalModelRecordV1:
        attempt = attempt_id or uuid.uuid4()
        target = self.model_root(descriptor.model_id, descriptor.revision)
        if target.exists():
            try:
                _, manifest_hash = verify_model_install(descriptor, target)
            except Exception as error:
                raise ModelProvisionError("existing model revision is corrupt") from error
            return self._ready_record(descriptor, attempt, manifest_hash)

        staging = self.root / "downloads" / str(attempt) / "model"
        if staging.exists():
            shutil.rmtree(staging)
        staging.mkdir(parents=True, exist_ok=False)
        try:
            for declared in descriptor.files:
                source = self._safe_child(source_root, declared.relative_path)
                if not source.is_file():
                    raise ModelProvisionError(
                        f"required model file is missing: {declared.relative_path}"
                    )
                destination = self._safe_child(staging, declared.relative_path)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, destination)
            manifest, manifest_hash = verify_model_install(descriptor, staging)
            write_manifest(staging / "model-manifest.json", manifest)
            target.parent.mkdir(parents=True, exist_ok=True)
            target_staging = target.with_name(f".{target.name}.{attempt}.part")
            if target_staging.exists():
                shutil.rmtree(target_staging)
            staging.rename(target_staging)
            target_staging.rename(target)
        except Exception as error:
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            raise ModelProvisionError(str(error)) from error
        finally:
            download_root = self.root / "downloads" / str(attempt)
            if download_root.exists():
                shutil.rmtree(download_root, ignore_errors=True)
        return self._ready_record(descriptor, attempt, manifest_hash)

    def import_legacy_asr(
        self,
        descriptor: LocalModelDescriptorV1,
        legacy_root: Path,
        *,
        attempt_id: uuid.UUID | None = None,
    ) -> LocalModelRecordV1:
        return self.install_from_directory(descriptor, legacy_root, attempt_id=attempt_id)

    def _ready_record(
        self,
        descriptor: LocalModelDescriptorV1,
        attempt_id: uuid.UUID,
        manifest_hash: str,
    ) -> LocalModelRecordV1:
        now = datetime.now(UTC)
        record = LocalModelRecordV1(
            descriptor=descriptor,
            install=ModelInstallRecordV1(
                model_id=descriptor.model_id,
                revision=descriptor.revision,
                status="ready",
                attempt_id=attempt_id,
                bytes_total=sum(item.size_bytes for item in descriptor.files),
                bytes_completed=sum(item.size_bytes for item in descriptor.files),
                manifest_sha256=manifest_hash,
                installed_at=now,
            ),
        )
        try:
            return self.registry.update(record)
        except ModelRegistryError:
            return self.registry.register(descriptor, record=record)

    @staticmethod
    def _safe_child(root: Path, relative_path: str) -> Path:
        candidate = (root / Path(*relative_path.split("/"))).resolve()
        try:
            candidate.relative_to(root.resolve())
        except ValueError as error:
            raise ModelProvisionError("model file escapes model root") from error
        return candidate


def descriptor_from_directory(
    *,
    model_id: str,
    display_name: str,
    kind: ModelKind,
    engine: str,
    engine_version: str,
    revision: str,
    source_ref: str,
    license_ref: str,
    source_root: Path,
    relative_files: list[str],
    supported_languages: list[str] | None = None,
    capabilities: list[str] | None = None,
    runtime_contract_version: str = "1.0",
) -> LocalModelDescriptorV1:
    files: list[ModelFileV1] = []
    for relative in relative_files:
        path = LocalModelProvisioner._safe_child(source_root, relative)
        if not path.is_file():
            raise ModelProvisionError(f"required model file is missing: {relative}")
        files.append(
            ModelFileV1(
                relative_path=relative.replace("\\", "/"),
                size_bytes=path.stat().st_size,
                sha256=sha256_file(path),
            )
        )
    return LocalModelDescriptorV1(
        model_id=model_id,
        display_name=display_name,
        kind=kind,
        engine=engine,
        engine_version=engine_version,
        revision=revision,
        source_ref=source_ref,
        supported_languages=supported_languages or [],
        capabilities=capabilities or [],
        license_ref=license_ref,
        files=files,
        runtime_contract_version=runtime_contract_version,
    )
