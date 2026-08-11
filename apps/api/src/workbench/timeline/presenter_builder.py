from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from copy import deepcopy
from datetime import UTC, datetime
from typing import Literal, TypedDict
from uuid import UUID

from workbench.domain.presenter import (
    PresenterTimelineV1,
    PresenterTimeRange,
    SlideAnchor,
)
from workbench.domain.transcript import PresenterTranscriptSentence
from workbench.matching.presenter_slide_matcher import PresenterMatchResult


class _AnchorGroup(TypedDict):
    page_id: UUID
    page_index: int
    first: int
    last: int
    score: float
    sentence_ids: list[str]


def classify_confidence(score: float) -> Literal["auto", "review", "blocked"]:
    if score >= 0.9:
        return "auto"
    if score >= 0.8:
        return "review"
    return "blocked"


def build_presenter_timeline(
    match: PresenterMatchResult,
    sentences: list[PresenterTranscriptSentence],
    duration_ms: int,
    *,
    source_id: UUID,
    source_version: str,
) -> PresenterTimelineV1:
    sentence_by_id = {sentence.id: sentence for sentence in sentences}
    matches_by_page: dict[UUID, list[tuple[int, int, float, str]]] = defaultdict(list)
    page_indexes: dict[UUID, int] = {}
    for candidate in match.matches:
        page_indexes[candidate.page_id] = candidate.page_index
        for sentence_id in candidate.sentence_ids:
            sentence = sentence_by_id.get(sentence_id)
            if sentence is not None:
                matches_by_page[candidate.page_id].append(
                    (sentence.start_ms, sentence.end_ms, candidate.score, sentence_id)
                )

    groups: list[_AnchorGroup] = []
    for page_id, items in matches_by_page.items():
        ordered = sorted(items)
        groups.append(
            {
                "page_id": page_id,
                "page_index": page_indexes[page_id],
                "first": ordered[0][0],
                "last": ordered[-1][1],
                "score": sum(item[2] for item in ordered) / len(ordered),
                "sentence_ids": [item[3] for item in ordered],
            }
        )
    groups.sort(key=lambda item: (item["page_index"], item["first"]))

    anchors: list[SlideAnchor] = []
    for index, group in enumerate(groups):
        start_ms = 0 if index == 0 else anchors[-1].end_ms
        if index + 1 < len(groups):
            following = groups[index + 1]
            end_ms = (int(group["last"]) + int(following["first"])) // 2
        else:
            end_ms = duration_ms
        score = float(group["score"])
        anchors.append(
            SlideAnchor(
                page_id=group["page_id"],
                start_ms=start_ms,
                end_ms=end_ms,
                sentence_ids=group["sentence_ids"],
                confidence=score,
                status=classify_confidence(score),
                source_revision=source_version,
            )
        )

    unassigned_ranges = [
        PresenterTimeRange(
            start_ms=sentence_by_id[sentence_id].start_ms,
            end_ms=sentence_by_id[sentence_id].end_ms,
            reason=f"unassigned_sentence:{sentence_id}",
        )
        for sentence_id in match.unassigned_sentence_ids
        if sentence_id in sentence_by_id
    ]
    timeline = PresenterTimelineV1(
        source_id=source_id,
        source_version=source_version,
        duration_ms=duration_ms,
        anchors=anchors,
        unassigned_ranges=sorted(unassigned_ranges, key=lambda item: item.start_ms),
        generated_at=datetime.now(UTC),
    )
    return timeline.model_copy(update={"timeline_hash": timeline_content_hash(timeline)})


def replace_anchor(
    timeline: PresenterTimelineV1,
    replacement: SlideAnchor,
    *,
    expected_revision: int,
) -> PresenterTimelineV1:
    if expected_revision != timeline.revision:
        raise ValueError("presenter_timeline_revision_conflict")
    anchors = list(timeline.anchors)
    index = next(
        (
            position
            for position, anchor in enumerate(anchors)
            if anchor.page_id == replacement.page_id
        ),
        None,
    )
    if index is None:
        raise KeyError(replacement.page_id)
    if index > 0 and replacement.start_ms < anchors[index - 1].end_ms:
        raise ValueError("presenter_anchor_overlap")
    if index + 1 < len(anchors) and replacement.end_ms > anchors[index + 1].start_ms:
        raise ValueError("presenter_anchor_overlap")
    anchors[index] = replacement
    updated = timeline.model_copy(
        update={
            "anchors": anchors,
            "revision": timeline.revision + 1,
            "generated_at": datetime.now(UTC),
        }
    )
    updated = PresenterTimelineV1.model_validate(updated.model_dump(mode="python"))
    return updated.model_copy(update={"timeline_hash": timeline_content_hash(updated)})


def recalculate_unlocked(
    timeline: PresenterTimelineV1,
    changed_page_id: UUID,
    replacement: SlideAnchor,
) -> PresenterTimelineV1:
    """Replace one unlocked anchor while preserving non-adjacent anchors byte-for-byte."""
    anchors = deepcopy(timeline.anchors)
    index = next(
        (position for position, anchor in enumerate(anchors) if anchor.page_id == changed_page_id),
        None,
    )
    if index is None:
        raise KeyError(changed_page_id)
    if anchors[index].manual_lock:
        return timeline
    if replacement.page_id != changed_page_id:
        raise ValueError("replacement page id does not match changed page")
    anchors[index] = replacement
    if index > 0 and not anchors[index - 1].manual_lock:
        anchors[index - 1] = anchors[index - 1].model_copy(update={"end_ms": replacement.start_ms})
    if index + 1 < len(anchors) and not anchors[index + 1].manual_lock:
        anchors[index + 1] = anchors[index + 1].model_copy(update={"start_ms": replacement.end_ms})
    updated = PresenterTimelineV1.model_validate(
        timeline.model_copy(
            update={"anchors": anchors, "revision": timeline.revision + 1}
        ).model_dump(mode="python")
    )
    return updated.model_copy(update={"timeline_hash": timeline_content_hash(updated)})


def timeline_content_hash(timeline: PresenterTimelineV1) -> str:
    payload = timeline.model_dump(
        mode="json",
        exclude={"timeline_hash", "generated_at"},
    )
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
