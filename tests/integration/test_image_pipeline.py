from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from workbench.ocr.paddle_adapter import OcrResult
from workbench.parsers.image_parser import ImagePixelLimitError, parse_images
from workbench.parsers.pdf_parser import OcrPolicy


class FixedOcr:
    def recognize(self, _: Image.Image) -> list[OcrResult]:
        return [OcrResult(text="图片文字", bbox=(80, 90, 300, 140), confidence=0.79)]


def save_image(path: Path, format_name: str, *, mode: str = "RGB") -> None:
    if mode == "RGBA":
        image = Image.new(mode, (320, 180), (0, 0, 0, 0))
        image.paste((20, 80, 140, 255), (80, 45, 240, 135))
    else:
        image = Image.new(mode, (320, 180), (20, 80, 140))
    image.save(path, format=format_name)


@pytest.mark.parametrize(
    ("suffix", "format_name"),
    [(".jpg", "JPEG"), (".png", "PNG"), (".webp", "WEBP"), (".bmp", "BMP")],
)
def test_common_images_fit_safe_canvas_without_crop(
    tmp_path: Path, suffix: str, format_name: str
) -> None:
    path = tmp_path / f"page{suffix}"
    save_image(path, format_name)

    page = parse_images([path], [uuid4()], OcrPolicy.NEVER, preview_dir=tmp_path / "预览")[0]

    with Image.open(page.preview_path) as preview:
        assert preview.size == (1920, 1080)
        assert preview.mode == "RGB"
        pixel = preview.getpixel((960, 540))
        assert all(
            abs(actual - expected) <= 3
            for actual, expected in zip(pixel, (20, 80, 140), strict=True)
        )
        assert preview.getbbox() is not None


def test_multipage_tiff_exif_rotation_transparency_and_ocr_flags(tmp_path: Path) -> None:
    tiff = tmp_path / "多页.tiff"
    frames = [Image.new("RGB", (200, 300), "red"), Image.new("RGB", (300, 200), "blue")]
    frames[0].save(tiff, save_all=True, append_images=frames[1:])
    transparent = tmp_path / "透明.png"
    save_image(transparent, "PNG", mode="RGBA")
    rotated = tmp_path / "旋转.jpg"
    image = Image.new("RGB", (100, 200), "green")
    exif = image.getexif()
    exif[274] = 6
    image.save(rotated, exif=exif)

    pages = parse_images(
        [tiff, transparent, rotated],
        [uuid4(), uuid4(), uuid4()],
        OcrPolicy.ALWAYS,
        ocr=FixedOcr(),
        preview_dir=tmp_path / "预览",
    )

    assert len(pages) == 4
    assert [page.order for page in pages] == [1, 2, 3, 4]
    assert all(page.needs_confirmation for page in pages)
    with Image.open(pages[2].preview_path) as preview:
        assert preview.mode == "RGB"
        assert preview.getpixel((0, 0)) == (255, 255, 255)


def test_image_pixel_bomb_is_rejected_before_render(tmp_path: Path) -> None:
    path = tmp_path / "too-large.png"
    save_image(path, "PNG")

    with pytest.raises(ImagePixelLimitError, match="像素"):
        parse_images(
            [path],
            [uuid4()],
            OcrPolicy.NEVER,
            preview_dir=tmp_path / "预览",
            max_image_pixels=100,
        )
