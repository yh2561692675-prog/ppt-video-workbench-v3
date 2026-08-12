"""Local-only adapters for the reviewed, synthetic DG2 browser fixtures.

This module is not a production provider.  ``create_app`` installs it only
when ``WORKBENCH_E2E_SYNTHETIC_MODE=true`` is supplied by the Playwright
configuration.  The mode has no credentials, network calls or private media.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import wave
from collections.abc import Iterable
from pathlib import Path
from time import sleep

from workbench.audio.models import RecognizedSegment, RecognizedWord
from workbench.video.models import ProjectVideoProps, VideoPageProps

_DIGITS = "零一二三四五六七八九"


def synthetic_e2e_enabled() -> bool:
    return os.environ.get("WORKBENCH_E2E_SYNTHETIC_MODE", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class SyntheticTranscriptionBackend:
    """Return deterministic word timing for the generated 750ms/page WAVs."""

    requires_local_model = False

    def transcribe(
        self,
        audio: Path,
        **_: object,
    ) -> tuple[Iterable[RecognizedSegment], str]:
        with wave.open(str(audio), "rb") as handle:
            duration_ms = round(handle.getnframes() * 1_000 / handle.getframerate())
        page_count = max(1, duration_ms // 750)
        segments: list[RecognizedSegment] = []
        for order in range(1, page_count + 1):
            start_ms = (order - 1) * 750 + 50
            end_ms = min(order * 750 - 50, duration_ms)
            text = f"合成第{_chinese_number(order)}页旁白"
            word = RecognizedWord(
                text=text,
                start=start_ms / 1_000,
                end=end_ms / 1_000,
                probability=0.99,
            )
            segments.append(
                RecognizedSegment(
                    start=start_ms / 1_000,
                    end=end_ms / 1_000,
                    text=text,
                    words=[word],
                )
            )
        return segments, "zh"


class SyntheticVideoRenderer:
    """Use local FFmpeg to create a real H.264 page clip from each source image."""

    def __init__(self, ffmpeg: str | None = None) -> None:
        self.ffmpeg = ffmpeg or shutil.which("ffmpeg") or "ffmpeg"
        self.delay_seconds = _synthetic_render_delay_seconds()

    def render(
        self,
        _: ProjectVideoProps,
        page: VideoPageProps,
        source: Path,
        output: Path,
        control: object | None = None,
    ) -> None:
        del control
        output.parent.mkdir(parents=True, exist_ok=True)
        if self.delay_seconds:
            sleep(self.delay_seconds)
        completed = subprocess.run(
            [
                self.ffmpeg,
                "-y",
                "-loglevel",
                "error",
                "-loop",
                "1",
                "-i",
                str(source),
                "-t",
                f"{(page.end_ms - page.start_ms) / 1_000:.3f}",
                "-r",
                "30",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                str(output),
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
            raise RuntimeError("synthetic DG2 renderer failed to create an H.264 page clip")


def _chinese_number(value: int) -> str:
    if not 0 < value < len(_DIGITS):
        raise ValueError("DG2 synthetic transcription supports one to eight pages")
    return _DIGITS[value]


def _synthetic_render_delay_seconds() -> float:
    """Return an explicitly configured per-page delay for lifecycle E2E tests."""

    if not synthetic_e2e_enabled():
        return 0.0
    raw = os.environ.get("WORKBENCH_DG2_RENDER_DELAY_SECONDS", "0").strip()
    try:
        seconds = float(raw)
    except ValueError as error:
        raise ValueError("WORKBENCH_DG2_RENDER_DELAY_SECONDS must be numeric") from error
    if not 0 <= seconds <= 5:
        raise ValueError("WORKBENCH_DG2_RENDER_DELAY_SECONDS must be between zero and five")
    return seconds
