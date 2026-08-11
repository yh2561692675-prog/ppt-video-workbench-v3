"""Static, failure-isolated Provider descriptor registry."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from pydantic import ValidationError

from .models import ProviderDescriptorV1


class ProviderRegistryError(ValueError):
    """Raised when a registry mutation would make provider selection ambiguous."""


@dataclass(frozen=True)
class RegistryDiagnostic:
    provider_id: str
    code: str
    message: str


class ProviderRegistry:
    """In-memory registry populated only from reviewed static descriptors."""

    def __init__(self, descriptors: Iterable[ProviderDescriptorV1] = ()) -> None:
        self._descriptors: dict[str, ProviderDescriptorV1] = {}
        self._diagnostics: list[RegistryDiagnostic] = []
        for descriptor in descriptors:
            self.register(descriptor)

    @classmethod
    def load(
        cls, raw_descriptors: Iterable[object]
    ) -> tuple[ProviderRegistry, list[RegistryDiagnostic]]:
        registry = cls()
        for raw in raw_descriptors:
            provider_id = (
                str(raw.get("provider_id", "<unknown>")) if isinstance(raw, dict) else "<unknown>"
            )
            try:
                descriptor = ProviderDescriptorV1.model_validate(raw)
                registry.register(descriptor)
            except (ValidationError, ProviderRegistryError, AttributeError) as error:
                registry._diagnostics.append(
                    RegistryDiagnostic(provider_id, "invalid_descriptor", str(error)[:500])
                )
        return registry, list(registry._diagnostics)

    def register(self, descriptor: ProviderDescriptorV1) -> None:
        if descriptor.provider_id in self._descriptors:
            raise ProviderRegistryError(f"duplicate provider_id: {descriptor.provider_id}")
        if descriptor.execution_mode == "remote_https" and descriptor.trust != "builtin_signed":
            raise ProviderRegistryError("remote providers must use a signed built-in adapter")
        self._descriptors[descriptor.provider_id] = descriptor

    def get(self, provider_id: str) -> ProviderDescriptorV1 | None:
        return self._descriptors.get(provider_id)

    def require(self, provider_id: str) -> ProviderDescriptorV1:
        descriptor = self.get(provider_id)
        if descriptor is None:
            raise ProviderRegistryError(f"unknown provider_id: {provider_id}")
        return descriptor

    def list(
        self, *, kind: str | None = None, enabled_only: bool = True
    ) -> list[ProviderDescriptorV1]:
        values: Iterable[ProviderDescriptorV1] = self._descriptors.values()
        if enabled_only:
            values = (item for item in values if item.enabled)
        if kind is not None:
            values = (item for item in values if item.kind == kind)
        return sorted(values, key=lambda item: item.provider_id)

    @property
    def diagnostics(self) -> tuple[RegistryDiagnostic, ...]:
        return tuple(self._diagnostics)
