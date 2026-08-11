from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Iterable
from pathlib import Path
from typing import Protocol
from uuid import NAMESPACE_URL, uuid5

from workbench.audio.models import RecognizedSegment
from workbench.domain.transcript import (
    PresenterTranscriptSentence,
    PresenterTranscriptWord,
    TranscriptRevision,
)
from workbench.media.presenter_audio import AnalysisAudio


class PresenterTranscriptionBackend(Protocol):
    def transcribe(
        self,
        audio: Path,
        **kwargs: object,
    ) -> tuple[Iterable[RecognizedSegment], str]: ...


def transcribe_presenter(
    audio: AnalysisAudio,
    backend: PresenterTranscriptionBackend,
    *,
    source_hash: str,
    glossary: list[str] | None = None,
    model_version: str = "faster-whisper-small-v1",
    language: str = "zh",
    backend_options: dict[str, object] | None = None,
) -> TranscriptRevision:
    glossary_items = sorted({_normalize(item) for item in (glossary or []) if item.strip()})
    glossary_version = _digest(glossary_items)
    cache_key = _digest(
        {
            "source_hash": source_hash,
            "audio_hash": audio.sha256,
            "audio_cache_key": audio.cache_key,
            "model_version": model_version,
            "glossary_version": glossary_version,
            "language": language,
            "word_timestamps": True,
        }
    )
    raw_segments, detected_language = backend.transcribe(
        Path(audio.wav_path),
        **(backend_options or {}),
        language=language,
        word_timestamps=True,
        glossary=glossary_items,
        model_version=model_version,
    )
    words: list[PresenterTranscriptWord] = []
    sentences: list[PresenterTranscriptSentence] = []
    previous_end = 0
    for segment_index, segment in enumerate(raw_segments):
        sentence_words: list[PresenterTranscriptWord] = []
        for word_index, word in enumerate(segment.words):
            start_ms = max(0, round(word.start * 1_000))
            end_ms = min(audio.duration_ms, round(word.end * 1_000))
            if end_ms <= start_ms or start_ms < previous_end:
                raise ValueError("presenter word timestamps must be monotonic")
            identifier = str(
                uuid5(NAMESPACE_URL, f"{cache_key}:word:{segment_index}:{word_index}:{start_ms}")
            )
            converted = PresenterTranscriptWord(
                id=identifier,
                text=word.text,
                normalized_text=_normalize(word.text),
                start_ms=start_ms,
                end_ms=end_ms,
                confidence=word.probability,
            )
            sentence_words.append(converted)
            words.append(converted)
            previous_end = end_ms
        if not sentence_words:
            continue
        normalized_sentence = _normalize(segment.text)
        review_reasons = []
        if any(marker in normalized_sentence for marker in ("重来", "刚才说错", "说错了")):
            review_reasons.append("suspected_rerecord")
        sentences.append(
            PresenterTranscriptSentence(
                id=str(uuid5(NAMESPACE_URL, f"{cache_key}:sentence:{segment_index}")),
                text=segment.text,
                normalized_text=normalized_sentence,
                start_ms=sentence_words[0].start_ms,
                end_ms=sentence_words[-1].end_ms,
                word_ids=[item.id for item in sentence_words],
                review_reasons=review_reasons,
            )
        )
    content_payload = {
        "words": [item.model_dump(mode="json") for item in words],
        "sentences": [item.model_dump(mode="json") for item in sentences],
    }
    content_hash = _digest(content_payload)
    return TranscriptRevision(
        id=uuid5(NAMESPACE_URL, f"{cache_key}:{content_hash}"),
        source_hash=source_hash,
        audio_hash=audio.sha256,
        duration_ms=audio.duration_ms,
        detected_language=detected_language,
        model_version=model_version,
        glossary_version=glossary_version,
        cache_key=cache_key,
        content_hash=content_hash,
        words=words,
        sentences=sentences,
    )


def _normalize(text: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", text).strip().split())


def _digest(payload: object) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
