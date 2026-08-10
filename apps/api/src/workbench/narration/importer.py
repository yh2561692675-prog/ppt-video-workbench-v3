from __future__ import annotations

import io
import re
from collections.abc import Sequence
from typing import Literal

from docx import Document
from pydantic import BaseModel, ConfigDict, Field

from workbench.domain.models import PageRecord

ImportMethod = Literal["page_number", "page_title", "sequential"]

_PAGE_HEADING = re.compile(
    r"^第\s*(?P<order>\d+)\s*页(?:\s*[-—:：.]?\s*(?P<inline>.*))?$",
    re.MULTILINE,
)


class NarrationImportError(ValueError):
    pass


class NarrationImportAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str
    page_order: int = Field(ge=1)
    page_title: str | None
    text: str = Field(min_length=1)
    method: ImportMethod
    warning: str | None = None


class NarrationImportPreview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_name: str = Field(min_length=1, max_length=255)
    assignments: list[NarrationImportAssignment]


def preview_import(
    filename: str,
    content: bytes,
    pages: Sequence[PageRecord],
) -> NarrationImportPreview:
    ordered_pages = sorted(pages, key=lambda page: page.order)
    if not ordered_pages:
        raise NarrationImportError("请先完成页面解析，再导入旁白稿")
    text = _read_text(filename, content)
    numbered = _by_page_number(text, ordered_pages)
    if numbered is not None:
        return NarrationImportPreview(source_name=filename, assignments=numbered)
    titled = _by_page_title(text, ordered_pages)
    if titled is not None:
        return NarrationImportPreview(source_name=filename, assignments=titled)
    return NarrationImportPreview(
        source_name=filename,
        assignments=[
            NarrationImportAssignment(
                page_id=str(page.id),
                page_order=page.order,
                page_title=page.title,
                text=segment,
                method="sequential",
                warning="未识别页码或页标题，已按页面顺序均衡分配，请逐页核对。",
            )
            for page, segment in zip(
                ordered_pages,
                _balanced_segments(text, len(ordered_pages)),
                strict=True,
            )
        ],
    )


def _read_text(filename: str, content: bytes) -> str:
    suffix = filename.rsplit(".", maxsplit=1)[-1].lower() if "." in filename else ""
    if suffix == "txt":
        try:
            text = content.decode("utf-8-sig")
        except UnicodeDecodeError as error:
            raise NarrationImportError("TXT 旁白稿必须使用 UTF-8 编码") from error
    elif suffix == "docx":
        try:
            document = Document(io.BytesIO(content))
        except Exception as error:
            raise NarrationImportError(f"无法解析 Word 旁白稿：{filename}") from error
        text = "\n".join(
            paragraph.text.strip() for paragraph in document.paragraphs if paragraph.text.strip()
        )
    else:
        raise NarrationImportError("仅支持 .docx 或 UTF-8 .txt 旁白稿")
    clean = text.strip()
    if not clean:
        raise NarrationImportError("旁白稿不包含可导入的正文")
    return clean


def _by_page_number(
    text: str, pages: Sequence[PageRecord]
) -> list[NarrationImportAssignment] | None:
    matches = list(_PAGE_HEADING.finditer(text))
    if not matches:
        return None
    parts: dict[int, str] = {}
    for index, match in enumerate(matches):
        order = int(match.group("order"))
        if order in parts:
            raise NarrationImportError(f"第 {order} 页在旁白稿中出现重复页码标题")
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        inline_text = match.group("inline") or ""
        following_text = text[match.end() : next_start]
        body = "\n".join(value for value in [inline_text, following_text] if value).strip()
        parts[order] = body
    expected = {page.order for page in pages}
    provided = set(parts)
    if provided != expected:
        missing = sorted(expected - provided)
        unexpected = sorted(provided - expected)
        details = []
        if missing:
            missing_labels = "、".join(map(str, missing))
            details.append(f"缺少第 {missing_labels} 页")
        if unexpected:
            unexpected_labels = "、".join(map(str, unexpected))
            details.append(f"包含不存在的第 {unexpected_labels} 页")
        raise NarrationImportError("页码匹配不完整：" + "；".join(details))
    return [
        NarrationImportAssignment(
            page_id=str(page.id),
            page_order=page.order,
            page_title=page.title,
            text=_require_text(parts[page.order], page.order),
            method="page_number",
        )
        for page in pages
    ]


def _by_page_title(
    text: str, pages: Sequence[PageRecord]
) -> list[NarrationImportAssignment] | None:
    if any(not page.title for page in pages):
        return None
    lines = text.splitlines()
    title_indexes: dict[int, int] = {}
    for page in pages:
        matches = [index for index, line in enumerate(lines) if line.strip() == page.title]
        if len(matches) != 1:
            return None
        title_indexes[page.order] = matches[0]
    if list(title_indexes.values()) != sorted(title_indexes.values()):
        return None
    assignments: list[NarrationImportAssignment] = []
    for index, page in enumerate(pages):
        start = title_indexes[page.order] + 1
        end = title_indexes[pages[index + 1].order] if index + 1 < len(pages) else len(lines)
        assignments.append(
            NarrationImportAssignment(
                page_id=str(page.id),
                page_order=page.order,
                page_title=page.title,
                text=_require_text("\n".join(lines[start:end]).strip(), page.order),
                method="page_title",
            )
        )
    return assignments


def _balanced_segments(text: str, count: int) -> list[str]:
    if len(text.strip()) < count:
        raise NarrationImportError("旁白稿内容不足，无法为每一页分配正文")
    boundaries = [match.end() for match in re.finditer(r"[。！？!?](?:\s|$)", text)]
    segments: list[str] = []
    cursor = 0
    for position in range(1, count):
        target = round(len(text) * position / count)
        candidates = [boundary for boundary in boundaries if boundary > cursor]
        boundary = min(candidates, key=lambda value: abs(value - target)) if candidates else target
        if boundary <= cursor:
            boundary = target
        segments.append(_require_text(text[cursor:boundary].strip(), position))
        cursor = boundary
    segments.append(_require_text(text[cursor:].strip(), count))
    return segments


def _require_text(text: str, order: int) -> str:
    if not text:
        raise NarrationImportError(f"第 {order} 页未识别到旁白正文")
    return text
