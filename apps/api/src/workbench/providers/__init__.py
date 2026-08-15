"""Versioned Provider Kernel primitives.

Only built-in, reviewed adapters are supported by this first implementation. The
package intentionally has no dynamic import or plugin execution path.
"""

from .api import ProviderApiState, create_provider_router
from .broker import ProviderBroker, RouteRequest
from .cache import ProviderCache, cache_identity
from .credentials import CredentialMetadataV1, InMemoryCredentialStore
from .governance import CostReservationV1, PersistentCostLedger, ProviderGovernance
from .models import (
    ProviderAuditEventV1,
    ProviderCapabilityV1,
    ProviderDescriptorV1,
    ProviderHealthV1,
    ProviderInvocationResultV1,
    ProviderKind,
)
from .policy import ProviderPolicyV1
from .probe import CapabilityProbeService
from .registry import ProviderRegistry
from .upstream import (
    BUILTIN_PROVIDER_SPECS,
    BrokerCompletionClient,
    BuiltinArtifactStore,
    BuiltinProviderAdapter,
    builtin_descriptors,
    create_llm_handler,
)
from .v2 import AdapterConformanceResultV1, ProviderOperationV2, ProviderRoutePolicyV2

__all__ = [
    "ProviderBroker",
    "ProviderApiState",
    "ProviderCache",
    "ProviderCapabilityV1",
    "ProviderAuditEventV1",
    "ProviderDescriptorV1",
    "ProviderHealthV1",
    "ProviderInvocationResultV1",
    "ProviderKind",
    "ProviderRegistry",
    "ProviderPolicyV1",
    "RouteRequest",
    "CapabilityProbeService",
    "CredentialMetadataV1",
    "InMemoryCredentialStore",
    "cache_identity",
    "CostReservationV1",
    "PersistentCostLedger",
    "ProviderGovernance",
    "ProviderRoutePolicyV2",
    "ProviderOperationV2",
    "AdapterConformanceResultV1",
    "create_provider_router",
    "BuiltinProviderAdapter",
    "BuiltinArtifactStore",
    "BrokerCompletionClient",
    "create_llm_handler",
    "BUILTIN_PROVIDER_SPECS",
    "builtin_descriptors",
]
