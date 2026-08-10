from __future__ import annotations

import io
import re
from collections.abc import Callable
from pathlib import Path
from uuid import UUID

from docx import Document
from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.models import PageRecord
from workbench.services.project_service import ProjectService

# Legacy compatibility service retained for older callers; its user-facing
# messages intentionally remain on single lines.
# ruff: noqa: E501


class NarrationImportError(ValueError):
    pass


class NarrationImportAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: UUID
    page_order: int = Field(ge=1)
    page_title: str | None
    text: str
    method: str
    warning: str | None = None


class NarrationImportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str
    assignments: list[NarrationImportAssignment]


class NarrationImportService:
    def __init__(self, projects: ProjectService) -> None:
        self.projects = projects

    def preview(self, project_id: UUID, source_name: str, content: bytes) -> NarrationImportPreview:
        manifest = self.projects.get(project_id)
        pages = sorted(manifest.pages, key=lambda page: page.order)
        if not pages:
            raise NarrationImportError("请先完成材料解析与页面匹配后再导入旁白稿")
        paragraphs = _read_paragraphs(source_name, content)
        if not paragraphs:
            raise NarrationImportError("旁白稿没有可导入的正文")

        numbered = _extract_sections(paragraphs, pages, _numbered_page)
        if numbered is not None:
            return NarrationImportPreview(
                source_name=Path(source_name).name,
                assignments=_assign_sections(
                    pages, numbered, "page_number", "未找到该页的页码分段"
                ),
            )
        titled = _extract_sections(paragraphs, pages, _titled_page)
        if titled is not None:
            return NarrationImportPreview(
                source_name=Path(source_name).name,
                assignments=_assign_sections(pages, titled, "page_title", "未找到该页的标题分段"),
            )
        return NarrationImportPreview(
            source_name=Path(source_name).name,
            assignments=_assign_sequential(pages, paragraphs),
        )


def _read_paragraphs(source_name: str, content: bytes) -> list[str]:
    suffix = Path(source_name).suffix.casefold()
    if suffix == ".txt":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise NarrationImportError("TXT 旁白稿必须使用 UTF-8 编码") from error
        return _paragraphs_from_text(text)
    if suffix == ".docx":
        try:
            document = Document(io.BytesIO(content))
        except Exception as error:
            raise NarrationImportError("无法读取 Word 旁白稿") from error
        return [
            paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()
        ]
    raise NarrationImportError("旁白稿仅支持 .docx 和 UTF-8 .txt 文件")


def _paragraphs_from_text(text: str) -> list[str]:
    return [
        "\n".join(line.strip() for line in block.splitlines() if line.strip())
        for block in re.split(r"\r?\n\s*\r?\n", text)
        if block.strip()
    ]


def _numbered_page(line: str, pages: list[PageRecord]) -> tuple[UUID, str] | None:
    match = re.match(r"^\s*(?:第\s*)?(\d+)\s*(?:页|page|p)\b\s*[:：、.\-—]?\s*(.*)$", line, re.I)
    if match is None:
        return None
    page = next((item for item in pages if item.order == int(match.group(1))), None)
    return (page.id, match.group(2).strip()) if page is not None else None


def _titled_page(line: str, pages: list[PageRecord]) -> tuple[UUID, str] | None:
    normalized = _normalize_heading(line)
    matched = [
        item for item in pages if item.title and _normalize_heading(item.title) == normalized
    ]
    return (matched[0].id, "") if len(matched) == 1 else None


def _normalize_heading(value: str) -> str:
    return re.sub(r"[\s#:：、.\-—]+", "", value).casefold()


def _extract_sections(
    paragraphs: list[str],
    pages: list[PageRecord],
    marker: Callable[[str, list[PageRecord]], tuple[UUID, str] | None],
) -> dict[UUID, str] | None:
    sections: dict[UUID, list[str]] = {}
    current: UUID | None = None
    found = False
    for paragraph in paragraphs:
        lines = paragraph.splitlines()
        first = marker(lines[0], pages)
        if first is not None:
            current, remaining = first
            sections.setdefault(current, [])
            if remaining:
                sections[current].append(remaining)
            if len(lines) > 1:
                sections[current].append("\n".join(lines[1:]))
            found = True
        elif current is not None:
            sections[current].append(paragraph)
    if not found:
        return None
    return {page_id: "\n\n".join(blocks).strip() for page_id, blocks in sections.items()}


def _assign_sections(
    pages: list[PageRecord], sections: dict[UUID, str], method: str, missing_message: str
) -> list[NarrationImportAssignment]:
    return [
        NarrationImportAssignment(
            page_id=page.id,
            page_order=page.order,
            page_title=page.title,
            text=sections.get(page.id, ""),
            method=method,
            warning=None if sections.get(page.id, "") else missing_message,
        )
        for page in pages
    ]


def _assign_sequential(
    pages: list[PageRecord], paragraphs: list[str]
) -> list[NarrationImportAssignment]:
    groups: list[list[str]] = [[] for _ in pages]
    for index, paragraph in enumerate(paragraphs):
        groups[min(index * len(pages) // len(paragraphs), len(pages) - 1)].append(paragraph)
    return [
        NarrationImportAssignment(
            page_id=page.id,
            page_order=page.order,
            page_title=page.title,
            text="\n\n".join(groups[index]),
            method="sequential",
            warning=None if groups[index] else "连续文本不足，请补充本页旁白后写入",
        )
        for index, page in enumerate(pages)
    ]
