"""Deterministic S0 Echo module."""

from __future__ import annotations

from typing import Literal

from peripheral_contracts import StrictModel
from pydantic import Field, JsonValue


class EchoParameters(StrictModel):
    text: str = Field(min_length=1, max_length=2000)
    delay_ms: int = Field(default=0, ge=0, le=30000)
    fail_mode: Literal["none", "retryable", "permanent", "invalid_result"] = "none"


def validate_parameters(parameters: dict[str, JsonValue]) -> EchoParameters:
    return EchoParameters.model_validate(parameters)


__all__ = ["EchoParameters", "validate_parameters"]
