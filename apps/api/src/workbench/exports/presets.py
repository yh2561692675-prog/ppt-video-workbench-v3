from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

from workbench.services.project_service import ProjectService


class ExportPresetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ExportPreset(ExportPresetModel):
    id: str = Field(min_length=1, max_length=64)
    label: str = Field(min_length=1, max_length=120)
    platform: Literal["master", "youtube", "bilibili", "douyin", "instagram", "gif"]
    width: int = Field(gt=0, le=8_000)
    height: int = Field(gt=0, le=8_000)
    fps: Literal[24, 25, 30, 60]
    video_bitrate: str = Field(min_length=3, max_length=16)
    audio_bitrate: str = Field(min_length=3, max_length=16)
    container: Literal["mp4", "gif"]
    video_codec: Literal["libx264", "libx265", "gif"]
    max_segment_seconds: int | None = Field(default=None, ge=1, le=600)

    @property
    def aspect_ratio(self) -> str:
        divisor = _gcd(self.width, self.height)
        return f"{self.width // divisor}:{self.height // divisor}"


class ExportPlan(ExportPresetModel):
    schema_version: Literal["1.0"] = "1.0"
    plan_id: UUID = Field(default_factory=uuid4)
    project_id: UUID
    revision: int = Field(default=1, ge=1)
    created_at: str
    preset: ExportPreset
    source_timeline_revision: int | None = Field(default=None, ge=1)
    output_relative_path: str
    segment_paths: list[str] = Field(default_factory=list)
    ffmpeg_video_filter: str
    execution_ready: bool = True
    content_hash: str = Field(default="", pattern=r"^[0-9a-f]{64}$|^$")


class ExportPlanRequest(ExportPresetModel):
    preset_id: str = Field(min_length=1, max_length=64)
    source_timeline_revision: int | None = Field(default=None, ge=1)
    output_name: str | None = Field(default=None, max_length=120)


EXPORT_PRESETS: tuple[ExportPreset, ...] = (
    ExportPreset(
        id="master-1080p-30",
        label="主母版 1080p 30fps",
        platform="master",
        width=1920,
        height=1080,
        fps=30,
        video_bitrate="12M",
        audio_bitrate="192k",
        container="mp4",
        video_codec="libx264",
    ),
    ExportPreset(
        id="master-4k-30",
        label="主母版 4K 30fps",
        platform="master",
        width=3840,
        height=2160,
        fps=30,
        video_bitrate="35M",
        audio_bitrate="256k",
        container="mp4",
        video_codec="libx264",
    ),
    ExportPreset(
        id="youtube-1080p-60",
        label="YouTube 1080p 60fps",
        platform="youtube",
        width=1920,
        height=1080,
        fps=60,
        video_bitrate="16M",
        audio_bitrate="192k",
        container="mp4",
        video_codec="libx264",
    ),
    ExportPreset(
        id="bilibili-vertical-1080p-30",
        label="Bilibili 竖屏 1080p",
        platform="bilibili",
        width=1080,
        height=1920,
        fps=30,
        video_bitrate="10M",
        audio_bitrate="192k",
        container="mp4",
        video_codec="libx264",
    ),
    ExportPreset(
        id="douyin-square-1080p-30",
        label="抖音方屏 1080p",
        platform="douyin",
        width=1080,
        height=1080,
        fps=30,
        video_bitrate="10M",
        audio_bitrate="160k",
        container="mp4",
        video_codec="libx264",
        max_segment_seconds=60,
    ),
    ExportPreset(
        id="instagram-reel-1080p-30",
        label="Instagram Reel 竖屏",
        platform="instagram",
        width=1080,
        height=1920,
        fps=30,
        video_bitrate="10M",
        audio_bitrate="160k",
        container="mp4",
        video_codec="libx264",
        max_segment_seconds=90,
    ),
    ExportPreset(
        id="gif-720p-24",
        label="GIF 720p 24fps",
        platform="gif",
        width=720,
        height=720,
        fps=24,
        video_bitrate="0kb",
        audio_bitrate="0kb",
        container="gif",
        video_codec="gif",
        max_segment_seconds=15,
    ),
)


