"""Versioned provider prices, hierarchical budgets and token-bucket limits."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from threading import Lock, RLock

from pydantic import Field

from workbench.contracts.p2_platform import _ContractModel


class PriceLineV1(_ContractModel):
    provider_id: str
    capability_id: str
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    unit: str = Field(min_length=1, max_length=100)
    unit_price_minor: Decimal = Field(ge=0, decimal_places=6)
    price_book_version: str = Field(min_length=1, max_length=100)


class PriceBookV1(_ContractModel):
    schema_version: int = 1
    version: str = Field(min_length=1, max_length=100)
    effective_at: datetime
    lines: list[PriceLineV1] = Field(min_length=1, max_length=10_000)

    def estimate(self, provider_id: str, capability_id: str, units: Decimal) -> PriceLineV1 | None:
        if units < 0:
            raise ValueError("units must not be negative")
        for line in self.lines:
            if line.provider_id == provider_id and line.capability_id == capability_id:
                amount = (line.unit_price_minor * units).quantize(
                    Decimal("0.000001"), rounding=ROUND_HALF_UP
                )
                return line.model_copy(update={"unit_price_minor": amount})
        return None


@dataclass(frozen=True)
class BudgetDecision:
    allowed: bool
    scope: str
    requested_minor: int
    remaining_minor: int
    reason: str | None = None


class BudgetLedger:
    """Atomic in-process reservation ledger; persistent storage is a later platform task."""

    def __init__(self, limits_minor: dict[str, int]) -> None:
        if any(value < 0 for value in limits_minor.values()):
            raise ValueError("budget limits must not be negative")
        self._limits = dict(limits_minor)
        self._reserved: dict[str, int] = {scope: 0 for scope in limits_minor}
        self._lock = RLock()

    def reserve(self, requested_minor: int, *, scopes: tuple[str, ...]) -> BudgetDecision:
        if requested_minor < 0:
            raise ValueError("requested budget must not be negative")
        with self._lock:
            for scope in scopes:
                if scope not in self._limits:
                    continue
                remaining = self._limits[scope] - self._reserved[scope]
                if requested_minor > remaining:
                    return BudgetDecision(
                        False, scope, requested_minor, remaining, "budget_exceeded"
                    )
            for scope in scopes:
                if scope in self._reserved:
                    self._reserved[scope] += requested_minor
            return BudgetDecision(
                True, scopes[0] if scopes else "none", requested_minor, self.remaining(scopes)
            )

    def release(self, amount_minor: int, *, scopes: tuple[str, ...]) -> None:
        with self._lock:
            for scope in scopes:
                if scope in self._reserved:
                    self._reserved[scope] = max(0, self._reserved[scope] - amount_minor)

    def remaining(self, scopes: tuple[str, ...]) -> int:
        values = [
            self._limits[scope] - self._reserved[scope] for scope in scopes if scope in self._limits
        ]
        return min(values) if values else 2**63 - 1


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: float
    remaining_tokens: float


class TokenBucket:
    def __init__(self, capacity: float, refill_per_second: float) -> None:
        if capacity <= 0 or refill_per_second <= 0:
            raise ValueError("token bucket parameters must be positive")
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self.tokens = capacity
        self.updated_at = datetime.now(UTC).timestamp()
        self._lock = Lock()

    def consume(self, tokens: float = 1.0, *, now: float | None = None) -> RateLimitDecision:
        if tokens <= 0:
            raise ValueError("tokens must be positive")
        current = datetime.now(UTC).timestamp() if now is None else now
        with self._lock:
            elapsed = max(0.0, current - self.updated_at)
            self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_second)
            self.updated_at = current
            if self.tokens >= tokens:
                self.tokens -= tokens
                return RateLimitDecision(True, 0.0, self.tokens)
            return RateLimitDecision(
                False,
                (tokens - self.tokens) / self.refill_per_second,
                self.tokens,
            )


class ProviderRateLimiter:
    def __init__(self, *, capacity: float = 10, refill_per_second: float = 1) -> None:
        self.capacity = capacity
        self.refill_per_second = refill_per_second
        self._buckets: dict[tuple[str, str, str], TokenBucket] = {}
        self._lock = Lock()

    def consume(
        self, provider_id: str, credential_ref: str, capability_id: str
    ) -> RateLimitDecision:
        key = (provider_id, credential_ref, capability_id)
        with self._lock:
            bucket = self._buckets.setdefault(
                key, TokenBucket(self.capacity, self.refill_per_second)
            )
        return bucket.consume()
