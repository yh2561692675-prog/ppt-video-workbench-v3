from __future__ import annotations


def test_p11_package_manifest_is_deterministic_and_path_safe(tmp_path) -> None:
    from workbench.business_modules.p11_render.runner import build_package_manifest

    (tmp_path / "final.mp4").write_bytes(b"video")
    result = build_package_manifest(tmp_path, ["final.mp4"])

    assert result["files"][0]["relative_path"] == "final.mp4"
    assert len(result["files"][0]["sha256"]) == 64
