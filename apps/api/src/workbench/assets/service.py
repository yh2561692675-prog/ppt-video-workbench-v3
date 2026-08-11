from __future__ import annotations

import hashlib
import json
import mimetypes
import shutil
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from uuid import UUID, uuid4

from .models import (
    AssetDeriveRequest,
    AssetImportRequest,
    AssetRecord,
    BrandPack,
    DerivedAssetRef,
    LicenseRecord,
)


class AssetRegistryError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AssetRegistryService:
    """Content-addressed asset storage with project-relative source access."""

    def __init__(
        self,
        root: Path,
        project_dir_resolver: Callable[[UUID], str] | None = None,
    ) -> None:
        self.root = root.resolve()
        self.project_dir_resolver = project_dir_resolver
        self._assets: dict[UUID, AssetRecord] = {}
        self._brands: dict[UUID, BrandPack] = {}
        self._lock = RLock()
        self._load()

    def import_asset(self, project_id: UUID, request: AssetImportRequest) -> AssetRecord:
        project_root = self._project_root(project_id)
        source = self._safe_path(project_root, request.relative_path)
        if not source.is_file():
            raise AssetRegistryError("asset_source_missing", "asset source does not exist")
        digest, size = _hash_file(source)
        object_path = self._object_path(digest, source.suffix)
        object_path.parent.mkdir(parents=True, exist_ok=True)
        if not object_path.is_file():
            temporary = object_path.with_name(f".{object_path.name}.part")
            shutil.copyfile(source, temporary)
            temporary.replace(object_path)
        record = AssetRecord(
            project_id=project_id,
            kind=request.kind,
            content_hash=digest,
            relative_object_path=self._relative(object_path),
            original_name=request.original_name or source.name,
            mime_type=request.mime_type
            if request.mime_type != "application/octet-stream"
            else mimetypes.guess_type(source.name)[0] or "application/octet-stream",
            size_bytes=size,
            license=request.license,
            tags=sorted(set(request.tags)),
            brand_pack_id=request.brand_pack_id,
        )
        with self._lock:
            duplicate = next(
                (
                    item
                    for item in self._assets.values()
                    if item.project_id == project_id
                    and item.content_hash == digest
                    and item.kind == record.kind
                ),
                None,
            )
            if duplicate is not None:
                return duplicate
            self._assets[record.asset_id] = record
            self._persist_asset(record)
        return record

    def derive(self, project_id: UUID, request: AssetDeriveRequest) -> AssetRecord:
        parent = self.get(project_id, request.parent_asset_id)
        operation_ref = DerivedAssetRef(
            asset_id=parent.asset_id,
            operation=request.operation,
            parameters=request.parameters,
            tool_version=request.tool_version,
        )
        # The first safe implementation records a deterministic derivative
        # reference. Heavy image/video transforms are delegated to a job and
        # must publish a new object before replacing this metadata reference.
        parameter_hash = hashlib.sha256(
            json.dumps(request.parameters, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:12]
        record = parent.model_copy(
            update={
                "asset_id": uuid4(),
                "revision": 1,
                "derived_from": parent.asset_id,
                "operation": f"{request.operation}:{parameter_hash}",
                "original_name": (
                    f"{Path(parent.original_name).stem}-{request.operation}"
                    f"{Path(parent.original_name).suffix}"
                ),
            }
        )
        # Validate the reference even though the job will later materialize
        # an independent object; this prevents arbitrary operation metadata.
        operation_ref.model_dump(mode="json")
        with self._lock:
            self._assets[record.asset_id] = record
            self._persist_asset(record)
        return record

    def get(self, project_id: UUID, asset_id: UUID) -> AssetRecord:
        record = self._assets.get(asset_id)
        if record is None or record.project_id != project_id:
            raise KeyError(asset_id)
        return record

    def list_assets(self, project_id: UUID, *, kind: str | None = None) -> list[AssetRecord]:
        values = [item for item in self._assets.values() if item.project_id == project_id]
        if kind is not None:
            values = [item for item in values if item.kind.value == kind]
        return sorted(values, key=lambda item: (item.created_at, str(item.asset_id)))

    def update_license(
        self, project_id: UUID, asset_id: UUID, license_record: LicenseRecord
    ) -> AssetRecord:
        record = self.get(project_id, asset_id)
        updated = record.model_copy(
            update={"revision": record.revision + 1, "license": license_record}
        )
        with self._lock:
            self._assets[asset_id] = updated
            self._persist_asset(updated)
        return updated

    def create_brand_pack(self, pack: BrandPack) -> BrandPack:
        for asset_id in pack.asset_ids:
            if asset_id not in self._assets:
                raise AssetRegistryError(
                    "brand_asset_missing", "brand pack references an unknown asset"
                )
        with self._lock:
            self._brands[pack.brand_pack_id] = pack
            self._persist_brand(pack)
        return pack

    def brand_packs(self, project_id: UUID) -> list[BrandPack]:
        return sorted(
            [item for item in self._brands.values() if item.project_id in {None, project_id}],
            key=lambda item: str(item.brand_pack_id),
        )

    def _project_root(self, project_id: UUID) -> Path:
        relative = (
            self.project_dir_resolver(project_id) if self.project_dir_resolver else str(project_id)
        )
        return self._safe_path(self.root, relative, allow_missing=True)

    def _object_path(self, digest: str, suffix: str) -> Path:
        return (
            self.root
            / "workspace-data"
            / "assets"
            / "objects"
            / digest[:2]
            / f"{digest}{suffix.lower()}"
        )

    def _relative(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def _persist_asset(self, record: AssetRecord) -> None:
        target = self.root / "workspace-data" / "assets" / "index" / f"{record.asset_id}.json"
        _atomic_json(target, record.model_dump(mode="json"))

    def _persist_brand(self, pack: BrandPack) -> None:
        target = (
            self.root / "workspace-data" / "assets" / "brand-packs" / f"{pack.brand_pack_id}.json"
        )
        _atomic_json(target, pack.model_dump(mode="json"))

    def _load(self) -> None:
        index = self.root / "workspace-data" / "assets" / "index"
        for path in index.glob("*.json"):
            try:
                record = AssetRecord.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            self._assets[record.asset_id] = record
        brands = self.root / "workspace-data" / "assets" / "brand-packs"
        for path in brands.glob("*.json"):
            try:
                pack = BrandPack.model_validate_json(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            self._brands[pack.brand_pack_id] = pack

    @staticmethod
    def _safe_path(base: Path, relative: str, *, allow_missing: bool = False) -> Path:
        candidate = (base / relative).resolve()
        try:
            candidate.relative_to(base.resolve())
        except ValueError as error:
            raise AssetRegistryError(
                "asset_path_outside_project", "asset path must stay inside project"
            ) from error
        if not allow_missing and not candidate.exists():
            return candidate
        return candidate


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
