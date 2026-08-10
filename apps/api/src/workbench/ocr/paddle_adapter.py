from __future__ import annotations

import importlib
import os
import tempfile
from collections.abc import Sequence
from pathlib import Path
from typing import Any, Protocol

from PIL import Image
from pydantic import BaseModel, ConfigDict, Field


class OcrUnavailableError(RuntimeError):
    pass


class OcrResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    bbox: tuple[float, float, float, float]
    confidence: float = Field(ge=0, le=1)


class OcrEngine(Protocol):
    def recognize(self, image: Image.Image) -> list[OcrResult]: ...


class PaddleOcrAdapter:
    def __init__(self, engine: Any | None = None) -> None:
        if engine is None:
            try:
                prepare_paddle_cache()
                paddle_module = importlib.import_module("paddleocr")
                engine = paddle_module.PaddleOCR(lang="ch", use_doc_orientation_classify=False)
            except Exception as error:
                raise OcrUnavailableError(
                    "PaddleOCR 中文运行时不可用，请在环境修复中安装 OCR 组件"
                ) from error
        self.engine = engine

    def recognize(self, image: Image.Image) -> list[OcrResult]:
        numpy = importlib.import_module("numpy")
        pixels = numpy.asarray(image.convert("RGB"))
        if hasattr(self.engine, "predict"):
            raw = self.engine.predict(pixels)
        else:
            raw = self.engine.ocr(pixels, cls=False)
        return _coerce_results(raw)


def prepare_paddle_cache(*, fallback_root: Path | None = None) -> Path:
    configured = os.environ.get("PADDLE_PDX_CACHE_HOME")
    if configured:
        selected = Path(configured)
    else:
        workbench_cache = os.environ.get("WORKBENCH_CACHE_DIR")
        if workbench_cache:
            root = Path(workbench_cache)
        elif fallback_root is not None:
            root = fallback_root
        elif os.name == "nt" and os.environ.get("LOCALAPPDATA"):
            root = Path(os.environ["LOCALAPPDATA"]) / "PPTVideoWorkbench" / "cache"
        elif os.environ.get("XDG_CACHE_HOME"):
            root = Path(os.environ["XDG_CACHE_HOME"]) / "ppt-video-workbench"
        else:
            root = Path(tempfile.gettempdir()) / "ppt-video-workbench-cache"
        selected = root / "paddlex"
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(selected)
    selected.mkdir(parents=True, exist_ok=True)
    return selected


def _coerce_results(raw: Any) -> list[OcrResult]:
    results: list[OcrResult] = []
    if raw is None:
        return results
    for page in raw if isinstance(raw, Sequence) and not isinstance(raw, (str, bytes)) else [raw]:
        payload = getattr(page, "json", page)
        if isinstance(payload, dict) and "res" in payload:
            payload = payload["res"]
        if isinstance(payload, dict) and "rec_texts" in payload:
            texts = payload.get("rec_texts", [])
            scores = payload.get("rec_scores", [])
            boxes = payload.get("rec_boxes", [])
            for text, score, box in zip(texts, scores, boxes, strict=False):
                x1, y1, x2, y2 = (float(value) for value in box)
                results.append(
                    OcrResult(text=str(text), bbox=(x1, y1, x2, y2), confidence=float(score))
                )
            continue
        lines = page if isinstance(page, list) else []
        for line in lines:
            if not isinstance(line, Sequence) or len(line) != 2:
                continue
            points, recognition = line
            text, confidence = recognition
            xs = [float(point[0]) for point in points]
            ys = [float(point[1]) for point in points]
            results.append(
                OcrResult(
                    text=str(text),
                    bbox=(min(xs), min(ys), max(xs), max(ys)),
                    confidence=float(confidence),
                )
            )
    return results
