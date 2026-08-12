from __future__ import annotations

from pathlib import Path

from .subtitle_packager import SubtitleArtifact


def build_final_mux_command(
    ffmpeg: str,
    video: Path,
    audio: Path,
    output: Path,
    *,
    subtitles: list[SubtitleArtifact] | None = None,
    video_codec: str = "copy",
    audio_codec: str = "aac",
    audio_bitrate: str = "192k",
) -> list[str]:
    tracks = subtitles or []
    command = [ffmpeg, "-y", "-loglevel", "error", "-i", str(video), "-i", str(audio)]
    for track in tracks:
        if track.format == "ass":
            command.extend(["-i", str(track.path)])
    command.extend(
        [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            video_codec,
            "-c:a",
            audio_codec,
            "-b:a",
            audio_bitrate,
        ]
    )
    ass_tracks = [track for track in tracks if track.format == "ass"]
    for index, track in enumerate(ass_tracks, start=2):
        command.extend(
            [
                "-map",
                f"{index}:0",
                "-c:s",
                "mov_text",
                f"-metadata:s:s:{index - 2}",
                f"language={track.language}",
            ]
        )
    # Subtitle tracks may end before the video/audio programme.  `-shortest`
    # considers every mapped input, so it would silently truncate a valid
    # preview to the last subtitle cue.  Video and master audio have already
    # been trimmed to the graph duration by their respective pipeline stages.
    command.append(str(output))
    return command
