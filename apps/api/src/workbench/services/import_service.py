from __future__ import annotations

import hashlib
import io
import re
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Final
from uuid import UUID, uuid4

from PIL import Image, UnidentifiedImageError

from workbench.domain.models import AuditEvent
from workbench.domain.source_file import SourceFile, SourceKind
from workbench.services.project_service import WINDOWS_INVALID, ProjectService

DEFAULT_MAX_FILE_BYTES: Final = 500 * 1024 * 1024
DEFAULT_MAX_IMAGE_PIXELS: Final = 120_000_000
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff"}


class ImportRejected(ValueError):
    pass


class ImportService:
    def __init__(
        self,
        projects: ProjectService,
        *,
        max_file_bytes: int = DEFAULT_MAX_FILE_BYTES,
        max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
    ) -> None:
        self.projects = projects
        self.max_file_bytes = max_file_bytes
        self.max_image_pixels = max_image_pixels

    def import_bytes(self, project_id: UUID, original_name: str, content: bytes) -> SourceFile:
        return self.import_batch(project_id, [(original_name, content)])[0]

    def import_batch(self, project_id: UUID, items: list[tuple[str, bytes]]) -> list[SourceFile]:
        if not items:
            raise ImportRejected("未选择材料文件")
        validated = [self._validate(name, content) for name, content in items]
        if all(kind is SourceKind.IMAGE for _, _, kind in validated):
            validated.sort(key=lambda item: _natural_key(item[0]))

        manifest = self.projects.get(project_id)
        project_dir = self.projects.workspace_root / manifest.project_dir
        source_dir = project_dir / "01_源文件"
        existing_names = {source.safe_name for source in manifest.source_files}
        imported: list[SourceFile] = []
        next_image_order = 1 + max(
            (source.image_order or 0 for source in manifest.source_files), default=0
        )
        image_indices = sorted(
            [index for index, (_, _, kind) in enumerate(validated) if kind is SourceKind.IMAGE],
            key=lambda index: _natural_key(validated[index][0]),
        )
        image_orders = {
            source_index: next_image_order + rank for rank, source_index in enumerate(image_indices)
        }
        now = datetime.now(UTC)
        for source_index, (original_name, content, kind) in enumerate(validated):
            safe_name = _available_name(_safe_file_name(original_name), existing_names)
            existing_names.add(safe_name)
            target = source_dir / safe_name
            target.write_bytes(content)
            image_order = image_orders.get(source_index)
            imported.append(
                SourceFile(
                    id=uuid4(),
                    kind=kind,
                    original_name=original_name,
                    safe_name=safe_name,
                    copied_path=(Path("01_源文件") / safe_name).as_posix(),
                    sha256=hashlib.sha256(content).hexdigest(),
                    size=len(content),
                    modified_at=now,
                    image_order=image_order,
                )
            )
        updated = manifest.model_copy(
            update={
                "source_files": [*manifest.source_files, *imported],
                "audit_log": [
                    *manifest.audit_log,
                    AuditEvent(
                        action="sources_imported",
                        occurred_at=now,
                        details={"source_ids": [str(source.id) for source in imported]},
                    ),
                ],
            }
        )
        self.projects.save(updated)
        return imported

    def reorder_images(self, project_id: UUID, ordered_ids: list[UUID]) -> list[SourceFile]:
        manifest = self.projects.get(project_id)
        images = [source for source in manifest.source_files if source.kind is SourceKind.IMAGE]
        if len(ordered_ids) != len(images) or set(ordered_ids) != {item.id for item in images}:
            raise ImportRejected("图片顺序必须包含当前项目的全部图片且不得重复")
        by_id = {item.id: item for item in images}
        reordered = [
            by_id[source_id].model_copy(update={"image_order": index})
            for index, source_id in enumerate(ordered_ids, start=1)
        ]
        replacements = {item.id: item for item in reordered}
        source_files = [replacements.get(source.id, source) for source in manifest.source_files]
        now = datetime.now(UTC)
        updated = manifest.model_copy(
            update={
                "source_files": source_files,
                "audit_log": [
                    *manifest.audit_log,
                    AuditEvent(
                        action="image_order_changed",
                        occurred_at=now,
                        details={"ordered_ids": [str(value) for value in ordered_ids]},
                    ),
                ],
            }
        )
        self.projects.save(updated)
        return reordered

    def _validate(self, original_name: str, content: bytes) -> tuple[str, bytes, SourceKind]:
        if not content:
            raise ImportRejected(f"{original_name} 是空文件")
        if len(content) > self.max_file_bytes:
            raise ImportRejected(f"{original_name} 超过文件大小限制")
        kind = _detect_kind(content)
        if kind is None or not _extension_matches(original_name, kind):
            raise ImportRejected(f"{original_name} 的文件类型与扩展名不一致或不受支持")
        if kind is SourceKind.IMAGE:
            self._validate_image(original_name, content)
        return original_name, content, kind

    def _validate_image(self, original_name: str, content: bytes) -> None:
        try:
            with Image.open(io.BytesIO(content)) as image:
                width, height = image.size
                image.verify()
        except (UnidentifiedImageError, OSError, SyntaxError) as error:
            raise ImportRejected(f"{original_name} 是损坏图片") from error
        if width * height > self.max_image_pixels:
            raise ImportRejected(f"{original_name} 的像素总量超过安全限制")


def _detect_kind(content: bytes) -> SourceKind | None:
    if content.startswith(b"%PDF-"):
        return SourceKind.PDF
    if content.startswith((b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n", b"BM", b"II*\x00", b"MM\x00*")):
        return SourceKind.IMAGE
    if len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return SourceKind.IMAGE
    if content.startswith(b"PK"):
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                names = set(archive.namelist())
        except zipfile.BadZipFile:
            return None
        if "word/document.xml" in names:
            return SourceKind.DOCX
        if "ppt/presentation.xml" in names:
            return SourceKind.PPTX
    return None


def _extension_matches(name: str, kind: SourceKind) -> bool:
    suffix = Path(name).suffix.lower()
    expected = {
        SourceKind.DOCX: {".docx"},
        SourceKind.PPTX: {".pptx"},
        SourceKind.PDF: {".pdf"},
        SourceKind.IMAGE: IMAGE_EXTENSIONS,
    }
    return suffix in expected[kind]


def _safe_file_name(original_name: str) -> str:
    basename = Path(original_name.replace("\\", "/")).name.strip()
    safe = WINDOWS_INVALID.sub("_", basename).rstrip(". ")
    if not safe or safe in {".", ".."}:
        raise ImportRejected("文件名无有效字符")
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
