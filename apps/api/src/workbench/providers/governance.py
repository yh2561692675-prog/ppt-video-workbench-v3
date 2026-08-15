"""Durable provider budget reservations, billing reconciliation and rate limits."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from workbench.contracts.p2_platform import _ContractModel

from .billing import ProviderRateLimiter
from .policy import ProviderPolicyV1, failover_allowed

ReservationStatus = Literal["reserved", "committed", "released", "unknown"]


class CostReservationV1(_ContractModel):
    schema_version: Literal[1] = 1
    reservation_id: UUID
    operation_id: UUID
    provider_id: str = Field(min_length=1, max_length=128)
    capability_id: str = Field(min_length=1, max_length=100)
    scopes: list[str] = Field(min_length=1, max_length=16)
    reserved_cost_minor: int = Field(ge=0)
    committed_cost_minor: int | None = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    price_book_version: str = Field(min_length=1, max_length=100)
    status: ReservationStatus = "reserved"
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("created_at", "updated_at")
    @classmethod
    def _utc(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("timestamps must include UTC offset")
        return value.astimezone(UTC)


class GovernanceDecision(_ContractModel):
    schema_version: Literal[1] = 1
    allowed: bool
    reason: str
    reservation_id: UUID | None = None
    retry_after_seconds: float = Field(default=0.0, ge=0)
    remaining_minor: int | None = Field(default=None, ge=0)


class CostLedgerError(RuntimeError):
    pass


class PersistentCostLedger:
    """A small JSON ledger with atomic replacement and conservative recovery.

    Unknown billing is intentionally retained as a first-class state; callers
    must reconcile it before a reservation can release budget or permit a
    billed failover.
    """

    def __init__(self, path: Path, limits_minor: dict[str, int] | None = None) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        self._limits = dict(limits_minor or {})
        self._entries: dict[str, CostReservationV1] = {}
        self._load()

    def reserve(
        self,
        *,
        operation_id: UUID,
        provider_id: str,
        capability_id: str,
        amount_minor: int,
        scopes: tuple[str, ...],
        price_book_version: str,
        currency: str = "USD",
    ) -> CostReservationV1:
        if amount_minor < 0:
            raise CostLedgerError("amount_minor must not be negative")
        if not scopes:
            raise CostLedgerError("at least one budget scope is required")
        with self._lock:
            usage = self._scope_usage()
            for scope in scopes:
                limit = self._limits.get(scope)
                if limit is not None and usage.get(scope, 0) + amount_minor > limit:
                    raise CostLedgerError(f"budget_exceeded:{scope}")
            entry = CostReservationV1(
                reservation_id=uuid4(),
                operation_id=operation_id,
                provider_id=provider_id,
                capability_id=capability_id,
                scopes=list(scopes),
                reserved_cost_minor=amount_minor,
                price_book_version=price_book_version,
                currency=currency,
            )
            self._entries[str(entry.reservation_id)] = entry
            self._save()
            return entry

    def commit(self, reservation_id: UUID, billed_cost_minor: int) -> CostReservationV1:
        if billed_cost_minor < 0:
            raise CostLedgerError("billed cost must not be negative")
        with self._lock:
            entry = self._require(reservation_id)
            if entry.status not in {"reserved", "unknown"}:
                raise CostLedgerError("reservation is no longer open")
            if entry.status == "reserved" and billed_cost_minor > entry.reserved_cost_minor:
                raise CostLedgerError("billed cost exceeds reserved budget")
            updated = entry.model_copy(
                update={
                    "committed_cost_minor": billed_cost_minor,
                    "status": "committed",
                    "updated_at": datetime.now(UTC),
                }
            )
            self._entries[str(reservation_id)] = updated
            self._save()
            return updated

    def mark_unknown(self, reservation_id: UUID) -> CostReservationV1:
        with self._lock:
            entry = self._require(reservation_id)
            if entry.status != "reserved":
                raise CostLedgerError("only reserved entries can become unknown")
            updated = entry.model_copy(
                update={"status": "unknown", "updated_at": datetime.now(UTC)}
            )
            self._entries[str(reservation_id)] = updated
            self._save()
            return updated

    def release(self, reservation_id: UUID) -> CostReservationV1:
        with self._lock:
            entry = self._require(reservation_id)
            if entry.status == "unknown":
                raise CostLedgerError("unknown billing must be reconciled before release")
            if entry.status != "reserved":
                return entry
            updated = entry.model_copy(
                update={"status": "released", "updated_at": datetime.now(UTC)}
            )
            self._entries[str(reservation_id)] = updated
            self._save()
            return updated

    def get(self, reservation_id: UUID) -> CostReservationV1:
        with self._lock:
            return self._require(reservation_id)

    def list(self) -> list[CostReservationV1]:
        with self._lock:
            return sorted(self._entries.values(), key=lambda item: item.created_at)

    def remaining(self, scopes: tuple[str, ...]) -> int | None:
        with self._lock:
            values = [
                self._limits[scope] - self._scope_usage().get(scope, 0)
                for scope in scopes
                if scope in self._limits
            ]
            return min(values) if values else None

    def _require(self, reservation_id: UUID) -> CostReservationV1:
        try:
            return self._entries[str(reservation_id)]
        except KeyError as error:
            raise CostLedgerError("reservation_not_found") from error

    def _scope_usage(self) -> dict[str, int]:
        usage: dict[str, int] = {}
        for entry in self._entries.values():
            if entry.status in {"reserved", "unknown"}:
                for scope in entry.scopes:
                    usage[scope] = usage.get(scope, 0) + entry.reserved_cost_minor
            elif entry.status == "committed":
                committed = entry.committed_cost_minor or 0
                for scope in entry.scopes:
                    usage[scope] = usage.get(scope, 0) + committed
        return usage

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            entries = payload.get("entries", [])
            self._entries = {
                str(item["reservation_id"]): CostReservationV1.model_validate(item)
                for item in entries
            }
        except (OSError, ValueError, TypeError, KeyError) as error:
            raise CostLedgerError("cost_ledger_corrupt") from error

    def _save(self) -> None:
        payload = {
            "schema_version": 1,
            "entries": [item.model_dump(mode="json") for item in self._entries.values()],
        }
        fd, raw_path = tempfile.mkstemp(prefix=self.path.name + ".", dir=self.path.parent)
        temp_path = Path(raw_path)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, self.path)
        finally:
            if temp_path.exists():
                temp_path.unlink()


class ProviderGovernance:
    def __init__(
        self,
        ledger: PersistentCostLedger,
        *,
        rate_limiter: ProviderRateLimiter | None = None,
    ) -> None:
        self.ledger = ledger
        self.rate_limiter = rate_limiter or ProviderRateLimiter()

    def authorize(
        self,
        *,
        operation_id: UUID,
        provider_id: str,
        credential_ref: str,
        capability_id: str,
        estimated_cost_minor: int,
        scopes: tuple[str, ...],
        price_book_version: str,
    ) -> GovernanceDecision:
        rate = self.rate_limiter.consume(provider_id, credential_ref, capability_id)
        if not rate.allowed:
            return GovernanceDecision(
                allowed=False,
                reason="rate_limited",
                retry_after_seconds=rate.retry_after_seconds,
            )
        try:
            reservation = self.ledger.reserve(
                operation_id=operation_id,
                provider_id=provider_id,
                capability_id=capability_id,
                amount_minor=estimated_cost_minor,
                scopes=scopes,
                price_book_version=price_book_version,
            )
        except CostLedgerError as error:
            reason = str(error)
            return GovernanceDecision(allowed=False, reason=reason)
        return GovernanceDecision(
            allowed=True,
            reason="reserved",
            reservation_id=reservation.reservation_id,
            remaining_minor=self._remaining(scopes),
        )

    def complete(
        self,
        reservation_id: UUID,
        *,
        billing_state: Literal["known", "unknown", "none"],
        billed_cost_minor: int = 0,
    ) -> CostReservationV1:
        if billing_state == "unknown":
            return self.ledger.mark_unknown(reservation_id)
        if billing_state == "none":
            return self.ledger.release(reservation_id)
        return self.ledger.commit(reservation_id, billed_cost_minor)

    def may_failover(
        self,
        *,
        policy: ProviderPolicyV1,
        error_code: str,
        error_retryable: bool,
        billed_state: Literal["none", "known", "unknown"],
        fixed_provider: bool = False,
        region_would_expand: bool = False,
        budget_would_increase: bool = False,
    ) -> bool:
        return failover_allowed(
            policy=policy,
            error_code=error_code,
            error_retryable=error_retryable,
            billed_state=billed_state,
            fixed_provider=fixed_provider,
            region_would_expand=region_would_expand,
            budget_would_increase=budget_would_increase,
        )

    def _remaining(self, scopes: tuple[str, ...]) -> int | None:
        return self.ledger.remaining(scopes)
