from __future__ import annotations

import argparse
import base64
import hashlib
import io
import re
import zipfile
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from peripheral_contracts import BusinessResultManifest, JobEnvelope
from PIL import Image, UnidentifiedImageError

from workbench.business_modules.p03_material.models import (
    MaterialIngestParameters,
    MaterialReorderParameters,
    MaterialSource,
    MaterialSourcesPayload,
)
from workbench.business_modules.runtime import (
    BusinessExecution,
    StagedArtifact,
    business_input_fingerprint,
    business_parameters,
    execute_business_handler,
    project_revision,
)
from workbench.domain.models import AuditEvent, ProjectManifest
from workbench.domain.source_file import SourceFile, SourceKind

MAX_FILE_BYTES = 500 * 1024 * 1024
MAX_IMAGE_PIXELS = 120_000_000
WINDOWS_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}
SOURCE_FOLDER = "01_源文件"


class MaterialRejected(ValueError):
    """The material is empty, malformed, unsafe, or unsupported."""


def stage_material_bytes(
    items: Iterable[tuple[str, bytes]],
    destination: Path,
) -> list[dict[str, Any]]:
    validated: list[tuple[str, bytes, str]] = []
    for original_name, content in items:
        kind = _validate(original_name, content)
        validated.append((original_name, content, kind))
    if not validated:
        raise MaterialRejected("no material files supplied")
    if all(kind == "image" for _, _, kind in validated):
        validated.sort(key=lambda item: _natural_key(item[0]))

    destination.mkdir(parents=True, exist_ok=True)
    used: set[str] = set()
    image_order = 0
    outputs: list[dict[str, Any]] = []
    for original_name, content, kind in validated:
        safe_name = _available_name(_safe_file_name(original_name), used)
        used.add(safe_name)
        (destination / safe_name).write_bytes(content)
        if kind == "image":
            image_order += 1
        outputs.append(
            {
                "original_name": original_name,
                "safe_name": safe_name,
                "kind": kind,
                "size_bytes": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
                "image_order": image_order if kind == "image" else None,
                "relative_path": safe_name,
            }
        )
    return outputs


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8-sig"))

    def handler(received: JobEnvelope, attempt_root: Path) -> BusinessExecution:
        staged_dir = attempt_root / "materials"
        if received.job_type == "material.ingest":
            ingest_parameters = MaterialIngestParameters.model_validate(
                business_parameters(received)
            )
            items = _ingest_items(received, attempt_root, ingest_parameters)
            raw_sources = stage_material_bytes(items, staged_dir)
            payload = MaterialSourcesPayload(
                operation="ingest",
                sources=tuple(MaterialSource.model_validate(item) for item in raw_sources),
                ordered_names=tuple(str(item["safe_name"]) for item in raw_sources),
            )
            artifacts = tuple(
                StagedArtifact(
                    logical_name=_artifact_name(source.safe_name),
                    kind=source.kind,
                    path=staged_dir / source.safe_name,
                )
                for source in payload.sources
            )
        elif received.job_type == "material.reorder":
            reorder_parameters = MaterialReorderParameters.model_validate(
                business_parameters(received)
            )
            by_name = {item.safe_name: item for item in reorder_parameters.sources}
            reordered: list[MaterialSource] = []
            image_order = 0
            for name in reorder_parameters.ordered_names:
                source = by_name[name]
                if source.kind == "image":
                    image_order += 1
                reordered.append(
                    source.model_copy(
                        update={"image_order": image_order if source.kind == "image" else None}
                    )
                )
            payload = MaterialSourcesPayload(
                operation="reorder",
                sources=tuple(reordered),
                ordered_names=reorder_parameters.ordered_names,
            )
            artifacts = ()
        else:
            raise MaterialRejected(f"unsupported P03 job type: {received.job_type}")
        fingerprint = business_input_fingerprint(received)
        result = BusinessResultManifest(
            schema_version="1.0",
            module_id="P03",
            job_type=received.job_type,
            project_id=received.project_id,
            project_revision=project_revision(received),
            input_fingerprint=fingerprint,
            cache_key=hashlib.sha256(
                (fingerprint + received.job_type + "material_sources").encode()
            ).hexdigest(),
            result_type="material_sources",
            payload=payload.model_dump(mode="json"),
        )
        return BusinessExecution(result, artifacts)

    execution = execute_business_handler(job, args.result.parent, args.result, "P03", handler)
    return 0 if execution.outcome == "succeeded" else 1


