from __future__ import annotations

import json
import re
from typing import Protocol

from pydantic import ValidationError

from .prompt_builder import LlmRequest, NarrationDraft, PageContext, build_prompt


class CompletionClient(Protocol):
    def complete(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
    ) -> str: ...


class NarrationGenerationError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class NarrationGenerator:
    def __init__(
        self,
        client: CompletionClient,
        *,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
    ) -> None:
        self._client = client
        self._base_url = base_url
        self._api_key = api_key
        self._model = model

    def generate(self, context: PageContext) -> NarrationDraft:
        request = build_prompt(context)
        raw = self._complete(request)
        try:
            draft = _parse_draft(raw)
        except NarrationGenerationError:
            repair_messages = [
                *request.messages,
                {"role": "assistant", "content": raw},
                {
                    "role": "user",
                    "content": (
                        "仅修复 JSON 格式，使其符合前述 Schema；不得增加、删除或改写事实。"
                    ),
                },
            ]
            repaired = self._client.complete(
                base_url=self._base_url,
                api_key=self._api_key,
                model=self._model,
                messages=repair_messages,
            )
            try:
                draft = _parse_draft(repaired)
            except NarrationGenerationError as error:
                raise NarrationGenerationError(
                    "narration_invalid_json", "模型两次返回的结构化旁白均无效"
                ) from error

        _validate_source_refs(draft, context)
        _validate_numbers(draft, context)
        return _mark_repetition(draft, context.previous_narrations)

    def _complete(self, request: LlmRequest) -> str:
        return self._client.complete(
            base_url=self._base_url,
            api_key=self._api_key,
            model=self._model,
            messages=request.messages,
            max_tokens=request.max_tokens,
        )


def _parse_draft(raw: str) -> NarrationDraft:
    try:
        return NarrationDraft.model_validate(json.loads(raw))
    except (json.JSONDecodeError, ValidationError, TypeError) as error:
        raise NarrationGenerationError(
            "narration_invalid_json", "模型返回的旁白不符合结构化输出契约"
        ) from error


def _validate_source_refs(draft: NarrationDraft, context: PageContext) -> None:
    unknown = set(draft.source_refs) - context.allowed_source_refs
    if unknown:
        raise NarrationGenerationError(
            "narration_unknown_source_ref", "旁白引用了当前材料之外的来源"
        )


def _validate_numbers(draft: NarrationDraft, context: PageContext) -> None:
    material = f"{context.page_text}\n{context.outline_text}"
    allowed = set(_numbers(material))
    generated = set(_numbers(draft.text))
    if generated - allowed:
        raise NarrationGenerationError("narration_unsupported_number", "旁白包含材料中不存在的数字")


def _numbers(text: str) -> list[str]:
    return re.findall(r"(?<![A-Za-z0-9])\d+(?:\.\d+)?%?(?![A-Za-z0-9])", text)


def _mark_repetition(draft: NarrationDraft, previous: list[str]) -> NarrationDraft:
    prior_sentences = _sentences("\n".join(previous))
    repeated = _sentences(draft.text) & prior_sentences
    if not repeated or "cross_page_repetition" in draft.warnings:
        return draft
    return draft.model_copy(update={"warnings": [*draft.warnings, "cross_page_repetition"]})


def _sentences(text: str) -> set[str]:
    return {
        normalized
        for sentence in re.split(r"[。！？!?；;\n]+", text)
        if (normalized := re.sub(r"\s+", "", sentence))
    }
