from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from workbench.domain.enums import NodeStatus
from workbench.domain.extraction import PageExtraction
from workbench.domain.matching import PageMatch
from workbench.domain.models import AuditEvent, PageRecord
from workbench.domain.source_file import SourceFile, SourceKind
from workbench.matching.page_matcher import match_outline_to_pages
from workbench.ocr.paddle_adapter import OcrEngine, OcrUnavailableError
from workbench.parsers.docx_parser import DocumentParseError, write_outline_artifact
from workbench.parsers.image_parser import ImageParseError, parse_images
from workbench.parsers.pdf_parser import EncryptedPdfError, OcrPolicy, PdfParseError, parse_pdf
from workbench.parsers.pptx_parser import PresentationParseError
from workbench.renderers.office_renderer import OfficeRendererError, build_pptx_previews
from workbench.services.project_service import ProjectService

PIPELINE_VERSION = "materials-v1"


class MaterialProcessingError(ValueError):
    pass


class MaterialProcessingResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cached: bool
    cache_key: str
    pages: list[PageExtraction]
    matches: list[PageMatch]


class MaterialProcessingService:
    def __init__(self, projects: ProjectService, *, ocr: OcrEngine | None = None) -> None:
        self.projects = projects
        self.ocr = ocr

    def process(self, project_id: UUID, ocr_policy: OcrPolicy) -> MaterialProcessingResult:
        manifest = self.projects.get(project_id)
        project_dir = self.projects.workspace_root / manifest.project_dir
        outline_source, page_sources = _select_sources(manifest.source_files)
        cache_key = _cache_key(outline_source, page_sources, ocr_policy)
        if (
            manifest.material_cache_key == cache_key
            and manifest.page_extractions
            and manifest.matches
        ):
            return MaterialProcessingResult(
                cached=True,
                cache_key=cache_key,
                pages=_absolute_pages(manifest.page_extractions, project_dir),
                matches=manifest.matches,
            )

        outline_path = project_dir / outline_source.copied_path
        outline_target = project_dir / "03_文字识别" / "大纲结构.json"
        try:
            outline_artifact = write_outline_artifact(outline_path, outline_target)
            preview_dir = project_dir / "02_页面预览"
            pages = self._parse_pages(project_dir, page_sources, ocr_policy, preview_dir)
        except (
            DocumentParseError,
            EncryptedPdfError,
            PdfParseError,
            ImageParseError,
            PresentationParseError,
            OfficeRendererError,
            OcrUnavailableError,
        ) as error:
            raise MaterialProcessingError(str(error)) from error
        plan = match_outline_to_pages(outline_artifact.document, pages)
        persisted_pages = _relative_pages(pages, project_dir)
        persisted_matches = _relative_matches(plan.matches, project_dir)
        page_records = [
            PageRecord(
                id=page.id,
                order=page.order,
                title=page.title,
                status=(
                    NodeStatus.NEEDS_CONFIRMATION
                    if page.needs_confirmation
                    else NodeStatus.COMPLETED
                ),
            )
            for page in pages
        ]
        now = datetime.now(UTC)
        updated = manifest.model_copy(
            update={
                "pages": page_records,
                "page_extractions": persisted_pages,
                "matches": persisted_matches,
                "material_cache_key": cache_key,
                "outline_artifact_path": outline_target.relative_to(project_dir).as_posix(),
                "audit_log": [
                    *manifest.audit_log,
                    AuditEvent(
                        action="materials_parsed",
                        occurred_at=now,
                        details={"cache_key": cache_key, "page_count": len(pages)},
                    ),
                ],
            }
        )
        self.projects.save(updated)
        return MaterialProcessingResult(
            cached=False, cache_key=cache_key, pages=pages, matches=persisted_matches
        )

    def _parse_pages(
        self,
        project_dir: Path,
        sources: list[SourceFile],
        ocr_policy: OcrPolicy,
        preview_dir: Path,
    ) -> list[PageExtraction]:
        if all(source.kind is SourceKind.IMAGE for source in sources):
            ordered = sorted(sources, key=lambda source: source.image_order or 0)
            return parse_images(
                [project_dir / source.copied_path for source in ordered],
                [source.id for source in ordered],
                ocr_policy,
                ocr=self.ocr,
                preview_dir=preview_dir,
            )
        source = sources[0]
        path = project_dir / source.copied_path
        if source.kind is SourceKind.PPTX:
            return build_pptx_previews(path, preview_dir).pages
        if source.kind is SourceKind.PDF:
            return parse_pdf(
                path,
                ocr_policy,
                ocr=self.ocr,
                preview_dir=preview_dir,
            )
        raise MaterialProcessingError("不受支持的页面材料类型")


def _select_sources(sources: list[SourceFile]) -> tuple[SourceFile, list[SourceFile]]:
    outlines = [source for source in sources if source.kind is SourceKind.DOCX]
    page_sources = [source for source in sources if source.kind is not SourceKind.DOCX]
    if len(outlines) != 1:
        raise MaterialProcessingError("项目必须且只能包含一份 Word 大纲")
    deck_sources = [
        source for source in page_sources if source.kind in {SourceKind.PPTX, SourceKind.PDF}
    ]
    image_sources = [source for source in page_sources if source.kind is SourceKind.IMAGE]
    if not page_sources:
        raise MaterialProcessingError("项目缺少 PPTX、PDF 或图片课件")
    if len(deck_sources) > 1 or (deck_sources and image_sources):
        raise MaterialProcessingError("同一项目只能选择一份 PPTX/PDF 或一个图片批次")
    return outlines[0], image_sources if image_sources else deck_sources


def _cache_key(outline: SourceFile, pages: list[SourceFile], ocr_policy: OcrPolicy) -> str:
    ordered = sorted(pages, key=lambda source: source.image_order or 0)
    payload = {
        "version": PIPELINE_VERSION,
        "ocr_policy": ocr_policy.value,
        "outline": outline.sha256,
        "pages": [(source.sha256, source.image_order) for source in ordered],
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _relative_pages(pages: list[PageExtraction], project_dir: Path) -> list[PageExtraction]:
    return [
        page.model_copy(
            update={
                "preview_path": (
                    page.preview_path.relative_to(project_dir)
                    if page.preview_path is not None
                    else None
                )
            }
        )
        for page in pages
    ]


def _absolute_pages(pages: list[PageExtraction], project_dir: Path) -> list[PageExtraction]:
    return [
        page.model_copy(
            update={
                "preview_path": (
                    project_dir / page.preview_path if page.preview_path is not None else None
                )
            }
        )
        for page in pages
    ]


def _relative_matches(matches: list[PageMatch], project_dir: Path) -> list[PageMatch]:
    relative: list[PageMatch] = []
    for match in matches:
        preview = match.preview_path
        if preview:
            preview = Path(preview).relative_to(project_dir).as_posix()
        relative.append(match.model_copy(update={"preview_path": preview}))
    return relative
