"""Optional desktop sync primitives kept outside the local project manifest."""

from .client import SyncBatchResult, SyncClient, SyncClientState, SyncTransport, SyncTransportError

__all__ = [
    "SyncBatchResult",
    "SyncClient",
    "SyncClientState",
    "SyncTransport",
    "SyncTransportError",
]
