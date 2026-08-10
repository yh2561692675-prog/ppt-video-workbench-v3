from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

from docx import Document
from docx.table import Table
from docx.text.paragraph import Paragraph

from workbench.domain.outline import OutlineArtifact, OutlineBlock, OutlineDocument

HEADING_STYLE = re.compile(r"^(?:Heading|标题)\s*([1-9])$", re.IGNORECASE)


class DocumentParseError(ValueError):
    pass


def parse_docx(path: Path) -> OutlineDocument:
    try:
        document = Document(str(path))
    except Exception as error:
        raise DocumentParseError(f"无法解析 Word 文档：{path.name}") from error

    blocks: list[OutlineBlock] = []
    paragraph_number = 0
    table_number = 0
    for item in document.iter_inner_content():
        if isinstance(item, Paragraph):
            paragraph_number += 1
            text = item.text.strip()
            if not text:
                continue
            level = _heading_level(item)
            blocks.append(
                OutlineBlock(
                    kind="heading" if level is not None else "paragraph",
                    order=len(blocks) + 1,
                    level=level,
                    text=text,
                    source_ref=f"paragraph:{paragraph_number}",
                )
            )
        elif isinstance(item, Table):
            table_number += 1
            cells = [[cell.text.strip() for cell in row.cells] for row in item.rows]
            flattened: list[str] = []
            for value in (cell for row in cells for cell in row):
                if value and value not in flattened:
                    flattened.append(value)
            blocks.append(
                OutlineBlock(
                    kind="table",
                    order=len(blocks) + 1,
                    text=" | ".join(flattened),
                    table_cells=cells,
                    source_ref=f"table:{table_number}",
                )
            )
    return OutlineDocument(source_name=path.name, blocks=blocks)


def write_outline_artifact(source: Path, target: Path) -> OutlineArtifact:
    source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
    artifact = OutlineArtifact(
        source_sha256=source_hash,
        cache_key=f"docx-v1:{source_hash}",
        document=parse_docx(source),
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False, indent=2)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        Path(temporary).replace(target)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return artifact


def _heading_level(paragraph: Paragraph) -> int | None:
    style_name = paragraph.style.name if paragraph.style is not None else ""
    match = HEADING_STYLE.match(style_name)
    return int(match.group(1)) if match else None
