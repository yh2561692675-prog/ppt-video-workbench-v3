from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


class AssetKind(StrEnum):
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    PRESENTATION = "presentation"
    LOGO = "logo"
    STICKER = "sticker"
    ICON = "icon"
    FONT = "font"
    LUT = "lut"


class LicenseStatus(StrEnum):
    UNKNOWN = "unknown"
    CONFIRMED = "confirmed"
    EXPIRED = "expired"
    BLOCKED = "blocked"


class AssetModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LicenseRecord(AssetModel):
    status: LicenseStatus = LicenseStatus.UNKNOWN
    source: str | None = Field(default=None, max_length=500)
    owner: str | None = Field(default=None, max_length=200)
    license_name: str | None = Field(default=None, max_length=200)
    license_reference: str | None = Field(default=None, max_length=500)
    project_ids: list[UUID] = Field(default_factory=list)
    expires_at: datetime | None = None
    confirmed_by: str | None = Field(default=None, max_length=120)
    confirmed_at: datetime | None = None

    @model_validator(mode="after")
    def validate_expiry(self) -> LicenseRecord:
        if self.status is LicenseStatus.CONFIRMED and self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise ValueError("confirmed license expiry must include timezone")
            if self.expires_at <= datetime.now(UTC):
                raise ValueError("confirmed license is already expired")
        return self


class DerivedAssetRef(AssetModel):
    asset_id: UUID
    operation: Literal["proxy", "thumbnail", "crop", "remove_background", "transcode"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    tool_version: str = Field(min_length=1, max_length=80)


class AssetRecord(AssetModel):
    schema_version: Literal["1.0"] = "1.0"
    asset_id: UUID = Field(default_factory=uuid4)
    revision: int = Field(default=1, ge=1)
    project_id: UUID
    kind: AssetKind
    content_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    relative_object_path: str = Field(min_length=1, max_length=500)
    original_name: str = Field(min_length=1, max_length=255)
    mime_type: str = Field(min_length=1, max_length=120)
    size_bytes: int = Field(ge=0)
    duration_us: int | None = Field(default=None, ge=0)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    fps_num: int | None = Field(default=None, gt=0)
    fps_den: int | None = Field(default=None, gt=0)
    alpha_mode: Literal["none", "straight", "premultiplied"] = "none"
    license: LicenseRecord = Field(default_factory=LicenseRecord)
    tags: list[str] = Field(default_factory=list)
    brand_pack_id: UUID | None = None
    derived_from: UUID | None = None
    operation: str | None = Field(default=None, max_length=80)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_relative_object_path(self) -> AssetRecord:
        path = Path(self.relative_object_path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("asset object path must be relative")
        return self


class AssetImportRequest(AssetModel):
    relative_path: str = Field(min_length=1, max_length=500)
    kind: AssetKind
    original_name: str | None = Field(default=None, max_length=255)
    mime_type: str = Field(default="application/octet-stream", max_length=120)
    license: LicenseRecord = Field(default_factory=LicenseRecord)
    tags: list[str] = Field(default_factory=list, max_length=50)
    brand_pack_id: UUID | None = None


class AssetDeriveRequest(AssetModel):
    parent_asset_id: UUID
    operation: Literal["proxy", "thumbnail", "crop", "remove_background", "transcode"]
    parameters: dict[str, Any] = Field(default_factory=dict)
    tool_version: str = Field(default="asset-tools-v1", min_length=1, max_length=80)


class BrandPack(AssetModel):
    brand_pack_id: UUID = Field(default_factory=uuid4)
    revision: int = Field(default=1, ge=1)
    project_id: UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    asset_ids: list[UUID] = Field(default_factory=list)
    colors: dict[str, str] = Field(default_factory=dict)
    locked_asset_ids: list[UUID] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
