from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .models import SubtitleCue, SubtitleRenderPlan


@dataclass(frozen=True)
class SubtitleArtifact:
    language: str
    format: str
    path: Path


class SubtitlePackager:
    def write(self, plan: SubtitleRenderPlan, output_dir: Path) -> list[SubtitleArtifact]:
        if plan.render_mode == "none":
            return []
        output_dir.mkdir(parents=True, exist_ok=True)
        artifacts: list[SubtitleArtifact] = []
        for language in plan.languages or sorted({cue.language for cue in plan.cues}):
            cues = [cue for cue in plan.cues if cue.language == language]
            if not cues:
                continue
            safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in language)
            for extension, content in (
                ("srt", self.to_srt(cues)),
                ("vtt", self.to_webvtt(cues)),
                ("ass", self.to_ass(cues, plan.default_style)),
            ):
                path = output_dir / f"字幕-{safe}.{extension}"
                path.write_text(content, encoding="utf-8")
                artifacts.append(SubtitleArtifact(language, extension, path))
        return artifacts

    @staticmethod
    def to_srt(cues: list[SubtitleCue]) -> str:
        lines: list[str] = []
        for index, cue in enumerate(cues, start=1):
            lines.extend(
                [
                    str(index),
                    f"{_timestamp(cue.start_us, ',')} --> {_timestamp(cue.end_us, ',')}",
                    _text(cue),
                    "",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def to_webvtt(cues: list[SubtitleCue]) -> str:
        lines = ["WEBVTT", ""]
        for cue in cues:
            lines.extend(
                [
                    f"{_timestamp(cue.start_us, '.')} --> {_timestamp(cue.end_us, '.')}",
                    _text(cue),
                    "",
                ]
            )
        return "\n".join(lines)

    @staticmethod
    def to_ass(cues: list[SubtitleCue], style: dict[str, object]) -> str:
        font = str(style.get("font_family", "Arial"))
        size_value = style.get("font_size", 48)
        size = int(size_value) if isinstance(size_value, (str, int, float)) else 48
        header = (
            "[Script Info]\nScriptType: v4.00+\nPlayResX: 1920\nPlayResY: 1080\n\n"
            "[V4+ Styles]\n"
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
            "OutlineColour, BackColour, Bold, Italic, BorderStyle, Outline, Shadow, "
            "Alignment, MarginL, MarginR, MarginV, Encoding\n"
        )
        header += (
            f"Style: Default,{font},{size},&H00FFFFFF,&H000000FF,&H00000000,"
            "&H66000000,0,0,1,2,0,2,80,80,50,1\n\n"
            "[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, "
            "MarginV, Effect, Text\n"
        )
        body = "\n".join(
            "Dialogue: 0,"
            f"{_ass_timestamp(cue.start_us)},{_ass_timestamp(cue.end_us)},"
            f"Default,,0,0,0,,{_ass_text(cue)}"
            for cue in cues
        )
        return header + body + "\n"


def _text(cue: SubtitleCue) -> str:
    text = cue.text
    for index in sorted(cue.line_breaks, reverse=True):
        if 0 < index < len(text):
            text = text[:index] + "\n" + text[index:]
    return text if not cue.translation else f"{text}\n{cue.translation}"


def _ass_text(cue: SubtitleCue) -> str:
    return _text(cue).replace("\n", "\\N").replace("{", "\\{").replace("}", "\\}")


def _timestamp(value_us: int, separator: str) -> str:
    total_ms = max(0, value_us // 1_000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, milliseconds = divmod(remainder, 1_000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{milliseconds:03d}"


def _ass_timestamp(value_us: int) -> str:
    total_cs = max(0, value_us // 10_000)
    hours, remainder = divmod(total_cs, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{seconds:02d}.{centiseconds:02d}"
