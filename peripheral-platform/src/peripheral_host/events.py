from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID, uuid4

from peripheral_contracts import EventEnvelope
from pydantic import JsonValue

from peripheral_host.repositories import JobRecord


def _utc_now() -> datetime:
    return datetime.now(UTC)


class EventFactory:
    def __init__(
        self,
        *,
        event_id_factory: Callable[[], UUID] = uuid4,
        clock: Callable[[], datetime] = _utc_now,
        source: str = "peripheral-host",
    ) -> None:
        self._event_id_factory = event_id_factory
        self._clock = clock
        self._source = source

    def create(
        self,
        *,
        record: JobRecord,
        event_type: str,
        data: dict[str, JsonValue],
        severity: str = "info",
    ) -> EventEnvelope:
        return EventEnvelope.model_validate(
            {
                "schema_version": "1.0",
                "event_id": self._event_id_factory(),
                "job_id": record.job_id,
                "project_id": record.project_id,
                "source": self._source,
                "event_type": event_type,
                "severity": severity,
                "occurred_at": self._clock(),
                "data": data,
            }
        )
