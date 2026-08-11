from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class PlaybackEvidenceError(RuntimeError):
    pass


def validate_playback_evidence(payload: Mapping[str, Any]) -> dict[str, object]:
    """Validate browser-recorded playback events without trusting an internal callback."""
    events = payload.get("events")
    if not isinstance(events, list) or not events:
        raise PlaybackEvidenceError("playback_events_missing")
    first = events[0] if isinstance(events[0], Mapping) else {}
    last = events[-1] if isinstance(events[-1], Mapping) else {}
    if first.get("event") != "play" or first.get("current_time") != 0:
        raise PlaybackEvidenceError("playback_not_started_at_zero")
    if last.get("event") != "ended":
        raise PlaybackEvidenceError("playback_not_ended")
    if payload.get("console_errors"):
        raise PlaybackEvidenceError("playback_console_error")
    failed_requests = payload.get("failed_requests", [])
    if not isinstance(failed_requests, list):
        raise PlaybackEvidenceError("playback_network_evidence_invalid")
    if any(
        isinstance(item, Mapping) and int(item.get("status", 0)) >= 400
        for item in failed_requests
    ):
        raise PlaybackEvidenceError("playback_network_error")
    stalls = [
        item
        for item in events
        if isinstance(item, Mapping) and item.get("event") == "stalled"
    ]
    return {
        "duration_seconds": last.get("current_time"),
        "event_count": len(events),
        "stall_count": len(stalls),
        "screenshots": payload.get("screenshots", []),
    }
