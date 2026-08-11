"""Explicit bridge between the P2 envelope and the frozen V1 core contracts.

The P2/Cloud APIs use an integer major version.  Core wire contracts use their
own version strings.  These values are deliberately not normalized or coerced.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

CORE_CONTRACT_SET_SHA256: Literal[
    "de55cc1090e49b0ab4d7fb6375b4509cb878d5888e8bef54fd00407a34fbebf6"
] = (
    "de55cc1090e49b0ab4d7fb6375b4509cb878d5888e8bef54fd00407a34fbebf6"
)


class CoreCompatibilityEnvelopeV1(BaseModel):
    """Pin one P2 operation to the audited A13 core contract set."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal[1] = 1
    core_contract_set_sha256: Literal[
        "de55cc1090e49b0ab4d7fb6375b4509cb878d5888e8bef54fd00407a34fbebf6"
    ] = CORE_CONTRACT_SET_SHA256
    job_schema_version: Literal["1.0"] = "1.0"
    asset_schema_version: Literal["1.0"] = "1.0"
    error_mapping_version: Literal["1.0"] = "1.0"
    version_conversion: Literal["none"] = "none"


CoreProjectedErrorCode = Literal[
    "P2_PROVIDER_FAILURE",
    "P2_PLATFORM_FAILURE",
    "P2_SYNC_FAILURE",
    "P2_CLOUD_FAILURE",
    "P2_EXECUTOR_FAILURE",
    "P2_VALIDATION_FAILURE",
    "P2_UNMAPPED_ERROR",
]


class CoreErrorProjectionV1(BaseModel):
    """Safe core-facing projection; every projection is blocking."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    code: CoreProjectedErrorCode
    source_code: str
    message: str
    action: str
    blocking: Literal[True] = True


_KNOWN_ERROR_CODES: dict[str, CoreProjectedErrorCode] = {
    "provider.no_candidate": "P2_PROVIDER_FAILURE",
    "provider.timeout": "P2_PROVIDER_FAILURE",
    "provider.invoke_failed": "P2_PROVIDER_FAILURE",
    "provider.cost_unknown": "P2_PROVIDER_FAILURE",
    "provider.budget_exceeded": "P2_PROVIDER_FAILURE",
    "provider.adapter_error": "P2_PROVIDER_FAILURE",
    "provider.scope_mismatch": "P2_PROVIDER_FAILURE",
    "platform.unavailable": "P2_PLATFORM_FAILURE",
    "sync.conflict": "P2_SYNC_FAILURE",
    "cloud.rejected": "P2_CLOUD_FAILURE",
    "executor.unavailable": "P2_EXECUTOR_FAILURE",
    "validation.schema_mismatch": "P2_VALIDATION_FAILURE",
}


def project_p2_error(*, code: str, message: str) -> CoreErrorProjectionV1:
    """Map known codes explicitly and fail closed for every unknown code."""

    projected = _KNOWN_ERROR_CODES.get(code, "P2_UNMAPPED_ERROR")
    action = (
        "Review the P2 compatibility table before retrying"
        if projected == "P2_UNMAPPED_ERROR"
        else "Review the optional P2 operation and retry only after remediation"
    )
    return CoreErrorProjectionV1(
        code=projected,
        source_code=code,
        message=message,
        action=action,
    )
