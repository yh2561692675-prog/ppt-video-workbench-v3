from __future__ import annotations

import base64
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from workbench.updates.secure import (
    HttpResponse,
    MetadataSignature,
    SecureUpdateClient,
    SecureUpdateError,
    SignedMetadata,
    TrustedKey,
    TrustedRoot,
    UpdateTarget,
    canonical_json,
)


def _signed(signed: dict[str, object]) -> SignedMetadata:
    return SignedMetadata(
        signed=signed,
        signatures=[MetadataSignature(key_id="root-1", signature=base64.b64encode(b"ok").decode())],
    )


def _client(
    tmp_path: Path, responses: dict[str, HttpResponse], *, current: str = "1.0.0"
) -> SecureUpdateClient:
    def transport(url: str, _headers):
        return responses[url]

    return SecureUpdateClient(
        tmp_path,
        trusted_root=TrustedRoot(
            version=1,
            threshold=1,
            keys=[TrustedKey(key_id="root-1", public_key="unused")],
        ),
        verifier=lambda payload, signature, key: (
            payload and signature == b"ok" and key.key_id == "root-1"
        ),
        transport=transport,
        current_version=current,
        now=lambda: datetime(2026, 8, 10, tzinfo=UTC),
    )


def test_refresh_verifies_metadata_and_rejects_rollback(tmp_path: Path) -> None:
    future = (datetime(2026, 8, 11, tzinfo=UTC)).isoformat()
    responses = {
        "https://updates.example/timestamp.json": HttpResponse(
            status=200,
            body=json.dumps(
                {
                    "signed": {"role": "timestamp", "version": 1, "expires_at": future},
                    "signatures": [
                        {"key_id": "root-1", "signature": base64.b64encode(b"ok").decode()}
                    ],
                }
            ).encode(),
        ),
        "https://updates.example/snapshot.json": HttpResponse(
            status=200,
            body=json.dumps(
                {
                    "signed": {"role": "snapshot", "version": 1, "expires_at": future},
                    "signatures": [
                        {"key_id": "root-1", "signature": base64.b64encode(b"ok").decode()}
                    ],
                }
            ).encode(),
        ),
        "https://updates.example/targets.json": HttpResponse(
            status=200,
            body=json.dumps(
                {
                    "signed": {
                        "role": "targets",
                        "version": 1,
                        "expires_at": future,
                        "targets": [
                            {
                                "version": "1.1.0",
                                "channel": "stable",
                                "published_at": "2026-08-10T00:00:00Z",
                                "expires_at": future,
                                "size": 4,
                                "sha256": "0" * 64,
                                "url": "https://updates.example/1.1.0.package",
                            }
                        ],
                    },
                    "signatures": [
                        {"key_id": "root-1", "signature": base64.b64encode(b"ok").decode()}
                    ],
                }
            ).encode(),
        ),
    }
    candidate = _client(tmp_path, responses).refresh("https://updates.example")

    assert candidate is not None
    assert candidate.version == "1.1.0"

    rollback_client = _client(tmp_path, {})
    rollback_client.trusted_root.version = 2
    rollback = _signed({"role": "targets", "version": 1, "expires_at": future})
    with pytest.raises(SecureUpdateError, match="回退"):
        rollback_client.verify_metadata(rollback, "targets")


def test_download_resumes_and_verifies_hash(tmp_path: Path) -> None:
    payload = b"package-data"
    candidate = UpdateTarget(
        version="1.1.0",
        channel="stable",
        published_at=datetime(2026, 8, 10, tzinfo=UTC),
        expires_at=datetime(2026, 8, 11, tzinfo=UTC),
        size=len(payload),
        sha256=hashlib.sha256(payload).hexdigest(),
        url="https://updates.example/1.1.0.package",
    )
    client = _client(tmp_path, {})
    part = tmp_path / "updates" / "downloads" / "1.1.0.package.part"
    part.parent.mkdir(parents=True)
    part.write_bytes(payload[:4])
    part.with_suffix(part.suffix + ".json").write_text(
        json.dumps({"url": candidate.url, "sha256": candidate.sha256, "size": candidate.size}),
        encoding="utf-8",
    )
    seen_headers: list[dict[str, str]] = []

    def transport(_url: str, headers):
        seen_headers.append(dict(headers))
        return HttpResponse(status=206, body=payload[4:])

    client.transport = transport
    downloaded = client.download(candidate)

    assert downloaded.read_bytes() == payload
    assert seen_headers == [{"Range": "bytes=4-"}]


def test_download_rejects_http_urls(tmp_path: Path) -> None:
    candidate = UpdateTarget(
        version="1.1.0",
        channel="stable",
        published_at=datetime(2026, 8, 10, tzinfo=UTC),
        expires_at=datetime(2026, 8, 11, tzinfo=UTC),
        size=1,
        sha256="0" * 64,
        url="http://updates.example/1.1.0.package",
    )
    with pytest.raises(SecureUpdateError, match="HTTPS"):
        _client(tmp_path, {}).download(candidate)


def test_root_rotation_requires_newer_signed_root(tmp_path: Path) -> None:
    client = _client(tmp_path, {})
    client.verifier = lambda payload, signature, key: payload and signature == b"ok"
    rotated = SignedMetadata(
        signed={
            "role": "root",
            "version": 2,
            "expires_at": "2026-08-11T00:00:00Z",
            "threshold": 1,
            "keys": [{"key_id": "root-2", "public_key": "new-key"}],
        },
        signatures=[
            MetadataSignature(key_id="root-1", signature=base64.b64encode(b"ok").decode()),
            MetadataSignature(key_id="root-2", signature=base64.b64encode(b"ok").decode()),
        ],
    )

    root = client.rotate_root(rotated)

    assert root.version == 2
    assert root.keys[0].key_id == "root-2"


def test_canonical_json_is_stable() -> None:
    assert canonical_json({"b": 1, "a": 2}) == b'{"a":2,"b":1}'