class ExportPresetService:
    def __init__(
        self,
        workspace_root: Path,
        project_dir_resolver: Callable[[UUID], str],
        projects: ProjectService | None = None,
    ) -> None:
        self.workspace_root = workspace_root
        self.project_dir_resolver = project_dir_resolver
        self.projects = projects
        self._plans: dict[UUID, list[ExportPlan]] = {}

    def presets(self) -> list[ExportPreset]:
        return list(EXPORT_PRESETS)

    def create_plan(
        self, project_id: UUID, request: ExportPlanRequest, *, duration_ms: int = 0
    ) -> ExportPlan:
        preset = next((item for item in EXPORT_PRESETS if item.id == request.preset_id), None)
        if preset is None:
            raise ValueError(f"unknown export preset: {request.preset_id}")
        if duration_ms <= 0 and self.projects is not None:
            project = self.projects.get(project_id)
            duration_ms = max(
                (page.timeline.end_ms for page in project.pages if page.timeline is not None),
                default=project.audio_timeline.duration_ms if project.audio_timeline else 0,
            )
        base_name = _safe_name(request.output_name or preset.id)
        extension = "gif" if preset.container == "gif" else "mp4"
        output = f"08_输出/{base_name}.{extension}"
        segments: list[str] = []
        if (
            preset.max_segment_seconds is not None
            and duration_ms > preset.max_segment_seconds * 1_000
        ):
            segment_count = (duration_ms + preset.max_segment_seconds * 1_000 - 1) // (
                preset.max_segment_seconds * 1_000
            )
            segments = [
                f"08_输出/{base_name}-part-{index:02d}.{extension}"
                for index in range(1, segment_count + 1)
            ]
        plan = ExportPlan(
            project_id=project_id,
            revision=len(self._plans.get(project_id, [])) + 1,
            created_at=datetime.now(UTC).isoformat(),
            preset=preset,
            source_timeline_revision=request.source_timeline_revision,
            output_relative_path=output,
            segment_paths=segments,
            ffmpeg_video_filter=f"scale={preset.width}:{preset.height}:flags=lanczos,fps={preset.fps}",
        )
        plan = _with_hash(plan)
        self._plans.setdefault(project_id, []).append(plan)
        self._persist(project_id, plan)
        return plan

    def plans(self, project_id: UUID) -> list[ExportPlan]:
        cached = self._plans.get(project_id)
        if cached:
            return cached
        folder = self._folder(project_id)
        loaded = [
            ExportPlan.model_validate_json(path.read_text(encoding="utf-8"))
            for path in sorted(folder.glob("plan-*.json"), key=lambda item: item.name)
        ]
        self._plans[project_id] = loaded
        return loaded

    def _folder(self, project_id: UUID) -> Path:
        root = (self.workspace_root / self.project_dir_resolver(project_id)).resolve()
        workspace = self.workspace_root.resolve()
        if root != workspace and workspace not in root.parents:
            raise ValueError("project path escapes workspace root")
        folder = root / "08_输出" / "export-plans"
        folder.mkdir(parents=True, exist_ok=True)
        return folder

    def _persist(self, project_id: UUID, plan: ExportPlan) -> None:
        content = (plan.model_dump_json(indent=2) + "\n").encode("utf-8")
        _atomic_write(self._folder(project_id) / f"plan-{plan.revision:08d}.json", content)


def _with_hash(plan: ExportPlan) -> ExportPlan:
    payload = plan.model_dump(mode="json", exclude={"content_hash"})
    digest = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
            "utf-8"
        )
    ).hexdigest()
    return plan.model_copy(update={"content_hash": digest})


def _safe_name(value: str) -> str:
    normalized = "".join(char if char.isalnum() or char in "-_" else "_" for char in value).strip(
        "._"
    )
    if not normalized:
        raise ValueError("output name is empty")
    return normalized[:100]


def _gcd(left: int, right: int) -> int:
    while right:
        left, right = right, left % right
    return max(left, 1)


def _atomic_write(path: Path, content: bytes) -> None:
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(content)
    os.replace(temporary, path)
