from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def ensure_route(
    requested: Literal["local", "heygen"], existing: Literal["local", "heygen", "none"]
) -> None:
    if existing != "none" and existing != requested:
        raise ValueError("AUDIO_ROUTE_CONFLICT: local and HeyGen routes cannot be mixed")


def synthesis_cache_key(revision_id: UUID, voice_id: str, speed: float) -> str:
    return hashlib.sha256(f"{revision_id}|{voice_id}|{speed:.3f}|zh".encode()).hexdigest()


class PaidRequestRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: UUID
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    request_id: str = Field(min_length=1)
    audio_url: str = Field(min_length=1)


class PaidRequestCheckpoint:
    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> dict[UUID, PaidRequestRecord]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if payload.get("schema_version") != 1:
            return {}
        records: dict[UUID, PaidRequestRecord] = {}
        for item in payload.get("requests", []):
            try:
                record = PaidRequestRecord.model_validate(item)
            except ValueError:
                continue
            records[record.page_id] = record
        return records

    def save(self, records: dict[UUID, PaidRequestRecord]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        serialized = {
            "schema_version": 1,
            "requests": [
                item.model_dump(mode="json")
                for _, item in sorted(records.items(), key=lambda pair: str(pair[0]))
            ],
        }
        with temporary.open("w", encoding="utf-8", newline="\n") as handle:
            json.dump(serialized, handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)
