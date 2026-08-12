from __future__ import annotations

import json
import subprocess
from pathlib import Path
from uuid import uuid4

import pytest
from workbench.e2e.synthetic import (
    SyntheticAuthoritativePreviewExecutor,
    SyntheticVideoRenderer,
)
from workbench.rendering.hashing import sha256_json
from workbench.rendering.models import GraphCanvas, RenderGraphV2

from scripts.dg2_e2e_fixture import (
    CONTRACT_PATH,
    FIXTURE_VERSION,
    FixtureValidationError,
    generate_fixtures,
    validate_fixtures,
)


def test_dg2_s1_and_s8_fixtures_are_synthetic_and_contract_valid(tmp_path: Path) -> None:
    observed = generate_fixtures(tmp_path)
    validated = validate_fixtures(tmp_path)

    assert set(validated) == {"S1", "S8"}
    assert validated == observed
    assert validated["S1"]["page_count"] == 2
    assert validated["S8"]["page_count"] == 8
    assert validated["S8"]["audio"] == {
        "sample_rate": 16_000,
        "channels": 1,
        "duration_ms": 6_000,
    }
    assert all(item["content_policy"] == "synthetic-only" for item in validated.values())


def test_dg2_fixture_validator_fails_closed_on_source_drift(tmp_path: Path) -> None:
    generate_fixtures(tmp_path)
    audio = tmp_path / "s8" / "local-narration.wav"
    audio.write_bytes(audio.read_bytes() + b"unexpected")

    with pytest.raises(FixtureValidationError, match="source hashes"):
        validate_fixtures(tmp_path)


def test_dg2_fixture_contract_is_reviewable_and_versioned() -> None:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))

    assert contract["fixture_version"] == FIXTURE_VERSION
    assert set(contract["profiles"]) == {"S1", "S8"}
    assert all(
        len(file["sha256"]) == 64
        for profile in contract["profiles"].values()
        for file in profile["files"].values()
    )


def test_synthetic_render_delay_is_explicitly_scoped_and_validated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("WORKBENCH_E2E_SYNTHETIC_MODE", raising=False)
    monkeypatch.setenv("WORKBENCH_DG2_RENDER_DELAY_SECONDS", "2")
    assert SyntheticVideoRenderer().delay_seconds == 0

    monkeypatch.setenv("WORKBENCH_E2E_SYNTHETIC_MODE", "true")
    assert SyntheticVideoRenderer().delay_seconds == 2
    monkeypatch.setenv("WORKBENCH_DG2_RENDER_DELAY_SECONDS", "invalid")
    with pytest.raises(ValueError, match="must be numeric"):
        SyntheticVideoRenderer()


def test_synthetic_authoritative_preview_uses_graph_media_contract(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    draft = RenderGraphV2(
        project_id=uuid4(),
        timeline_revision=1,
        duration_us=1_500_000,
        canvas=GraphCanvas(width=1280, height=720, fps_num=30, fps_den=1),
        graph_hash="0" * 64,
    )
    graph = draft.model_copy(
        update={
            "graph_hash": sha256_json(
                draft.model_dump(mode="json", exclude={"graph_hash", "created_at"})
            )
        }
    )
    observed: list[str] = []

    def run(command: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        observed.extend(command)
        Path(command[-1]).write_bytes(b"synthetic-preview")
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(subprocess, "run", run)
    output = SyntheticAuthoritativePreviewExecutor("fixture-ffmpeg")(
        graph, tmp_path / "preview"
    )

    assert output.read_bytes() == b"synthetic-preview"
    assert observed[0] == "fixture-ffmpeg"
    assert "color=c=black:s=1280x720:r=30/1:d=1.500000" in observed
    assert "anullsrc=r=48000:cl=stereo" in observed
    assert "libx264" in observed
    assert "aac" in observed
