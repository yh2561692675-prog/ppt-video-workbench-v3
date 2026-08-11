from __future__ import annotations

import json
from pathlib import Path

import pytest
from workbench.desktop.release_slots import ReleaseSlotError, ReleaseSlots


def _release(app_root: Path, version: str, content: str) -> Path:
    root = app_root / "releases" / version / "release"
    root.mkdir(parents=True)
    (root / "runtime-manifest.json").write_text(content, encoding="utf-8")
    return root


def test_activate_and_rollback_switches_atomic_release_pointers(tmp_path: Path) -> None:
    slots = ReleaseSlots(tmp_path / "app")
    v1 = slots.slot_for_release(_release(slots.app_root, "1.0.0", "v1"), "1.0.0")
    v2 = slots.slot_for_release(_release(slots.app_root, "1.1.0", "v2"), "1.1.0")

    slots.activate(v1)
    slots.activate(v2)

    assert slots.read_active().version == "1.1.0"
    assert slots.read_previous().version == "1.0.0"
    assert slots.rollback().version == "1.0.0"
    assert slots.read_active().version == "1.0.0"
    assert slots.read_previous().version == "1.1.0"


def test_slot_rejects_tampered_payload_or_path_escape(tmp_path: Path) -> None:
    slots = ReleaseSlots(tmp_path / "app")
    root = _release(slots.app_root, "1.0.0", "v1")
    slot = slots.slot_for_release(root, "1.0.0")
    slots.activate(slot)
    (root / "runtime-manifest.json").write_text("tampered", encoding="utf-8")

    with pytest.raises(ReleaseSlotError, match="release_payload_manifest_hash_mismatch"):
        slots.resolve(slots.read_active())

    slots.state_root.mkdir(parents=True, exist_ok=True)
    slots.active_path.write_text(
        json.dumps(
            {
                "version": "1.0.0",
                "relative_path": "../outside",
                "payload_manifest_sha256": "a" * 64,
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ReleaseSlotError, match="release_slot_path_invalid"):
        slots.read_active()
