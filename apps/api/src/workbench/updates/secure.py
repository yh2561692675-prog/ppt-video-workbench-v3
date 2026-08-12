from __future__ import annotations

import base64
import hashlib
import json
import shutil
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class SecureUpdateError(RuntimeError):
    def __init__(self, code: str, message: str, action: str = "请检查更新源后重试") -> None:
        super().__init__(message)
        self.code = code
        self.action = action


class UpdateOperationStatus(StrEnum):
    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    STAGED = "staged"
    APPLYING = "applying"
    VERIFYING = "verifying"
    APPLIED = "applied"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class UpdateOperationState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: UUID = Field(default_factory=uuid4)
    status: UpdateOperationStatus = UpdateOperationStatus.IDLE
    current_version: str
    candidate_version: str | None = None
    downloaded_bytes: int = Field(default=0, ge=0)
    total_bytes: int | None = Field(default=None, ge=0)
    package_path: str | None = None
    error_code: str | None = None
    error: str | None = None
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class MetadataSignature(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=120)
    signature: str = Field(min_length=1, max_length=512)


class SignedMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signed: dict[str, Any]
    signatures: list[MetadataSignature] = Field(min_length=1)


class TrustedKey(BaseModel):
    model_config = ConfigDict(extra="forbid")

    key_id: str = Field(min_length=1, max_length=120)
    public_key: str = Field(min_length=1, max_length=200)


class TrustedRoot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = Field(ge=1)
    threshold: int = Field(ge=1)
    keys: list[TrustedKey] = Field(min_length=1)

    def key_map(self) -> dict[str, TrustedKey]:
        return {key.key_id: key for key in self.keys}


class UpdateTarget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1, max_length=40)
    channel: str = Field(min_length=1, max_length=20)
    published_at: datetime
    expires_at: datetime
    min_supported_version: str = "0.0.0"
    size: int = Field(ge=0)
    sha256: str = Field(pattern=r"^[0-9a-fA-F]{64}$")
    url: str = Field(min_length=1, max_length=2_000)
    runtime_manifest_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")


class HttpResponse(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True, extra="forbid")

    status: int
    headers: dict[str, str] = Field(default_factory=dict)
    body: bytes


class HttpTransport(Protocol):
    def __call__(self, url: str, headers: Mapping[str, str]) -> HttpResponse: ...


SignatureVerifier = Callable[[bytes, bytes, TrustedKey], bool]


