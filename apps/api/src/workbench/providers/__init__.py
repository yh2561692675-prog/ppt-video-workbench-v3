"""Versioned Provider Kernel primitives.

Only built-in, reviewed adapters are supported by this first implementation. The
package intentionally has no dynamic import or plugin execution path.
"""

from .api import ProviderApiState, create_provider_router
from .broker import ProviderBroker, RouteRequest
from .cache import ProviderCache, cache_identity
from .credentials import CredentialMetadataV1, InMemoryCredentialStore
from .models import (
    ProviderCapabilityV1,
    ProviderDescriptorV1,
    ProviderHealthV1,
    ProviderInvocationResultV1,
    ProviderKind,
)
from .policy import ProviderPolicyV1
from .probe import CapabilityProbeService
from .registry import ProviderRegistry

__all__ = [
    "ProviderBroker",
    "ProviderApiState",
    "ProviderCache",
    "ProviderCapabilityV1",
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
    "create_provider_router",
]
