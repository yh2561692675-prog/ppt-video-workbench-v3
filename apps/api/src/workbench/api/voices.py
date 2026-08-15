"""HTTP surface for local voice identity and authorization management."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from workbench.voices.models import VoiceAuthorizationV1, VoiceIdentityV1
from workbench.voices.repository import VoiceRepositoryError
from workbench.voices.service import VoiceAuthorizationService

from .projects import Envelope, envelope


def create_voices_router(service: VoiceAuthorizationService) -> APIRouter:
    router = APIRouter(prefix="/api/ai/voices")

    @router.get("", response_model=Envelope[list[VoiceIdentityV1]])
    def list_voices() -> Envelope[list[VoiceIdentityV1]]:
        return envelope(service.repository.list_voices())

    @router.post(
        "/authorizations",
        status_code=status.HTTP_201_CREATED,
        response_model=Envelope[VoiceAuthorizationV1],
    )
    def grant_authorization(
        authorization: VoiceAuthorizationV1,
    ) -> Envelope[VoiceAuthorizationV1]:
        try:
            return envelope(service.grant(authorization))
        except VoiceRepositoryError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[VoiceIdentityV1])
    def register_voice(voice: VoiceIdentityV1) -> Envelope[VoiceIdentityV1]:
        try:
            return envelope(service.register_voice(voice))
        except VoiceRepositoryError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    @router.post("/{voice_id}/revoke", response_model=Envelope[VoiceIdentityV1])
    def revoke_voice(voice_id: str) -> Envelope[VoiceIdentityV1]:
        try:
            return envelope(service.revoke(voice_id))
        except VoiceRepositoryError as error:
            raise HTTPException(status_code=404, detail=str(error)) from error

    return router
