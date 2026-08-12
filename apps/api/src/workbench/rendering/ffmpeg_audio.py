from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import AudioMixClip, RenderGraphV2


@dataclass(frozen=True)
class AudioFilterSpec:
    input_paths: tuple[Path, ...]
    filter_complex: str
    output_label: str = "master"


class AudioFilterCompiler:
    """Compile an AudioMixPlan into a deterministic FFmpeg filter graph."""

    def compile(self, graph: RenderGraphV2, project_root: Path) -> AudioFilterSpec:
        root = project_root.resolve()
        assets = {asset.source_ref: asset for asset in graph.assets}
        clips = graph.audio.clips
        input_paths: list[Path] = []
        branches: list[str] = []
        for index, clip in enumerate(clips):
            asset = assets.get(clip.source_ref)
            relative = asset.resolved_path if asset and asset.resolved_path else clip.source_ref
            path = (root / relative).resolve()
            if path != root and root not in path.parents:
                raise ValueError(f"audio asset path escapes project root: {clip.source_ref}")
            input_paths.append(path)
            branches.append(self._clip_filter(index, clip))
        if not branches:
            branches.append(
                f"anullsrc=channel_layout=stereo:sample_rate=48000,"
                f"atrim=duration={graph.duration_us / 1_000_000:.6f},asetpts=PTS-STARTPTS[master]"
            )
            return AudioFilterSpec(tuple(input_paths), ";".join(branches))
        mix_inputs = "".join(f"[a{index}]" for index in range(len(branches)))
        mix = (
            f"{mix_inputs}amix=inputs={len(branches)}:duration=longest:dropout_transition=0,"
            f"loudnorm=I={graph.audio.loudness_target_lufs}:TP={graph.audio.true_peak_db}:LRA=11,"
            "alimiter=limit=0.95[master]"
        )
        return AudioFilterSpec(tuple(input_paths), ";".join([*branches, mix]))

    @staticmethod
    def _clip_filter(index: int, clip: AudioMixClip) -> str:
        duration_s = (clip.timeline_end_us - clip.timeline_start_us) / 1_000_000
        source_s = clip.source_in_us / 1_000_000
        delay_ms = round(clip.timeline_start_us / 1_000)
        filters = [
            f"atrim=start={source_s:.6f}:duration={duration_s:.6f}",
            "asetpts=PTS-STARTPTS",
        ]
        if clip.fade_in_us:
            filters.append(f"afade=t=in:st=0:d={clip.fade_in_us / 1_000_000:.6f}")
        if clip.fade_out_us:
            fade_start = max(0, duration_s - clip.fade_out_us / 1_000_000)
            filters.append(f"afade=t=out:st={fade_start:.6f}:d={clip.fade_out_us / 1_000_000:.6f}")
        if clip.gain_db:
            filters.append(f"volume={clip.gain_db:.4f}dB")
        if clip.pan:
            left = max(0.0, min(2.0, 1 - clip.pan))
            right = max(0.0, min(2.0, 1 + clip.pan))
            filters.append(f"pan=stereo|c0={left:.4f}*c0|c1={right:.4f}*c1")
        # The bundled Windows FFmpeg build does not expose the newer `all`
        # option.  Give both output channels an explicit delay instead so the
        # command is portable across the packaged and developer runtimes.
        filters.append(f"adelay={delay_ms}|{delay_ms}")
        return f"[{index}:a]" + ",".join(filters) + f"[a{index}]"


def build_audio_render_command(
    ffmpeg: str,
    spec: AudioFilterSpec,
    output: Path,
    *,
    sample_rate: int = 48_000,
) -> list[str]:
    command = [ffmpeg, "-y", "-loglevel", "error"]
    for path in spec.input_paths:
        command.extend(["-i", str(path)])
    command.extend(
        [
            "-filter_complex",
            spec.filter_complex,
            "-map",
            f"[{spec.output_label}]",
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            "-c:a",
            "pcm_s16le",
            str(output),
        ]
    )
    return command
