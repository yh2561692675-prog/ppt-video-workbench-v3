"""Cross-platform foundation services and composition root."""

from .composition import create_platform_services
from .models import PlatformCapabilitySnapshotV1, PlatformInfoV1, ToolInfoV1
from .protocols import PlatformServices

__all__ = [
    "PlatformCapabilitySnapshotV1",
    "PlatformInfoV1",
    "PlatformServices",
    "ToolInfoV1",
    "create_platform_services",
]