def _validate(name: str, content: bytes) -> str:
    if not content:
        raise MaterialRejected(f"{name} is empty")
    if len(content) > MAX_FILE_BYTES:
        raise MaterialRejected(f"{name} exceeds the file size limit")
    suffix = Path(name).suffix.lower()
    if content.startswith(b"%PDF-"):
        kind = "pdf"
        valid = suffix == ".pdf"
    elif content.startswith(
        (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"BM", b"II*\x00", b"MM\x00*")
    ) or (len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP"):
        kind = "image"
        valid = suffix in IMAGE_EXTENSIONS
    elif content.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
                total_uncompressed = sum(item.file_size for item in archive.infolist())
        except (zipfile.BadZipFile, OSError) as error:
            raise MaterialRejected(f"{name} is not a valid office archive") from error
        if total_uncompressed > MAX_FILE_BYTES * 4:
            raise MaterialRejected(f"{name} has an unsafe archive expansion ratio")
        if "word/document.xml" in names:
            kind, valid = "docx", suffix == ".docx"
        elif "ppt/presentation.xml" in names:
            kind, valid = "pptx", suffix == ".pptx"
        else:
            raise MaterialRejected(f"{name} is not a supported office document")
    else:
        raise MaterialRejected(f"{name} has an unsupported file signature")
    if not valid:
        raise MaterialRejected(f"{name} extension does not match its file signature")
    if kind == "image":
        try:
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as error:
            raise MaterialRejected(f"{name} is a corrupt image") from error
        if width * height > MAX_IMAGE_PIXELS:
            raise MaterialRejected(f"{name} exceeds the image pixel limit")
    return kind


def _ingest_items(
    job: JobEnvelope,
    attempt_root: Path,
    parameters: MaterialIngestParameters,
) -> list[tuple[str, bytes]]:
    items: list[tuple[str, bytes]] = []
    if job.inputs:
        names = parameters.input_names or tuple(Path(item.path).name for item in job.inputs)
        if len(names) != len(job.inputs):
            raise MaterialRejected("input_names must match the number of input artifacts")
        for name, reference in zip(names, job.inputs, strict=True):
            source = (attempt_root / reference.path).resolve()
            if not source.is_relative_to(attempt_root.resolve()) or not source.is_file():
                raise MaterialRejected("material input escapes the attempt directory")
            content = source.read_bytes()
            if len(content) != reference.size_bytes:
                raise MaterialRejected("material input size changed after staging")
            if hashlib.sha256(content).hexdigest() != reference.sha256:
                raise MaterialRejected("material input hash changed after staging")
            items.append((name, content))
    for item in parameters.files:
        try:
            content = base64.b64decode(item.content_base64, validate=True)
        except ValueError as error:
            raise MaterialRejected("material content is not valid base64") from error
        items.append((item.name, content))
    return items


def _safe_file_name(name: str) -> str:
    stripped = Path(name.replace("\\", "/")).name.strip()
    safe = WINDOWS_INVALID.sub("_", stripped).rstrip(". ")
    if not safe or safe in {".", ".."}:
        raise MaterialRejected("material name is invalid")
    return safe[:180]


def _available_name(name: str, existing: set[str]) -> str:
    if name not in existing:
        return name
    path = Path(name)
    counter = 2
    while True:
        candidate = f"{path.stem}_{counter}{path.suffix}"
        if candidate not in existing:
            return candidate
        counter += 1


def _natural_key(name: str) -> list[tuple[int, int | str]]:
    return [
        (0, int(part)) if part.isdigit() else (1, part.casefold())
        for part in re.split(r"(\d+)", name)
    ]


def _artifact_name(name: str) -> str:
    stem = Path(name).stem.lower()
    safe = re.sub(r"[^a-z0-9_.-]", "-", stem).strip("-") or "material"
    return f"material-{safe}"[:64]


if __name__ == "__main__":
    raise SystemExit(main())


def project_material_sources(result: BusinessResultManifest, project_dir: Path) -> None:
    """Apply P03 sources to project.json while preserving existing source IDs."""
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    payload = MaterialSourcesPayload.model_validate(result.payload)
    if payload.operation == "reorder":
        existing_by_name = {item.safe_name: item for item in manifest.source_files}
        if set(existing_by_name) != set(payload.ordered_names):
            raise MaterialRejected("reorder payload does not match current project sources")
        order_by_name = {item.safe_name: item.image_order for item in payload.sources}
        reordered = [
            existing_by_name[name].model_copy(update={"image_order": order_by_name[name]})
            for name in payload.ordered_names
        ]
        updated = manifest.model_copy(
            update={
                "source_files": reordered,
                "audit_log": [
                    *manifest.audit_log,
                    AuditEvent(
                        action="sources_reordered",
                        occurred_at=datetime.now(UTC),
                        details={"ordered_names": list(payload.ordered_names)},
                    ),
                ],
            }
        )
        _write_project_manifest(manifest_path, updated)
        return
    existing = {item.safe_name for item in manifest.source_files}
    now = datetime.now(UTC)
    imported: list[SourceFile] = []
    next_image_order = 1 + max((item.image_order or 0 for item in manifest.source_files), default=0)
    for source in payload.sources:
        item = source.model_dump(mode="json")
        safe_name = source.safe_name
        if not safe_name or safe_name in existing:
            continue
        kind = SourceKind(source.kind)
        image_order = next_image_order if kind is SourceKind.IMAGE else None
        if image_order is not None:
            next_image_order += 1
        imported.append(
            SourceFile(
                id=uuid4(),
                kind=kind,
                original_name=str(item.get("original_name", safe_name)),
                safe_name=safe_name,
                copied_path=(Path(SOURCE_FOLDER) / safe_name).as_posix(),
                sha256=str(item["sha256"]),
                size=int(item["size_bytes"]),
                modified_at=now,
                image_order=image_order,
            )
        )
        existing.add(safe_name)
    updated = manifest.model_copy(
        update={
            "source_files": [*manifest.source_files, *imported],
            "audit_log": [
                *manifest.audit_log,
                AuditEvent(
                    action="sources_imported",
                    occurred_at=now,
                    details={"source_ids": [str(item.id) for item in imported]},
                ),
            ],
        }
    )
    _write_project_manifest(manifest_path, updated)


def _write_project_manifest(path: Path, manifest: ProjectManifest) -> None:
    temporary = path.with_name(".project.json.s1.tmp")
    temporary.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    temporary.replace(path)
