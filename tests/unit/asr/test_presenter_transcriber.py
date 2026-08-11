from pathlib import Path

from workbench.asr.presenter_transcriber import transcribe_presenter
from workbench.audio.models import RecognizedSegment, RecognizedWord
from workbench.media.presenter_audio import AnalysisAudio


class FixedBackend:
    def transcribe(self, _: Path, **__: object):
        return (
            [
                RecognizedSegment(
                    start=0.0,
                    end=1.2,
                    text="院校专业组 一",
                    words=[
                        RecognizedWord("院校专业组", 0.0, 0.7, 0.98),
                        RecognizedWord("一", 0.7, 1.2, 0.95),
                    ],
                ),
                RecognizedSegment(
                    start=1.5,
                    end=2.4,
                    text="刚才说错 重来",
                    words=[
                        RecognizedWord("刚才说错", 1.5, 2.0, 0.9),
                        RecognizedWord("重来", 2.0, 2.4, 0.9),
                    ],
                ),
            ],
            "zh",
        )


def _audio(tmp_path: Path) -> AnalysisAudio:
    path = tmp_path / "analysis.wav"
    path.write_bytes(b"wav")
    return AnalysisAudio(
        source_path="source.mp4",
        wav_path=str(path),
        duration_ms=3_000,
        sample_rate=16_000,
        channels=1,
        sha256="b" * 64,
        cache_key="audio-cache",
    )


def test_words_are_monotonic_and_inside_media(tmp_path: Path) -> None:
    transcript = transcribe_presenter(
        _audio(tmp_path),
        FixedBackend(),
        source_hash="a" * 64,
        glossary=["院校专业组"],
    )

    assert all(
        first.end_ms <= second.start_ms
        for first, second in zip(transcript.words, transcript.words[1:], strict=False)
    )
    assert transcript.words[-1].end_ms <= transcript.duration_ms
    assert transcript.words[0].normalized_text == "院校专业组"
    assert transcript.sentences[1].review_reasons == ["suspected_rerecord"]


def test_cache_key_and_ids_are_deterministic(tmp_path: Path) -> None:
    audio = _audio(tmp_path)
    first = transcribe_presenter(
        audio,
        FixedBackend(),
        source_hash="a" * 64,
        glossary=["院校专业组"],
    )
    second = transcribe_presenter(
        audio,
        FixedBackend(),
        source_hash="a" * 64,
        glossary=["院校专业组"],
    )

    assert first.cache_key == second.cache_key
    assert [word.id for word in first.words] == [word.id for word in second.words]
    assert first.content_hash == second.content_hash
