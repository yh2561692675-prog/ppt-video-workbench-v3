from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import Field, JsonValue

from peripheral_contracts.models import StrictModel, VersionedModel


class BusinessArtifact(StrictModel):
    logical_name: str = Field(pattern=r"^[a-z][a-z0-9_.-]{1,63}$")
    kind: str = Field(min_length=1, max_length=64)
    size_bytes: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class BusinessResultManifest(VersionedModel):
    module_id: Literal[
        "P03",
        "P04",
        "P05",
        "P06",
        "P07",
        "P08",
        "P09",
        "P10",
        "P11",
        "P12",
    ]
    job_type: str = Field(pattern=r"^[a-z][a-z0-9_.-]{2,63}$")
    project_id: UUID
    project_revision: int = Field(ge=1)
    input_fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")
    cache_key: str = Field(pattern=r"^[0-9a-f]{64}$")
    result_type: str = Field(pattern=r"^[a-z][a-z0-9_]{2,63}$")
    payload: dict[str, JsonValue]
    artifacts: tuple[BusinessArtifact, ...] = ()
