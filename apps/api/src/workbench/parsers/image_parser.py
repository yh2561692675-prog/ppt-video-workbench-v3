from __future__ import annotations

from pathlib import Path
from uuid import UUID, uuid5

from PIL import Image, ImageOps, ImageSequence, UnidentifiedImageError

from workbench.domain.extraction import PageExtraction
from workbench.ocr.paddle_adapter import OcrEngine, PaddleOcrAdapter
from workbench.parsers.pdf_parser import OcrPolicy, _ocr_spans

DEFAULT_MAX_IMAGE_PIXELS = 120_000_000


class ImageParseError(ValueError):
    pass


class ImagePixelLimitError(ImageParseError):
    pass


def parse_images(
    paths: list[Path],
    ordered_ids: list[UUID],
    ocr_policy: OcrPolicy,
    *,
    ocr: OcrEngine | None = None,
    preview_dir: Path | None = None,
    max_image_pixels: int = DEFAULT_MAX_IMAGE_PIXELS,
) -> list[PageExtraction]:
    if len(paths) != len(ordered_ids):
        raise ValueError("图片路径与顺序 ID 数量不一致")
    output = preview_dir or (paths[0].parent / "02_页面预览" if paths else Path("02_页面预览"))
    output.mkdir(parents=True, exist_ok=True)
    pages: list[PageExtraction] = []
    order = 0
    for path, source_id in zip(paths, ordered_ids, strict=True):
        try:
            source = Image.open(path)
        except (UnidentifiedImageError, OSError) as error:
            raise ImageParseError(f"无法解析图片：{path.name}") from error
        try:
            for frame_index, frame in enumerate(ImageSequence.Iterator(source), start=1):
                oriented = ImageOps.exif_transpose(frame.copy())
                if oriented.width * oriented.height > max_image_pixels:
                    raise ImagePixelLimitError(f"{path.name} 的像素总量超过安全限制")
                order += 1
                canvas = _safe_canvas(oriented)
                preview = output / f"image-{source_id}-{frame_index:04d}.png"
                canvas.save(preview, format="PNG")
                should_ocr = ocr_policy is not OcrPolicy.NEVER
                spans = []
                if should_ocr:
                    engine = ocr or PaddleOcrAdapter()
                    spans = _ocr_spans(engine.recognize(canvas))
                text = "\n".join(span.text for span in spans)
                pages.append(
                    PageExtraction(
                        id=uuid5(source_id, f"frame:{frame_index}"),
                        order=order,
                        text=text,
                        title=text.splitlines()[0] if text else None,
                        spans=spans,
                        preview_path=preview,
                        width=1920,
                        height=1080,
                        needs_confirmation=any(span.needs_confirmation for span in spans),
                        extraction_method="ocr" if should_ocr else "image",
                        source_ref=f"image:{source_id}:frame:{frame_index}",
                    )
                )
        finally:
            source.close()
    return pages


def _safe_canvas(image: Image.Image) -> Image.Image:
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGBA", rgba.size, "white")
        background.alpha_composite(rgba)
        image = background.convert("RGB")
    else:
        image = image.convert("RGB")
    fitted = ImageOps.contain(image, (1920, 1080), Image.Resampling.LANCZOS)
    canvas = Image.new("RGB", (1920, 1080), "white")
    canvas.paste(fitted, ((1920 - fitted.width) // 2, (1080 - fitted.height) // 2))
    return canvas
