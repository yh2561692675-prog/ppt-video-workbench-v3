"""Local deterministic assistance with provider-gated translation."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from .models import ContentAssistCandidateV1, ContentAssistRequestV1
from .repository import ContentAssistRepository


class ContentAssistUnavailable(RuntimeError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


class ContentAssistService:
    def __init__(
        self,
        repository: ContentAssistRepository,
        translator: Callable[[str, str, str], str] | None = None,
    ) -> None:
        self.repository = repository
        self.translator = translator

    def create(self, request: ContentAssistRequestV1) -> ContentAssistCandidateV1:
        if request.kind == "translate":
            if self.translator is None or request.target_language is None:
                candidate = ContentAssistCandidateV1(
                    request_id=request.request_id,
                    kind=request.kind,
                    status="needs_provider",
                    source_text=request.source_text,
                    candidate_text=request.source_text,
                    source_language=request.source_language,
                    target_language=request.target_language,
                    warnings=["translation_provider_unavailable"],
                )
                return self.repository.save(candidate)
            translated = self.translator(
                request.source_text, request.source_language, request.target_language
            )
            candidate = ContentAssistCandidateV1(
                request_id=request.request_id,
                kind=request.kind,
                source_text=request.source_text,
                candidate_text=translated.strip(),
                source_language=request.source_language,
                target_language=request.target_language,
                provider_id="injected-sandbox",
            )
            return self.repository.save(candidate)
        if request.kind == "segment":
            segments = self.segment(request.source_text, request.max_segment_chars)
            candidate = ContentAssistCandidateV1(
                request_id=request.request_id,
                kind=request.kind,
                source_text=request.source_text,
                candidate_text="\n".join(segments),
                source_language=request.source_language,
                segments=segments,
            )
        else:
            polished = self.polish(request.source_text, request.style)
            candidate = ContentAssistCandidateV1(
                request_id=request.request_id,
                kind=request.kind,
                source_text=request.source_text,
                candidate_text=polished,
                source_language=request.source_language,
            )
        return self.repository.save(candidate)

    def accept(self, candidate_id: UUID) -> ContentAssistCandidateV1:
        candidate = self.repository.get(candidate_id)
        if candidate.status == "needs_provider":
            raise ContentAssistUnavailable("translation_provider_unavailable")
        return self.repository.update(
            candidate.model_copy(update={"status": "accepted", "accepted_at": datetime.now(UTC)})
        )

    @staticmethod
    def polish(text: str, style: str = "neutral") -> str:
        clean = re.sub(r"\s+", " ", text.strip())
        if style == "concise":
            clean = re.sub(r"(其实|然后|就是|这个)", "", clean)
            clean = re.sub(r"\s{2,}", " ", clean).strip()
        if clean and clean[-1] not in "。！？.!?":
            clean += "。"
        return clean

    @staticmethod
    def segment(text: str, max_chars: int = 60) -> list[str]:
        if max_chars < 1:
            raise ValueError("max_chars must be positive")
        source = text.strip()
        result: list[str] = []
        remainder = source
        while len(remainder) > max_chars:
            boundary = max(
                (remainder.rfind(mark, 0, max_chars) + 1 for mark in "。！？；，、："),
                default=0,
            )
            if boundary <= 0:
                boundary = max_chars
            result.append(remainder[:boundary].strip())
            remainder = remainder[boundary:].strip()
        if remainder:
            result.append(remainder)
        return [item for item in result if item]
