"""Versioned S0 contracts shared by the host, modules, and adapter."""

from peripheral_contracts.business_results import BusinessArtifact, BusinessResultManifest
from peripheral_contracts.enums import ActionType, ErrorCategory, JobStatus
from peripheral_contracts.models import (
    ActionRequest,
    ArtifactManifest,
    ArtifactRef,
    ErrorDetail,
    EventEnvelope,
    JobEnvelope,
    JobResult,
    JobStatusResponse,
    ModuleManifest,
    OutputArtifact,
    StrictModel,
)
from peripheral_contracts.versioning import (
    SCHEMA_VERSION,
    UnsupportedSchemaVersion,
    require_supported_major,
)

__all__ = [
    "SCHEMA_VERSION",
    "ActionRequest",
    "ActionType",
    "ArtifactManifest",
    "ArtifactRef",
    "BusinessArtifact",
    "BusinessResultManifest",
    "ErrorCategory",
    "ErrorDetail",
    "EventEnvelope",
    "JobEnvelope",
    "JobResult",
    "JobStatus",
    "JobStatusResponse",
    "ModuleManifest",
    "OutputArtifact",
    "StrictModel",
    "UnsupportedSchemaVersion",
    "require_supported_major",
]
