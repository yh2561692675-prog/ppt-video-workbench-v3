from __future__ import annotations

from pathlib import Path

import fitz
import pytest
from PIL import Image
from workbench.ocr.paddle_adapter import OcrResult
from workbench.parsers.pdf_parser import EncryptedPdfError, OcrPolicy, parse_pdf


class FixedOcr:
    def __init__(self, confidence: float = 0.95) -> None:
        self.confidence = confidence

    def recognize(self, _: Image.Image) -> list[OcrResult]:
        return [OcrResult(text="扫描文字", bbox=(100, 120, 400, 180), confidence=self.confidence)]


def make_pdf(path: Path, *, text_pages: list[str], rotation: int = 0) -> None:
    document = fitz.open()
    for text in text_pages:
        page = document.new_page(width=960, height=540)
        if text:
            page.insert_text((72, 72), text)
        else:
            pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 200, 100), False)
            pixmap.clear_with(230)
            page.insert_image(fitz.Rect(100, 100, 300, 200), pixmap=pixmap)
        if rotation:
            page.set_rotation(rotation)
    document.save(path)
    document.close()


def test_searchable_mixed_and_scanned_pdf_choose_text_or_ocr_per_page(tmp_path: Path) -> None:
    path = tmp_path / "混合.pdf"
    make_pdf(path, text_pages=["Searchable page content", ""])

    pages = parse_pdf(path, OcrPolicy.AUTO, ocr=FixedOcr(), preview_dir=tmp_path / "预览")

    assert [page.order for page in pages] == [1, 2]
    assert pages[0].extraction_method == "pdf_text"
    assert "Searchable page content" in pages[0].text
    assert pages[1].extraction_method == "ocr"
    assert pages[1].spans[0].bbox == (100.0, 120.0, 400.0, 180.0)
    assert all((page.width, page.height) == (1920, 1080) for page in pages)


def test_low_confidence_ocr_and_rotated_page_are_locatable(tmp_path: Path) -> None:
    path = tmp_path / "扫描.pdf"
    make_pdf(path, text_pages=[""], rotation=90)

    page = parse_pdf(path, OcrPolicy.ALWAYS, ocr=FixedOcr(0.79), preview_dir=tmp_path / "预览")[0]

    assert page.rotation == 90
    assert page.needs_confirmation is True
    assert page.spans[0].needs_confirmation is True
    assert page.spans[0].confidence == 0.79


def test_encrypted_pdf_is_a_blocking_error(tmp_path: Path) -> None:
    source = fitz.open()
    source.new_page()
    path = tmp_path / "加密.pdf"
    source.save(
        path,
        encryption=fitz.PDF_ENCRYPT_AES_256,
        owner_pw="owner",
        user_pw="reader",
    )
    source.close()

    with pytest.raises(EncryptedPdfError, match="加密"):
        parse_pdf(path, OcrPolicy.NEVER, preview_dir=tmp_path / "预览")


def test_auto_ocr_preserves_existing_short_pdf_text_on_same_page(tmp_path: Path) -> None:
    path = tmp_path / "同页混合.pdf"
    make_pdf(path, text_pages=["Label"])

    page = parse_pdf(path, OcrPolicy.AUTO, ocr=FixedOcr(), preview_dir=tmp_path / "预览")[0]

    assert "Label" in page.text
    assert "扫描文字" in page.text
