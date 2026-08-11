from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from PIL import Image, ImageOps, UnidentifiedImageError

from workbench.assets.derivative_models import DerivativeOperation, DerivativeRequestV1
from workbench.assets.object_store import ContentAddressedObjectStore, StoredObject


class ImageDerivativeError(ValueError):
    pass


class ImageDerivativeExecutor:
    def __init__(self, object_store: ContentAddressedObjectStore, work_root: Path) -> None:
        self.object_store = object_store
        self.work_root = work_root

    def execute(self, request: DerivativeRequestV1, source: Path) -> StoredObject:
        if request.operation not in {
            DerivativeOperation.CROP,
            DerivativeOperation.THUMBNAIL,
            DerivativeOperation.TRANSCODE,
        }:
            raise ImageDerivativeError(f"unsupported image operation: {request.operation.value}")
        self.work_root.mkdir(parents=True, exist_ok=True)
        try:
            with Image.open(source) as opened:
                image = ImageOps.exif_transpose(opened)
                rendered = self._apply(request, image)
                output_format = _output_format(request.parameters, opened.format)
                suffix = _suffix(output_format)
                with TemporaryDirectory(
                    prefix="image-derivative-", dir=self.work_root
                ) as temporary:
                    output = Path(temporary) / f"output{suffix}"
                    if output_format == "JPEG" and rendered.mode not in {"RGB", "L"}:
                        background = Image.new("RGB", rendered.size, "white")
                        if rendered.mode == "RGBA":
                            background.paste(rendered, mask=rendered.getchannel("A"))
                        else:
                            background.paste(rendered.convert("RGB"))
                        rendered = background
                    rendered.save(output, format=output_format, optimize=True)
                    return self.object_store.ingest_file(output, suffix=suffix)
        except (OSError, UnidentifiedImageError) as error:
            raise ImageDerivativeError("image source cannot be decoded") from error

    def _apply(self, request: DerivativeRequestV1, image: Image.Image) -> Image.Image:
        if request.operation is DerivativeOperation.CROP:
            _require_only(request.parameters, {"x", "y", "width", "height", "format"})
            x = _integer(request.parameters, "x", minimum=0)
            y = _integer(request.parameters, "y", minimum=0)
            width = _integer(request.parameters, "width", minimum=1)
            height = _integer(request.parameters, "height", minimum=1)
            if x + width > image.width or y + height > image.height:
                raise ImageDerivativeError("crop rectangle exceeds image bounds")
            return image.crop((x, y, x + width, y + height))
        if request.operation is DerivativeOperation.THUMBNAIL:
            _require_only(request.parameters, {"width", "height", "format"})
            width = _integer(request.parameters, "width", minimum=1)
            height = _integer(request.parameters, "height", minimum=1)
            result = image.copy()
            result.thumbnail((width, height), Image.Resampling.LANCZOS)
            return result
        _require_only(request.parameters, {"format"})
        return image.copy()


def _require_only(parameters: dict[str, Any], allowed: set[str]) -> None:
    unknown = sorted(set(parameters) - allowed)
    if unknown:
        raise ImageDerivativeError(f"unsupported image parameters: {', '.join(unknown)}")


def _integer(parameters: dict[str, Any], key: str, *, minimum: int) -> int:
    try:
        value = int(parameters[key])
    except (KeyError, TypeError, ValueError) as error:
        raise ImageDerivativeError(f"image parameter {key} must be an integer") from error
    if value < minimum:
        raise ImageDerivativeError(f"image parameter {key} is out of range")
    return value


def _output_format(parameters: dict[str, Any], source_format: str | None) -> str:
    selected = str(parameters.get("format", source_format or "PNG")).upper()
    selected = {"JPG": "JPEG"}.get(selected, selected)
    if selected not in {"PNG", "JPEG", "WEBP"}:
        raise ImageDerivativeError("image output format must be PNG, JPEG or WEBP")
    return selected


def _suffix(output_format: str) -> str:
    return {"PNG": ".png", "JPEG": ".jpg", "WEBP": ".webp"}[output_format]
