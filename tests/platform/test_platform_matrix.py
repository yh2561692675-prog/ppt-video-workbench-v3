from __future__ import annotations

from pathlib import Path

import pytest
from workbench.platform.composition import create_platform_services


@pytest.mark.parametrize("platform_name", ["windows", "macos", "linux"])
def test_platform_services_have_stable_capability_contract(
    tmp_path: Path, platform_name: str
) -> None:
    services = create_platform_services(
        tmp_path / platform_name,
        platform_override=platform_name,  # type: ignore[arg-type]
    )
    snapshot = services.capabilities()
    assert snapshot.info.platform == platform_name
    assert "paths" in snapshot.capabilities
    assert "processes" in snapshot.capabilities
    assert snapshot.fingerprint.startswith("sha256:")
    office_state = {
        item.capability_id: item.status
        for item in snapshot.capability_states
        if item.capability_id == "office.powerpoint_native"
    }
    assert office_state["office.powerpoint_native"] in {
        "supported",
        "missing",
        "unsupported",
    }
