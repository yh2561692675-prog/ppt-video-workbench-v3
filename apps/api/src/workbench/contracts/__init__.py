"""Versioned cross-cutting contracts shared by the P2 platform lines."""

from .p2_platform import (
    BudgetV1,
    LogicalResourceRefV1,
    OperationContextV1,
    StructuredErrorV1,
    canonical_json,
    canonical_sha256,
)

__all__ = [
    "BudgetV1",
    "LogicalResourceRefV1",
    "OperationContextV1",
    "StructuredErrorV1",
    "canonical_json",
    "canonical_sha256",
]

