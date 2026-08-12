from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from workbench.rendering.ffmpeg_audio import AudioFilterCompiler, build_audio_render_command
from workbench.rendering.final_mux import build_final_mux_command
from workbench.rendering.models import (
    AudioMixClip,
    AudioMixPlan,
    GraphCanvas,
    RenderGraphV2,
    SubtitleCue,
    SubtitleRenderPlan,
    SubtitleWord,
)
from workbench.rendering.subtitle_packager import SubtitlePackager


def _graph() -> RenderGraphV2:
    return RenderGraphV2(
        project_id=uuid4(),
        timeline_revision=2,
        duration_us=3_000_000,
        canvas=GraphCanvas(width=1920, height=1080, fps=30),
        audio=AudioMixPlan(
            clips=[
                AudioMixClip(
                    id=uuid4(),
                    kind="narration",
                    source_ref="audio/narration.wav",
                    timeline_start_us=500_000,
                    timeline_end_us=2_500_000,
                    source_in_us=100_000,
                    gain_db=-3,
                )
            ]
        ),
        subtitles=SubtitleRenderPlan(
            render_mode="both",
            languages=["zh-CN"],
            cues=[
                SubtitleCue(
                    language="zh-CN",
                    label="中文",
                    start_us=100_000,
                    end_us=900_000,
                    text="你好世界",
                    words=[SubtitleWord(text="你好", start_us=100_000, end_us=400_000)],
                )
            ],
        ),
        graph_hash="0" * 64,
    )


def test_audio_filter_compiler_preserves_timeline_delay_and_gain(tmp_path: Path) -> None:
    spec = AudioFilterCompiler().compile(_graph(), tmp_path)
    assert spec.input_paths == ((tmp_path / "audio" / "narration.wav").resolve(),)
    assert "atrim=start=0.100000:duration=2.000000" in spec.filter_complex
    assert "adelay=500|500" in spec.filter_complex
    assert "volume=-3.0000dB" in spec.filter_complex
    command = build_audio_render_command("ffmpeg", spec, tmp_path / "master.wav")
    assert "-filter_complex" in command
    assert "[master]" in command


def test_subtitle_packager_generates_srt_vtt_ass_and_mux_maps_soft_tracks(tmp_path: Path) -> None:
    plan = _graph().subtitles
    artifacts = SubtitlePackager().write(plan, tmp_path / "subs")
    assert {artifact.format for artifact in artifacts} == {"srt", "vtt", "ass"}
    srt = next(artifact.path for artifact in artifacts if artifact.format == "srt")
    assert "00:00:00,100 --> 00:00:00,900" in srt.read_text(encoding="utf-8")
    ass = [artifact for artifact in artifacts if artifact.format == "ass"]
    command = build_final_mux_command(
        "ffmpeg",
        tmp_path / "video.mp4",
        tmp_path / "master.wav",
        tmp_path / "final.mp4",
        subtitles=ass,
    )
    assert command.count("-map") == 3
    assert "language=zh-CN" in command
    assert "-shortest" not in command


def test_subtitle_none_mode_writes_no_files(tmp_path: Path) -> None:
    plan = _graph().subtitles.model_copy(update={"render_mode": "none"})
    assert SubtitlePackager().write(plan, tmp_path) == []
