from __future__ import annotations

import base64
import json
import re
from pathlib import Path
from uuid import UUID

import httpx
from docx import Document
from fastapi.testclient import TestClient
from workbench.domain.enums import NodeStatus
from workbench.domain.extraction import PageExtraction
from workbench.domain.matching import MatchCandidate, MatchComponents, MatchWeights, PageMatch
from workbench.domain.models import PageRecord, stable_page_id
from workbench.exports.narration_docx import export_narration_docx
from workbench.main import create_app
from workbench.settings.secret_store import SecretProtector


class GateTestProtector(SecretProtector):
    def protect(self, plaintext: bytes) -> bytes:
        return base64.b64encode(plaintext[::-1])

    def unprotect(self, ciphertext: bytes) -> bytes:
        return base64.b64decode(ciphertext)[::-1]


def _transport(request: httpx.Request) -> httpx.Response:
    payload = json.loads(request.content)
    prompt = "\n".join(item["content"] for item in payload["messages"])
    matched = re.search(r"\[课件来源 page:(\d+)\]", prompt)
    assert matched is not None
    order = int(matched.group(1))
    content = json.dumps(
        {
            "text": f"第 {order} 页介绍主题 {order}，并说明对应培养目标。",
            "source_refs": [f"page:{order}", f"outline:{order}"],
            "insufficiencies": [],
            "warnings": [],
        },
        ensure_ascii=False,
    )
    return httpx.Response(200, json={"choices": [{"message": {"content": content}}]})


def test_eight_page_generation_version_confirmation_export_and_relock(tmp_path: Path) -> None:
    app = create_app(
        tmp_path,
        secret_protector=GateTestProtector(),
        llm_transport=httpx.MockTransport(_transport),
    )
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "M3八页验收"}).json()["data"]
        project_id = UUID(project["id"])
        page_ids = [stable_page_id(project_id, order) for order in range(1, 9)]
        service = app.state.project_service
        manifest = service.get(project_id)
        pages = [
            PageRecord(
                id=page_id,
                order=order,
                title=f"第{order}页主题",
                status=NodeStatus.COMPLETED,
            )
            for order, page_id in enumerate(page_ids, start=1)
        ]
        extractions = [
            PageExtraction(
                id=page_id,
                order=order,
                title=f"第{order}页主题",
                text=f"第 {order} 页介绍主题 {order}",
                extraction_method="pptx",
                source_ref=f"page:{order}",
            )
            for order, page_id in enumerate(page_ids, start=1)
        ]
        matches = [
            PageMatch(
                page_id=page_id,
                page_order=order,
                page_title=f"第{order}页主题",
                page_text=f"第 {order} 页介绍主题 {order}",
                selected_outline_ref=f"outline:{order}",
                score=0.9,
                needs_confirmation=False,
                decision_source="deterministic_rules",
                candidates=[
                    MatchCandidate(
                        outline_ref=f"outline:{order}",
                        outline_title=f"培养目标{order}",
                        outline_text=f"对应培养目标 {order}",
                        score=0.9,
                        weights=MatchWeights(),
                        components=MatchComponents(
                            page_order=1,
                            title=1,
                            keywords=0.7,
                            body=0.6,
                        ),
                    )
                ],
            )
            for order, page_id in enumerate(page_ids, start=1)
        ]
        service.save(
            manifest.model_copy(
                update={"pages": pages, "page_extractions": extractions, "matches": matches}
            )
        )
        profile = client.post(
            "/api/settings/llm-profiles",
            json={
                "name": "M3测试模型",
                "base_url": "https://llm.example.test/v1",
                "api_key": "sk-m3-gate-secret",
                "model": "compatible-model",
            },
        ).json()["data"]

        generated = []
        for page_id in page_ids:
            response = client.post(
                f"/api/projects/{project_id}/narrations/{page_id}/generate",
                json={"profile_id": profile["id"]},
            )
            assert response.status_code == 201
            generated.append(response.json()["data"])

        edited = client.post(
            f"/api/projects/{project_id}/narrations/{page_ids[2]}/revisions",
            json={
                "text": "第 3 页经人工修改，仍只说明主题 3 与培养目标。",
                "author": "规划师",
                "expected_revision_id": generated[2]["id"],
                "source_refs": ["page:3", "outline:3"],
            },
        ).json()["data"]
        restored = client.post(
            f"/api/projects/{project_id}/narrations/{page_ids[2]}/restore/{generated[2]['id']}",
            json={"actor": "规划师", "expected_revision_id": edited["id"]},
        ).json()["data"]
        assert restored["version"] == 3
        current_revision_ids = [item["id"] for item in generated]
        current_revision_ids[2] = restored["id"]

        confirmed = client.post(
            f"/api/projects/{project_id}/confirmations/batch",
            json={
                "actor": "规划师",
                "items": [
                    {"page_id": str(page_id), "revision_id": revision_id}
                    for page_id, revision_id in zip(page_ids, current_revision_ids, strict=True)
                ],
            },
        )
        assert confirmed.status_code == 200
        assert len(confirmed.json()["data"]) == 8
        assert (
            client.get(f"/api/projects/{project_id}/workflow/audio-gate").json()["data"]["allowed"]
            is True
        )

        confirmed_manifest = service.get(project_id)
        project_dir = tmp_path / confirmed_manifest.project_dir
        docx_path = export_narration_docx(confirmed_manifest, project_dir)
        document_text = "\n".join(paragraph.text for paragraph in Document(docx_path).paragraphs)
        assert [document_text.index(f"第{order}页主题") for order in range(1, 9)] == sorted(
            document_text.index(f"第{order}页主题") for order in range(1, 9)
        )

        relock = client.post(
            f"/api/projects/{project_id}/narrations/{page_ids[5]}/revisions",
            json={
                "text": "第 6 页确认后修改。",
                "author": "规划师",
                "expected_revision_id": current_revision_ids[5],
                "source_refs": ["page:6", "outline:6"],
            },
        )
        assert relock.status_code == 201
        gate = client.get(f"/api/projects/{project_id}/workflow/audio-gate").json()["data"]
        assert gate["allowed"] is False
        assert any(reason["page_id"] == str(page_ids[5]) for reason in gate["reasons"])

    saved = app.state.project_service.get(project_id)
    assert len(saved.llm_usage) == 8
    assert "sk-m3-gate-secret" not in (tmp_path / saved.project_dir / "project.json").read_text(
        encoding="utf-8"
    )
