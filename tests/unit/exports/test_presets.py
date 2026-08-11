from __future__ import annotations

from uuid import uuid4

import pytest
from workbench.exports.presets import ExportPlanRequest, ExportPresetService


def test_preset_catalog_contains_multi_orientation_and_segment_options(tmp_path):
    service = ExportPresetService(tmp_path, project_dir_resolver=lambda _: "project")
    presets = service.presets()
    assert {preset.aspect_ratio for preset in presets} >= {"16:9", "9:16", "1:1"}
    assert any(preset.max_segment_seconds for preset in presets)


def test_create_export_plan_is_safe_and_reproducible(tmp_path):
    project_id = uuid4()
    service = ExportPresetService(tmp_path, project_dir_resolver=lambda _: "project")
    plan = service.create_plan(
        project_id,
        ExportPlanRequest(preset_id="douyin-square-1080p-30", output_name="课程/第1章"),
        duration_ms=125_000,
    )
    assert plan.output_relative_path == "08_输出/课程_第1章.mp4"
    assert len(plan.segment_paths) == 3
    assert plan.ffmpeg_video_filter == "scale=1080:1080:flags=lanczos,fps=30"
    assert len(plan.content_hash) == 64
    assert service.plans(project_id)[0] == plan


def test_unknown_preset_is_rejected(tmp_path):
    service = ExportPresetService(tmp_path, project_dir_resolver=lambda _: "project")
    with pytest.raises(ValueError, match="unknown export preset"):
        service.create_plan(uuid4(), ExportPlanRequest(preset_id="unknown"))
