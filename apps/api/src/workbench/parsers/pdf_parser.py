from __future__ import annotations

import hashlib
from enum import StrEnum
from pathlib import Path
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import fitz  # type: ignore[import-untyped]
from PIL import Image

from workbench.domain.extraction import PageExtraction, TextSpan
from workbench.ocr.paddle_adapter import OcrEngine, OcrResult, PaddleOcrAdapter


class OcrPolicy(StrEnum):
    NEVER = "never"
    AUTO = "auto"
    ALWAYS = "always"


class EncryptedPdfError(ValueError):
    pass


class PdfParseError(ValueError):
    pass


def parse_pdf(
    path: Path,
    ocr_policy: OcrPolicy,
    *,
    ocr: OcrEngine | None = None,
    preview_dir: Path | None = None,
) -> list[PageExtraction]:
    try:
        document = fitz.open(path)
    except Exception as error:
        raise PdfParseError(f"无法解析 PDF：{path.name}") from error
    if document.needs_pass:
        document.close()
        raise EncryptedPdfError("PDF 已加密，请先解除密码保护")
    output = preview_dir or path.parent / "02_页面预览"
    output.mkdir(parents=True, exist_ok=True)
    source_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    pages: list[PageExtraction] = []
    try:
        for order, page in enumerate(document, start=1):
            image, scale, offset = _render_pdf_page(page)
            preview = output / f"pdf-{source_hash[:12]}-{order:04d}.png"
            image.save(preview, format="PNG")
            pdf_spans = _extract_pdf_spans(page, scale, offset)
            pdf_text = "\n".join(span.text for span in pdf_spans)
            should_ocr = ocr_policy is OcrPolicy.ALWAYS or (
                ocr_policy is OcrPolicy.AUTO and len("".join(pdf_text.split())) < 20
            )
            ocr_results: list[OcrResult] = []
            if should_ocr:
                engine = ocr or PaddleOcrAdapter()
                ocr_results = engine.recognize(image)
            spans = [*pdf_spans, *_ocr_spans(ocr_results)] if should_ocr else pdf_spans
            text = "\n".join(span.text for span in spans)
            pages.append(
                PageExtraction(
                    id=uuid5(NAMESPACE_URL, f"pdf:{source_hash}:{order}"),
                    order=order,
                    text=text,
                    title=text.splitlines()[0] if text else None,
                    spans=spans,
                    preview_path=preview,
                    width=1920,
                    height=1080,
                    rotation=page.rotation,
                    needs_confirmation=any(span.needs_confirmation for span in spans),
                    extraction_method="ocr" if should_ocr else "pdf_text",
                    source_ref=f"pdf-page:{order}",
                )
            )
    finally:
        document.close()
    return pages


def _render_pdf_page(page: Any) -> tuple[Image.Image, float, tuple[int, int]]:
    scale = min(1920 / page.rect.width, 1080 / page.rect.height)
    pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
    rendered = pixmap.pil_image().convert("RGB")
    canvas = Image.new("RGB", (1920, 1080), "white")
    offset = ((1920 - rendered.width) // 2, (1080 - rendered.height) // 2)
    canvas.paste(rendered, offset)
    return canvas, scale, offset


def _extract_pdf_spans(page: Any, scale: float, offset: tuple[int, int]) -> list[TextSpan]:
    spans: list[TextSpan] = []
    data = page.get_text("dict")
    for block in data.get("blocks", []):
        for line in block.get("lines", []):
            for raw in line.get("spans", []):
                text = str(raw.get("text", "")).strip()
                if not text:
                    continue
                x1, y1, x2, y2 = (float(value) for value in raw["bbox"])
                spans.append(
                    TextSpan(
                        text=text,
                        bbox=(
                            x1 * scale + offset[0],
                            y1 * scale + offset[1],
                            x2 * scale + offset[0],
                            y2 * scale + offset[1],
                        ),
                        confidence=1.0,
                    )
                )
    return spans


def _ocr_spans(results: list[OcrResult]) -> list[TextSpan]:
    return [
        TextSpan(
            text=result.text,
            bbox=result.bbox,
            confidence=result.confidence,
            needs_confirmation=result.confidence < 0.80,
        )
        for result in results
    ]
