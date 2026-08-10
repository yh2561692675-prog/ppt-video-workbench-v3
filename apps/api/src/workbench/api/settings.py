from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from workbench.api.projects import Envelope, envelope
from workbench.integrations.llm.client import LlmClient, LlmIntegrationError
from workbench.settings.secret_store import LlmProfilePublic, LlmProfileStore


class LlmProfileCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=80)
    base_url: HttpUrl
    api_key: str = Field(min_length=1, max_length=4096, repr=False)
    model: str = Field(min_length=1, max_length=160)


class ConnectionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ok: bool
    profile_id: UUID
    model: str


def create_settings_router(store: LlmProfileStore, client: LlmClient) -> APIRouter:
    router = APIRouter(prefix="/api/settings/llm-profiles")

    @router.post("", status_code=status.HTTP_201_CREATED, response_model=Envelope[LlmProfilePublic])
    def create_profile(request: LlmProfileCreate) -> Envelope[LlmProfilePublic]:
        try:
            return envelope(
                store.save(
                    name=request.name,
                    base_url=str(request.base_url),
                    api_key=request.api_key,
                    model=request.model,
                )
            )
        except (ValueError, RuntimeError) as error:
            raise HTTPException(
                status_code=422,
                detail={
                    "code": "llm_profile_save_failed",
                    "message": "无法安全保存模型配置",
                    "action": "请在 Windows 环境检查本机凭证保护后重试",
                },
            ) from error

    @router.get("", response_model=Envelope[list[LlmProfilePublic]])
    def list_profiles() -> Envelope[list[LlmProfilePublic]]:
        return envelope(store.list_profiles())

    @router.post("/{profile_id}/test", response_model=Envelope[ConnectionResult])
    def test_profile(profile_id: UUID) -> Envelope[ConnectionResult]:
        try:
            credentials = store.credentials(profile_id)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="LLM profile not found") from error
        try:
            client.test_connection(
                base_url=str(credentials.profile.base_url).rstrip("/"),
                api_key=credentials.api_key,
                model=credentials.profile.model,
            )
        except LlmIntegrationError as error:
            raise HTTPException(
                status_code=422,
                detail={"code": error.code, "message": str(error), "action": error.action},
            ) from error
        store.mark_used(profile_id)
        return envelope(
            ConnectionResult(ok=True, profile_id=profile_id, model=credentials.profile.model)
        )

    return router
