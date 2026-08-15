"""Manual reconciliation endpoint for unknown provider billing."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from workbench.providers.governance import CostLedgerError, ProviderGovernance

from .projects import Envelope, envelope


class BillingReconcileRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    billed_cost_minor: int = Field(ge=0)


def create_provider_governance_router(governance: ProviderGovernance) -> APIRouter:
    router = APIRouter(prefix="/api/providers/governance")

    @router.post("/{reservation_id}/reconcile", response_model=Envelope[object])
    def reconcile(
        reservation_id: UUID, request: BillingReconcileRequest
    ) -> Envelope[object]:
        try:
            entry = governance.complete(
                reservation_id,
                billing_state="known",
                billed_cost_minor=request.billed_cost_minor,
            )
        except CostLedgerError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        return envelope(entry)

    return router
