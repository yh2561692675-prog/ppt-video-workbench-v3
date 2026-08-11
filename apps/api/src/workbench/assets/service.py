from __future__ import annotations

import hashlib
import json
import mimetypes
from collections.abc import Callable
from pathlib import Path
from threading import RLock
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from workbench.cache.models import CacheEntry
from workbench.cache.repository import CacheRepository
from workbench.domain.enums import JobType
from workbench.domain.models import JobRecord
from workbench.jobs.repository import JobRepository, JobSpec

from .audio_executor import WaveformDerivativeExecutor
from .derivative_models import DerivativeOperation, DerivativeRequestV1
from .image_executor import ImageDerivativeExecutor
from .models import (
    AssetDeriveRequest,
    AssetImportRequest,
    AssetRecord,
    BrandPack,
    DerivedAssetRef,
    LicenseRecord,
)
from .object_store import ContentAddressedObjectStore, StoredObject
from .video_executor import VideoDerivativeExecutor


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
        jobs: JobRepository | None = None,
    ) -> None:
        self.root = root.resolve()
        self.project_dir_resolver = project_dir_resolver
        self.jobs = jobs
        self.object_store = ContentAddressedObjectStore(
            self.root / "workspace-data" / "assets"
        )
        self.cache = CacheRepository(
            self.root / "workspace-data" / "assets" / "cache-index.json"
        )
        self._assets: dict[UUID, AssetRecord] = {}
        self._brands: dict[UUID, BrandPack] = {}
        self._lock = RLock()
        self._load()

    def submit_derivative(self, project_id: UUID, request: AssetDeriveRequest) -> JobRecord:
        if self.jobs is None:
            raise AssetRegistryError(
                "asset_jobs_unavailable", "asset job repository is unavailable"
            )
        parent = self.get(project_id, request.parent_asset_id)
        tool_fingerprint = hashlib.sha256(request.tool_version.encode("utf-8")).hexdigest()
        frozen = DerivativeRequestV1(
            parent_asset_id=parent.asset_id,
            parent_revision=parent.revision,
            parent_content_hash=parent.content_hash,
            operation=DerivativeOperation(request.operation),
            parameters=request.parameters,
            output_slot=request.operation,
            tool_fingerprint=tool_fingerprint,
        )
        job_type = (
            JobType.BUILD_WAVEFORM
            if frozen.operation is DerivativeOperation.WAVEFORM
            else JobType.DERIVE_ASSET
        )
        return self.jobs.enqueue_or_get(
            JobSpec(
                project_id=project_id,
                job_type=job_type,
                cache_key=f"asset-derivative:{frozen.fingerprint}",
                input_fingerprint=frozen.fingerprint,
                payload={"request": frozen.model_dump(mode="json")},
            )
        ).record

    def handle_derivative_job(self, job: JobRecord) -> None:
        if self.jobs is None:
            raise AssetRegistryError(
                "asset_jobs_unavailable", "asset job repository is unavailable"
            )
        raw_request = job.payload.get("request")
        request = DerivativeRequestV1.model_validate(raw_request)
        parent = self.get(job.project_id, request.parent_asset_id)
        if (
            parent.revision != request.parent_revision
            or parent.content_hash != request.parent_content_hash
        ):
            raise AssetRegistryError("asset_derivative_stale", "parent asset revision has changed")
        derivative_id = uuid5(NAMESPACE_URL, f"{job.project_id}:{request.fingerprint}")
        existing = self._assets.get(derivative_id)
        if existing is None:
            source = self._safe_path(self.root, parent.relative_object_path)
            stored = self._execute_derivative(job, parent, request, source)
            relative_path = (
                Path("workspace-data") / "assets" / stored.relative_path
            ).as_posix()
            existing = parent.model_copy(
                update={
                    "asset_id": derivative_id,
                    "revision": 1,
                    "content_hash": stored.content_hash,
                    "relative_object_path": relative_path,
                    "size_bytes": stored.size_bytes,
                    "mime_type": _mime_for_path(relative_path),
                    "derived_from": parent.asset_id,
                    "operation": f"{request.operation.value}:{request.fingerprint[:12]}",
                    "original_name": (
                        f"{Path(parent.original_name).stem}-{request.operation.value}"
                        f"{Path(relative_path).suffix}"
                    ),
                }
            )
            with self._lock:
                self._assets[existing.asset_id] = existing
                self._persist_asset(existing)
            self.cache.put(
                CacheEntry(
                    cache_key=request.fingerprint,
                    project_id=job.project_id,
                    artifact_hash=existing.content_hash,
                    relative_path=stored.relative_path,
                    size_bytes=existing.size_bytes,
                    dependencies=[
                        f"asset:{parent.asset_id}:revision:{parent.revision}",
                        f"tool:{request.tool_fingerprint}",
                    ],
                )
            )
        attempt = self.jobs.current_attempt(job.id)
        if attempt is None:
            raise AssetRegistryError(
                "asset_attempt_missing", "derivative job has no active attempt"
            )
        publication = self.jobs.reserve_publication(
            f"asset:{job.project_id}:{request.fingerprint}",
            job.id,
            attempt.id,
            existing.model_dump(mode="json"),
        )
        self.jobs.publish_publication(
            publication.publication_key,
            job_id=job.id,
            attempt_id=attempt.id,
            manifest_hash=publication.manifest_hash,
        )
        self.jobs.succeed(job.id, {"asset": existing.model_dump(mode="json")})

    def _execute_derivative(
        self,
        job: JobRecord,
        parent: AssetRecord,
        request: DerivativeRequestV1,
        source: Path,
    ) -> StoredObject:
        work_root = self.root / "workspace-data" / "assets" / ".jobs" / str(job.id)
        if request.operation is DerivativeOperation.WAVEFORM:
            return WaveformDerivativeExecutor(self.object_store, work_root).execute(request, source)
        if parent.kind.value in {"image", "logo", "sticker", "icon"}:
            return ImageDerivativeExecutor(self.object_store, work_root).execute(request, source)
        if parent.kind.value == "video":
            return VideoDerivativeExecutor(self.object_store, work_root).execute(request, source)
        raise AssetRegistryError(
            "asset_derivative_unsupported", f"derivatives are not supported for {parent.kind.value}"
        )

    def import_asset(self, project_id: UUID, request: AssetImportRequest) -> AssetRecord:
        project_root = self._project_root(project_id)
        source = self._safe_path(project_root, request.relative_path)
        if not source.is_file():
            raise AssetRegistryError("asset_source_missing", "asset source does not exist")
        stored = self.object_store.ingest_file(source)
        relative_object_path = (
            Path("workspace-data") / "assets" / stored.relative_path
        ).as_posix()
        record = AssetRecord(
            project_id=project_id,
            kind=request.kind,
            content_hash=stored.content_hash,
            relative_object_path=relative_object_path,
            original_name=request.original_name or source.name,
            mime_type=request.mime_type
            if request.mime_type != "application/octet-stream"
            else mimetypes.guess_type(source.name)[0] or "application/octet-stream",
            size_bytes=stored.size_bytes,
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
                    and item.content_hash == stored.content_hash
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


def _mime_for_path(relative_path: str) -> str:
    return mimetypes.guess_type(relative_path)[0] or "application/octet-stream"


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
