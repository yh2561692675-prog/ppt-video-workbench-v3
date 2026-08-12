"""Admission control for executable V1 export profiles.

The preset catalogue is also used by batch planning, where a preset can be a
future delivery target.  This module is stricter: it only admits a profile
when the current V1 renderer, muxer, and package validator can all consume it.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from workbench.video.models import STANDARD_VIDEO_CANVASES, STANDARD_VIDEO_FPS, ProjectVideoProps

if TYPE_CHECKING:
    from .presets import ExportPreset


class ExportProfileBlocked(ValueError):
    """A requested output is known but not admissible for a queued V1 job."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ExportProfileCapabilities:
    """Feature and runtime capability claims supplied by the local launcher.

    4K is intentionally fail-closed.  The launcher must set both flags only
    after it has confirmed the selected hardware/encoder path; a mere catalog
    entry is not evidence that the machine can produce a 4K delivery.
    """

    four_k_feature_enabled: bool = False
    four_k_hardware_ready: bool = False

    @classmethod
    def from_environment(
        cls, env: Mapping[str, str | None] | None = None
    ) -> ExportProfileCapabilities:
        values = os.environ if env is None else env
        return cls(
            four_k_feature_enabled=_enabled(values.get("WORKBENCH_EXPORT_4K_ENABLED")),
            four_k_hardware_ready=_enabled(values.get("WORKBENCH_EXPORT_4K_HARDWARE_READY")),
        )


def resolve_export_profile(
    props: ProjectVideoProps,
    preset: ExportPreset,
    *,
    capabilities: ExportProfileCapabilities | None = None,
) -> ProjectVideoProps:
    """Return immutable props for an admitted delivery profile or fail early."""

    effective = capabilities or ExportProfileCapabilities.from_environment()
    if preset.container != "mp4" or preset.video_codec not in {"libx264", "libx265"}:
        raise ExportProfileBlocked(
            "export_container_not_supported",
            "this renderer only queues MP4 delivery profiles; GIF is planned but not executable",
        )
    if (preset.width, preset.height) not in STANDARD_VIDEO_CANVASES:
        raise ExportProfileBlocked(
            "export_canvas_not_supported",
            "the requested export canvas is not qualified for the V1 renderer",
        )
    if preset.fps not in STANDARD_VIDEO_FPS:
        raise ExportProfileBlocked(
            "export_fps_not_supported",
            "the requested frame rate is not qualified for the V1 renderer",
        )
    if (preset.width, preset.height) == (3840, 2160) and not (
        effective.four_k_feature_enabled and effective.four_k_hardware_ready
    ):
        raise ExportProfileBlocked(
            "export_4k_not_available",
            "4K requires both the 4K feature flag and a launcher-confirmed hardware capability",
        )
    return props.model_copy(
        update={"width": preset.width, "height": preset.height, "fps": preset.fps}
    )


def _enabled(value: str | None) -> bool:
    return value is not None and value.strip().lower() in {"1", "true", "yes", "on"}
