from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from workbench.api.projects import Envelope, envelope
from workbench.integrations.heygen.client import (
    HeyGenClient,
    HeyGenIntegrationError,
    HeyGenVoice,
    SpeechResult,
)
from workbench.settings.heygen_store import HeyGenProfilePublic, HeyGenProfileStore
from workbench.settings.secret_store import SecretStoreUnavailable


class HeyGenProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    base_url: HttpUrl = HttpUrl("https://api.heygen.com")
    api_key: str = Field(min_length=1, max_length=4096, repr=False)


class HeyGenProfileUpdate(HeyGenProfileCreate):
    pass


class VoicePreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    voice_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=200)


def create_heygen_settings_router(store: HeyGenProfileStore, client: HeyGenClient) -> APIRouter:
    router = APIRouter(prefix="/api/settings/heygen-profiles")

    @router.post(
        "",
        status_code=status.HTTP_201_CREATED,
        response_model=Envelope[HeyGenProfilePublic],
    )
    def create_profile(request: HeyGenProfileCreate) -> Envelope[HeyGenProfilePublic]:
        try:
            return envelope(
                store.save(
                    name=request.name,
                    base_url=str(request.base_url),
                    api_key=request.api_key,
                )
            )
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.patch("/{profile_id}", response_model=Envelope[HeyGenProfilePublic])
    def update_profile(
        profile_id: UUID, request: HeyGenProfileUpdate
    ) -> Envelope[HeyGenProfilePublic]:
        try:
            return envelope(
                store.update(
                    profile_id,
                    name=request.name,
                    base_url=str(request.base_url),
                    api_key=request.api_key,
                )
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="HeyGen profile not found") from error
        except (ValueError, RuntimeError) as error:
            raise HTTPException(status_code=422, detail=str(error)) from error

    @router.get("", response_model=Envelope[list[HeyGenProfilePublic]])
    def list_profiles() -> Envelope[list[HeyGenProfilePublic]]:
        return envelope(store.list_profiles())

    @router.get("/{profile_id}/voices", response_model=Envelope[list[HeyGenVoice]])
    def list_voices(profile_id: UUID) -> Envelope[list[HeyGenVoice]]:
        try:
            credentials = store.credentials(profile_id)
            return envelope(
                client.list_voices(credentials.api_key, base_url=str(credentials.profile.base_url))
            )
        except KeyError as error:
            raise HTTPException(status_code=404, detail="HeyGen profile not found") from error
        except SecretStoreUnavailable as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "heygen_secret_store_unavailable",
                    "message": "无法解密 HeyGen 配置",
                    "action": "请在当前 Windows 用户下重新保存 HeyGen API Key",
                },
            ) from error
        except HeyGenIntegrationError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": error.code, "message": str(error), "action": error.action},
            ) from error

    @router.post("/{profile_id}/preview", response_model=Envelope[SpeechResult])
    def preview_voice(profile_id: UUID, request: VoicePreviewRequest) -> Envelope[SpeechResult]:
        try:
            credentials = store.credentials(profile_id)
            result = client.generate_speech(
                credentials.api_key,
                text=request.text,
                voice_id=request.voice_id,
                language="zh",
                base_url=str(credentials.profile.base_url),
            )
            store.mark_used(profile_id)
            return envelope(result)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="HeyGen profile not found") from error
        except SecretStoreUnavailable as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "heygen_secret_store_unavailable",
                    "message": "无法解密 HeyGen 配置",
                    "action": "请在当前 Windows 用户下重新保存 HeyGen API Key",
                },
            ) from error
        except HeyGenIntegrationError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": error.code, "message": str(error), "action": error.action},
            ) from error

    return router
