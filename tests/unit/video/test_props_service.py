from __future__ import annotations

from uuid import uuid4

import pytest
from workbench.video.models import ProjectVideoProps, VideoPageProps, ms_to_frames


def _props() -> dict[str, object]:
    page_id = str(uuid4())
    return {
        "schema_version": 1,
        "project_id": str(uuid4()),
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "duration_ms": 2_000,
        "template_version": "tech-board-v1",
        "reduced_motion": False,
        "pages": [
            {
                "page_id": page_id,
                "page_order": 1,
                "title": "第一页",
                "image_path": "02_页面预览/page-0001.png",
                "audio_path": "05_音频/page-0001.wav",
                "start_ms": 0,
                "end_ms": 2_000,
                "subtitle_cue_ids": [],
            }
        ],
        "subtitles": [],
    }


def test_video_props_freezes_canvas_and_converts_milliseconds_to_frames() -> None:
    props = ProjectVideoProps.model_validate(_props())

    assert (props.width, props.height, props.fps) == (1920, 1080, 30)
    assert props.duration_in_frames == 60
    assert ms_to_frames(50, 30) == 2


def test_video_page_props_is_strict_and_rejects_unknown_fields() -> None:
    page = _props()["pages"][0]
    assert isinstance(page, dict)
    with pytest.raises(ValueError):
        VideoPageProps.model_validate({**page, "unexpected": True})


def test_video_props_accepts_qualified_output_profiles_and_rejects_unknown_canvas() -> None:
    for width, height, fps in ((1280, 720, 24), (720, 1280, 25), (1080, 1080, 60)):
        payload = _props()
        payload.update({"width": width, "height": height, "fps": fps})
        props = ProjectVideoProps.model_validate(payload)
        assert (props.width, props.height, props.fps) == (width, height, fps)

    wrong_canvas = _props()
    wrong_canvas["width"] = 1281
    with pytest.raises(ValueError, match="qualified"):
        ProjectVideoProps.model_validate(wrong_canvas)


def test_video_props_rejects_out_of_order_pages() -> None:

    out_of_order = _props()
    first = out_of_order["pages"][0]
    assert isinstance(first, dict)
    out_of_order["pages"] = [
        {**first, "page_order": 2},
        {
            **first,
            "page_order": 1,
            "page_id": str(uuid4()),
            "start_ms": 500,
            "end_ms": 1_500,
        },
    ]
    with pytest.raises(ValueError, match="页面顺序"):
        ProjectVideoProps.model_validate(out_of_order)
