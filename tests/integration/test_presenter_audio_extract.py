import wave
from pathlib import Path
from subprocess import CompletedProcess

from workbench.media.presenter_audio import extract_analysis_audio


def test_extracts_16khz_mono_pcm_with_safe_command(tmp_path: Path) -> None:
    source = tmp_path / "中文用户名" / "真人讲解.mp4"
    source.parent.mkdir()
    source.write_bytes(b"video")
    output = tmp_path / "分析音频.wav"
    seen: list[list[str]] = []

    def runner(command: list[str]) -> CompletedProcess[bytes]:
        seen.append(command)
        destination = Path(command[-1])
        with wave.open(str(destination), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(16_000)
            handle.writeframes(b"\x00\x00" * 16_000)
        return CompletedProcess(command, 0, stdout=b"", stderr=b"")

    result = extract_analysis_audio(source, output, runner=runner)

    assert result.duration_ms == 1_000
    assert result.sample_rate == 16_000
    assert result.channels == 1
    assert result.source_time_offset_ms == 0
    assert isinstance(seen[0], list)
    assert seen[0][-1].endswith(".tmp")
    assert output.is_file()
