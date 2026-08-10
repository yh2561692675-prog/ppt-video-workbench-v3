from __future__ import annotations

import base64
import json
from pathlib import Path
from uuid import UUID

import httpx
from fastapi.testclient import TestClient
from workbench.domain.enums import NodeStatus
from workbench.domain.extraction import PageExtraction
from workbench.domain.matching import MatchCandidate, MatchComponents, MatchWeights, PageMatch
from workbench.domain.models import PageRecord, stable_page_id
from workbench.main import create_app
from workbench.settings.secret_store import SecretProtector


class TestProtector(SecretProtector):
    def protect(self, plaintext: bytes) -> bytes:
        return base64.b64encode(plaintext[::-1])

    def unprotect(self, ciphertext: bytes) -> bytes:
        return base64.b64decode(ciphertext)[::-1]


def test_generate_narration_uses_current_sources_and_persists_profile_metadata(
    tmp_path: Path,
) -> None:
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        requests.append(payload)
        prompt = "\n".join(item["content"] for item in payload["messages"])
        assert "本页课件原文含 4 个方向" in prompt
        assert "匹配大纲强调工程能力" in prompt
        assert "第二页不可见文字" not in prompt
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "text": "本页介绍 4 个方向，并强调工程能力。",
                                    "source_refs": ["slides:1", "outline:1"],
                                    "insufficiencies": [],
                                    "warnings": [],
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    app = create_app(
        tmp_path,
        secret_protector=TestProtector(),
        llm_transport=httpx.MockTransport(handler),
    )
    with TestClient(app) as client:
        project = client.post("/api/projects", json={"name": "生成闭环"}).json()["data"]
        project_id = UUID(project["id"])
        first_id = stable_page_id(project_id, 1)
        second_id = stable_page_id(project_id, 2)
        service = app.state.project_service
        manifest = service.get(project_id)
        service.save(
            manifest.model_copy(
                update={
                    "pages": [
                        PageRecord(
                            id=first_id,
                            order=1,
                            title="培养方向",
                            status=NodeStatus.COMPLETED,
                        ),
                        PageRecord(
                            id=second_id,
                            order=2,
                            title="第二页",
                            status=NodeStatus.COMPLETED,
                        ),
                    ],
                    "page_extractions": [
                        PageExtraction(
                            id=first_id,
                            order=1,
                            text="本页课件原文含 4 个方向",
                            title="培养方向",
                            extraction_method="pptx",
                            source_ref="slides:1",
                        ),
                        PageExtraction(
                            id=second_id,
                            order=2,
                            text="第二页不可见文字",
                            title="第二页",
                            extraction_method="pptx",
                            source_ref="slides:2",
                        ),
                    ],
                    "matches": [
                        PageMatch(
                            page_id=first_id,
                            page_order=1,
                            page_title="培养方向",
                            page_text="本页课件原文含 4 个方向",
                            selected_outline_ref="outline:1",
                            score=0.91,
                            needs_confirmation=False,
                            decision_source="deterministic_rules",
                            candidates=[
                                MatchCandidate(
                                    outline_ref="outline:1",
                                    outline_title="培养目标",
                                    outline_text="匹配大纲强调工程能力",
                                    score=0.91,
                                    weights=MatchWeights(),
                                    components=MatchComponents(
                                        page_order=1,
                                        title=1,
                                        keywords=0.8,
                                        body=0.6,
                                    ),
                                )
                            ],
                        )
                    ],
                }
            )
        )
        profile = client.post(
            "/api/settings/llm-profiles",
            json={
                "name": "生成模型",
                "base_url": "https://llm.example.test/v1",
                "api_key": "sk-generation-secret",
                "model": "compatible-model",
            },
        ).json()["data"]

        generated = client.post(
            f"/api/projects/{project_id}/narrations/{first_id}/generate",
            json={"profile_id": profile["id"]},
        )

    assert generated.status_code == 201
    revision = generated.json()["data"]
    assert revision["text"] == "本页介绍 4 个方向，并强调工程能力。"
    assert revision["author"] == "AI草稿"
    assert revision["source_refs"] == ["slides:1", "outline:1"]
    assert len(requests) == 1
    saved = app.state.project_service.get(project_id)
    assert saved.pages[0].narration is not None
    assert saved.pages[0].narration.revision_id == UUID(revision["id"])
    assert saved.llm_usage[-1].profile_id == UUID(profile["id"])
    assert saved.llm_usage[-1].base_url_digest == profile["base_url_digest"]
    assert saved.llm_usage[-1].model == "compatible-model"
    manifest_text = (tmp_path / saved.project_dir / "project.json").read_text(encoding="utf-8")
    assert "sk-generation-secret" not in manifest_text