class SecureUpdateClient:
    """Verify signed update metadata and download artifacts safely.

    Network access is injected, which makes the trust boundary testable and
    allows the desktop shell to provide its own proxy/certificate policy.
    """

    def __init__(
        self,
        root: Path,
        *,
        trusted_root: TrustedRoot,
        verifier: SignatureVerifier | None = None,
        transport: HttpTransport | None = None,
        current_version: str = "0.1.1",
        now: Callable[[], datetime] | None = None,
        max_package_bytes: int = 2 * 1024 * 1024 * 1024,
    ) -> None:
        self.root = root.resolve()
        self.trusted_root = trusted_root
        self.verifier = verifier or verify_ed25519
        self.transport = transport or _http_transport
        self.current_version = current_version
        self.now = now or (lambda: datetime.now(UTC))
        self.max_package_bytes = max_package_bytes
        self.state_store = UpdateStateStore(self.root / "updates" / "state.json")
        self._candidate: UpdateTarget | None = None
        self.state_store.write(UpdateOperationState(current_version=current_version))

    def verify_metadata(self, envelope: SignedMetadata, role: str) -> dict[str, Any]:
        signed = envelope.signed
        version = _positive_int(signed.get("version"), "metadata_version_invalid")
        if version < self.trusted_root.version:
            raise SecureUpdateError(
                "update_metadata_rollback", "更新元数据版本回退", "清理旧元数据后重试"
            )
        expires_at = _parse_time(signed.get("expires_at"))
        if expires_at <= self.now():
            raise SecureUpdateError(
                "update_metadata_expired", "更新元数据已过期", "等待发布者生成新的元数据"
            )
        role_value = signed.get("role", role)
        if role_value != role:
            raise SecureUpdateError("update_metadata_role_invalid", "更新元数据角色不匹配")
        valid = 0
        keys = self.trusted_root.key_map()
        payload = canonical_json(signed)
        for signature in envelope.signatures:
            key = keys.get(signature.key_id)
            if key is None:
                continue
            try:
                signature_bytes = base64.b64decode(signature.signature, validate=True)
            except (ValueError, TypeError):
                continue
            if self.verifier(payload, signature_bytes, key):
                valid += 1
        if valid < self.trusted_root.threshold:
            raise SecureUpdateError(
                "update_signature_invalid",
                "更新元数据签名数量不足或签名无效",
                "获取可信发布源后重试",
            )
        return signed

    def rotate_root(self, envelope: SignedMetadata) -> TrustedRoot:
        signed = self.verify_metadata(envelope, "root")
        try:
            next_root = TrustedRoot.model_validate(
                {
                    "version": signed["version"],
                    "threshold": signed["threshold"],
                    "keys": signed["keys"],
                }
            )
        except (KeyError, ValueError) as error:
            raise SecureUpdateError(
                "update_root_invalid", "根密钥轮换元数据无效", "获取新的可信根元数据"
            ) from error
        if next_root.version <= self.trusted_root.version:
            raise SecureUpdateError("update_metadata_rollback", "根密钥版本回退", "拒绝旧根密钥")
        next_payload = canonical_json(signed)
        next_valid = 0
        next_keys = next_root.key_map()
        for signature in envelope.signatures:
            key = next_keys.get(signature.key_id)
            if key is None:
                continue
            try:
                signature_bytes = base64.b64decode(signature.signature, validate=True)
            except (ValueError, TypeError):
                continue
            if self.verifier(next_payload, signature_bytes, key):
                next_valid += 1
        if next_valid < next_root.threshold:
            raise SecureUpdateError(
                "update_root_dual_signature_invalid",
                "根密钥轮换缺少新根密钥签名",
                "重新获取同时由旧根和新根签名的轮换元数据",
            )
        self.trusted_root = next_root
        return next_root

    def refresh(self, metadata_url: str) -> UpdateTarget | None:
        self._set_status(UpdateOperationStatus.CHECKING)
        timestamp = self._fetch_metadata(metadata_url, "timestamp")
        timestamp_signed = self.verify_metadata(timestamp, "timestamp")
        snapshot = self._fetch_metadata(metadata_url, "snapshot")
        snapshot_signed = self.verify_metadata(snapshot, "snapshot")
        _check_meta_reference(timestamp_signed, "snapshot.json", snapshot)
        targets = self._fetch_metadata(metadata_url, "targets")
        signed_targets = self.verify_metadata(targets, "targets")
        _check_meta_reference(snapshot_signed, "targets.json", targets)
        target_items = signed_targets.get("targets", [])
        if not isinstance(target_items, list):
            raise SecureUpdateError("update_targets_invalid", "targets 元数据格式无效")
        candidates = [UpdateTarget.model_validate(item) for item in target_items]
        current = self.state_store.read().current_version
        available = next(
            (
                candidate
                for candidate in candidates
                if candidate.channel == "stable"
                and _version_key(candidate.version) > _version_key(current)
                and _version_key(candidate.min_supported_version) <= _version_key(current)
                and candidate.expires_at > self.now()
            ),
            None,
        )
        if available is None:
            self._candidate = None
            self._set_status(UpdateOperationStatus.IDLE, candidate_version=None)
            return None
        self._candidate = available
        self._set_status(UpdateOperationStatus.AVAILABLE, candidate_version=available.version)
        return available

    @property
    def candidate(self) -> UpdateTarget | None:
        return self._candidate

    def download(self, candidate: UpdateTarget) -> Path:
        _require_https(candidate.url)
        if candidate.size > self.max_package_bytes:
            raise SecureUpdateError(
                "update_package_too_large",
                "更新包超过本地安全大小上限",
                "选择较小的稳定更新包",
            )
        if shutil.disk_usage(self.root).free < candidate.size * 2:
            raise SecureUpdateError(
                "update_disk_space_low",
                "磁盘空间不足以安全下载更新包",
                "清理空间后重新下载",
            )
        downloads = self.root / "updates" / "downloads"
        downloads.mkdir(parents=True, exist_ok=True)
        final_path = downloads / f"{candidate.version}.package"
        part_path = final_path.with_suffix(final_path.suffix + ".part")
        sidecar_path = part_path.with_suffix(part_path.suffix + ".json")
        offset = 0
        if part_path.is_file() and sidecar_path.is_file():
            try:
                sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
                if sidecar == {
                    "url": candidate.url,
                    "sha256": candidate.sha256,
                    "size": candidate.size,
                }:
                    offset = part_path.stat().st_size
                else:
                    part_path.unlink(missing_ok=True)
                    sidecar_path.unlink(missing_ok=True)
            except (OSError, ValueError):
                part_path.unlink(missing_ok=True)
                sidecar_path.unlink(missing_ok=True)
        sidecar_path.write_text(
            json.dumps(
                {"url": candidate.url, "sha256": candidate.sha256, "size": candidate.size},
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        headers = {"Range": f"bytes={offset}-"} if offset else {}
        self._set_status(
            UpdateOperationStatus.DOWNLOADING,
            candidate_version=candidate.version,
            downloaded_bytes=offset,
            total_bytes=candidate.size,
        )
        response = self.transport(candidate.url, headers)
        if response.status not in {200, 206}:
            raise SecureUpdateError(
                "update_download_interrupted", "更新包下载失败", "检查网络后继续下载"
            )
        if offset and response.status == 200:
            offset = 0
        mode = "ab" if offset and response.status == 206 else "wb"
        with part_path.open(mode) as handle:
            handle.write(response.body)
        downloaded = part_path.stat().st_size
        self._set_status(UpdateOperationStatus.DOWNLOADING, downloaded_bytes=downloaded)
        if downloaded != candidate.size:
            raise SecureUpdateError(
                "update_download_interrupted", "更新包尚未下载完整", "继续下载或重新开始"
            )
        if _file_sha256(part_path) != candidate.sha256.lower():
            part_path.unlink(missing_ok=True)
            sidecar_path.unlink(missing_ok=True)
            raise SecureUpdateError(
                "update_package_hash_mismatch", "更新包哈希校验失败", "删除损坏包后重新下载"
            )
        part_path.replace(final_path)
        sidecar_path.unlink(missing_ok=True)
        self._set_status(
            UpdateOperationStatus.DOWNLOADED,
            package_path=final_path.as_posix(),
            downloaded_bytes=downloaded,
        )
        return final_path

    def _fetch_metadata(self, base_url: str, role: str) -> SignedMetadata:
        url = base_url.rstrip("/") + f"/{role}.json"
        _require_https(url)
        response = self.transport(url, {})
        if response.status != 200:
            raise SecureUpdateError("update_metadata_unavailable", "更新元数据获取失败")
        try:
            return SignedMetadata.model_validate(json.loads(response.body.decode("utf-8")))
        except (UnicodeDecodeError, ValueError) as error:
            raise SecureUpdateError("update_metadata_invalid", "更新元数据格式无效") from error

    def _set_status(self, status: UpdateOperationStatus, **updates: object) -> None:
        current = self.state_store.read()
        self.state_store.write(
            current.model_copy(update={"status": status, "updated_at": self.now(), **updates})
        )


class UpdateStateStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> UpdateOperationState:
        if not self.path.is_file():
            return UpdateOperationState(current_version="0.0.0")
        try:
            return UpdateOperationState.model_validate_json(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise SecureUpdateError(
                "update_state_invalid", "更新状态文件无效", "清理更新状态后重试"
            ) from error

    def write(self, state: UpdateOperationState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(state.model_dump_json(indent=2) + "\n", encoding="utf-8")
        temporary.replace(self.path)


def canonical_json(value: Mapping[str, Any]) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def verify_ed25519(payload: bytes, signature: bytes, key: TrustedKey) -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as error:
        raise SecureUpdateError(
            "update_crypto_unavailable",
            "当前运行时缺少 Ed25519 校验组件",
            "安装带安全更新依赖的正式运行时",
        ) from error
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            base64.b64decode(key.public_key, validate=True)
        )
        public_key.verify(signature, payload)
    except (ValueError, TypeError):
        return False
    return True


def _http_transport(url: str, headers: Mapping[str, str]) -> HttpResponse:
    request = urllib.request.Request(url, headers=dict(headers), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return HttpResponse(
                status=response.status,
                headers={key.lower(): value for key, value in response.headers.items()},
                body=response.read(),
            )
    except (urllib.error.URLError, OSError) as error:
        raise SecureUpdateError(
            "update_network_failed", "更新源网络请求失败", "检查网络后重试"
        ) from error


def _require_https(url: str) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme.lower() != "https" or not parsed.netloc:
        raise SecureUpdateError(
            "update_url_not_https", "更新地址必须使用 HTTPS", "改用受信任的 HTTPS 更新源"
        )


def _parse_time(value: object) -> datetime:
    if not isinstance(value, str):
        raise SecureUpdateError("update_metadata_invalid", "元数据过期时间无效")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise SecureUpdateError("update_metadata_invalid", "元数据过期时间无效") from error
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _positive_int(value: object, code: str) -> int:
    if not isinstance(value, int) or value < 1:
        raise SecureUpdateError(code, "元数据版本无效")
    return value


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_meta_reference(parent: Mapping[str, Any], filename: str, child: SignedMetadata) -> None:
    meta = parent.get("meta")
    if not isinstance(meta, dict):
        return
    reference = meta.get(filename)
    if not isinstance(reference, dict):
        return
    expected_version = reference.get("version")
    actual_version = child.signed.get("version")
    if expected_version is not None and expected_version != actual_version:
        raise SecureUpdateError("update_metadata_reference_invalid", "更新元数据版本引用不一致")
    expected_hash = reference.get("sha256")
    if expected_hash:
        actual_hash = hashlib.sha256(canonical_json(child.model_dump(mode="json"))).hexdigest()
        if str(expected_hash).lower() != actual_hash:
            raise SecureUpdateError("update_metadata_reference_invalid", "更新元数据哈希引用不一致")


def _version_key(value: str) -> tuple[int, ...]:
    values: list[int] = []
    for token in value.replace("-", ".").split("."):
        digits = "".join(character for character in token if character.isdigit())
        values.append(int(digits or 0))
    return tuple(values)
