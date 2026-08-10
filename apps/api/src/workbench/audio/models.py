from __future__ import annotations

import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


@dataclass(frozen=True)
class RecognizedWord:
    text: str
    start: float
    end: float
    probability: float


@dataclass(frozen=True)
class RecognizedSegment:
    start: float
    end: float
    text: str
    words: list[RecognizedWord] = field(default_factory=list)


class TranscriptModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TranscriptWord(TranscriptModel):
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    confidence: float = Field(ge=0, le=1)


class TranscriptSegment(TranscriptModel):
    text: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(ge=0)
    words: list[TranscriptWord] = Field(default_factory=list)


class Transcript(TranscriptModel):
    segments: list[TranscriptSegment] = Field(default_factory=list)
    words: list[TranscriptWord] = Field(default_factory=list)
    detected_language: str
    model: str
    device: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class WhisperModelManager:
    def __init__(self, root: Path) -> None:
        self.root = root

    def model_path(self, name: str) -> Path:
        return self.root / name

    def download_path(self, name: str) -> Path:
        return self.model_path(name) / "model.bin.part"

    def is_available(self, name: str) -> bool:
        return (self.model_path(name) / "model.bin").is_file()

    def download(
        self,
        name: str,
        *,
        total_bytes: int,
        chunks: Callable[[int], Iterable[bytes]],
        progress: Callable[[int, int], None],
    ) -> Path:
        part = self.download_path(name)
        part.parent.mkdir(parents=True, exist_ok=True)
        offset = part.stat().st_size if part.exists() else 0
        if offset > total_bytes:
            part.unlink()
            offset = 0
        with part.open("ab") as handle:
            for chunk in chunks(offset):
                handle.write(chunk)
                offset += len(chunk)
                progress(offset, total_bytes)
                if offset > total_bytes:
                    raise ValueError("模型下载数据超过声明大小")
            handle.flush()
            os.fsync(handle.fileno())
        if offset != total_bytes:
            raise ValueError("模型下载尚未完成")
        installed = self.model_path(name) / "model.bin"
        os.replace(part, installed)
        return installed
