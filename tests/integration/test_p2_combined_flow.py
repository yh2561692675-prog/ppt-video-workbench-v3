from __future__ import annotations

import hashlib
from pathlib import Path
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from workbench.contracts.p2_platform import canonical_sha256
from workbench.sync import HttpSyncTransport, SyncClient

from cloud_prototype.app import create_cloud_app


def test_synced_revision_runs_remote_job_and_second_device_pulls_candidate(
    tmp_path: Path,
) -> None:
    app = create_cloud_app(tmp_path / "control.db", tmp_path / "objects")
    with TestClient(app) as api:
        alice = {"X-Actor-ID": "alice"}
        bob = {"X-Actor-ID": "bob"}
        workspace_id = api.post(
            "/v1/workspaces", json={"name": "Integration"}, headers=alice
        ).json()["workspace_id"]
        project = api.post(
            f"/v1/workspaces/{workspace_id}/projects",
            json={"name": "Course", "manifest": {"pages": []}},
            headers=alice,
        ).json()
        project_id = project["project_id"]
        assert (
            api.post(
                f"/v1/workspaces/{workspace_id}/members",
                json={"actor_id": "bob", "role": "editor"},
                headers=alice,
            ).status_code
            == 201
        )
        device_a_id, device_b_id = str(uuid4()), str(uuid4())
        for actor_headers, device_id, platform in (
            (alice, device_a_id, "windows"),
            (bob, device_b_id, "linux"),
        ):
            assert (
                api.post(
                    "/v1/devices",
                    json={"device_id": device_id, "name": platform, "platform": platform},
                    headers=actor_headers,
                ).status_code
                == 201
            )

        def bridge(request: httpx.Request) -> httpx.Response:
            path = request.url.path
            if request.url.query:
                path += "?" + request.url.query.decode()
            forwarded = {
                key: request.headers[key]
                for key in (
                    "x-actor-id",
                    "x-device-id",
                    "content-type",
                    "idempotency-key",
                )
                if key in request.headers
            }
            response = api.request(
                request.method, path, headers=forwarded, content=request.content
            )
            return httpx.Response(
                response.status_code,
                headers=dict(response.headers),
                content=response.content,
                request=request,
            )

        def candidate_download(object_id: str) -> bytes:
            response = api.get(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/"
                f"{object_id}/content",
                headers=bob,
            )
            assert response.status_code == 200
            return response.content

        transport_a = HttpSyncTransport(
            "https://cloud.example.test",
            workspace_id=workspace_id,
            project_id=project_id,
            actor_id="alice",
            device_id=device_a_id,
            transport=httpx.MockTransport(bridge),
        )
        transport_b = HttpSyncTransport(
            "https://cloud.example.test",
            workspace_id=workspace_id,
            project_id=project_id,
            actor_id="bob",
            device_id=device_b_id,
            object_downloader=candidate_download,
            transport=httpx.MockTransport(bridge),
        )
        desktop_a = SyncClient(tmp_path / "device-a.db", enabled=True)
        desktop_b = SyncClient(tmp_path / "device-b.db", enabled=True)
        try:
            operation_payload = {
                "clip_id": str(uuid4()),
                "patch": {"text": "render this revision"},
            }
            operation = {
                "schema_version": 1,
                "operation_id": str(uuid4()),
                "idempotency_key": str(uuid4()),
                "attempt_id": str(uuid4()),
                "workspace_id": workspace_id,
                "project_id": project_id,
                "base_revision_id": project["current_revision_id"],
                "client_id": str(uuid4()),
                "client_sequence": 1,
                "kind": "timeline.patch",
                "payload": operation_payload,
                "payload_sha256": canonical_sha256(operation_payload),
                "created_at": "2026-08-11T00:00:00Z",
            }
            assert desktop_a.enqueue(operation["operation_id"], operation)
            assert desktop_a.flush(transport_a).accepted == 1
            pulled = desktop_b.pull(transport_b)
            assert [item["operation_id"] for item in pulled] == [operation["operation_id"]]

            current = api.get(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}", headers=alice
            ).json()
            platform_fingerprint = "sha256:" + "2" * 64
            executor = api.post(
                f"/v1/workspaces/{workspace_id}/executors",
                json={
                    "platform": "linux",
                    "capabilities": ["render", "ffmpeg.software"],
                    "region": "local",
                    "office_capability": "libreoffice",
                    "capability_snapshot": {"fingerprint": platform_fingerprint},
                    "ttl_seconds": 900,
                },
                headers=alice,
            ).json()
            policy_hash = "sha256:" + "1" * 64
            runtime_hash = "sha256:" + "3" * 64
            fingerprints = {
                "provider_policy": policy_hash,
                "platform": platform_fingerprint,
                "runtime": runtime_hash,
                "input": current["head"]["content_sha256"],
            }
            job = api.post(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/jobs",
                json={
                    "revision_id": current["current_revision_id"],
                    "kind": "render",
                    "provider_policy_sha256": policy_hash,
                    "provider_budget": {
                        "schema_version": 1,
                        "timeout_ms": 120000,
                        "max_attempts": 2,
                        "max_input_bytes": 1073741824,
                        "max_output_bytes": 4294967296,
                        "max_cost_minor": 1000,
                    },
                    "provider_cost_estimate_minor": 250,
                    "runtime_image_sha256": runtime_hash,
                    "required_capabilities": ["ffmpeg.software"],
                    "required_region": "local",
                    "parameters": {"preset": "preview"},
                    "fingerprints": fingerprints,
                },
                headers={**alice, "Idempotency-Key": str(uuid4())},
            )
            assert job.status_code == 202
            dispatched = job.json()
            assert dispatched["executor_id"] == executor["executor_id"]

            candidate = b"validated candidate media"
            object_id = "sha256:" + hashlib.sha256(candidate).hexdigest()
            upload = api.post(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads",
                json={
                    "object": {
                        "object_id": object_id,
                        "size_bytes": len(candidate),
                        "media_type": "application/octet-stream",
                        "classification": "internal",
                    }
                },
                headers=alice,
            ).json()
            part = api.put(upload["parts"][0]["local_endpoint"], content=candidate, headers=alice)
            assert part.status_code == 200
            assert (
                api.post(
                    f"/v1/workspaces/{workspace_id}/projects/{project_id}/objects/uploads/"
                    f"{upload['upload_id']}/complete",
                    json={"parts": [{"part_number": 1, "etag": part.json()["etag"]}]},
                    headers=alice,
                ).status_code
                == 201
            )
            result = {
                "candidate_object_id": object_id,
                "revision_id": current["current_revision_id"],
            }
            published = api.post(
                f"/v1/workspaces/{workspace_id}/projects/{project_id}/jobs/"
                f"{dispatched['job_id']}/result",
                json={
                    "attempt_id": dispatched["attempt_id"],
                    "executor_id": executor["executor_id"],
                    "status": "completed",
                    "result_schema_version": 1,
                    "result": result,
                    "result_sha256": canonical_sha256(result),
                    "output_refs": ["artifact://" + object_id],
                    "output_media_types": {
                        "artifact://" + object_id: "application/octet-stream"
                    },
                    "fingerprints": fingerprints,
                },
                headers={
                    **alice,
                    "Idempotency-Key": str(uuid4()),
                    "X-Attempt-Token": dispatched["attempt_access_token"],
                },
            )
            assert published.status_code == 200
            downloaded = transport_b.download_object(object_id)
            staged = desktop_b.stage_object(object_id, downloaded, tmp_path / "device-b-staging")
            assert staged.read_bytes() == candidate
        finally:
            transport_a.close()
            transport_b.close()
