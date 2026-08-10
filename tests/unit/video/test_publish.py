from __future__ import annotations

import json
from pathlib import Path

import pytest
from workbench.video import publish as publish_module
from workbench.video.publish import publish_render_outputs


def test_publish_keeps_previous_outputs_and_switches_latest_pointer_last(tmp_path: Path) -> None:
    output_root = tmp_path / "08_output"
    output_root.mkdir()
    previous_mp4 = output_root / "final.mp4"
    previous_mp4.write_bytes(b"previous")
    previous_package = output_root / "package-previous"
    previous_package.mkdir()
    (previous_package / "manifest.json").write_text("previous", encoding="utf-8")

    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "final.mp4").write_bytes(b"new")
    package = staging / "package"
    package.mkdir()
    (package / "manifest.json").write_text("new", encoding="utf-8")

    published = publish_render_outputs(
        staging_root=staging,
        output_root=output_root,
        run_id="job-1",
        final_name="final.mp4",
        package_name="package",
    )

    assert previous_mp4.read_bytes() == b"new"
    assert previous_package.exists()
    assert published.mp4_path.read_bytes() == b"new"
    assert published.package_path.name == "package-job-1"
    assert json.loads((output_root / "latest.json").read_text(encoding="utf-8")) == {
        "mp4_relative_path": "final.mp4",
        "package_relative_path": "package-job-1",
        "run_id": "job-1",
    }


def test_publish_replaces_stable_mp4_atomically_without_touching_package_history(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "08_output"
    output_root.mkdir()
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "final.mp4").write_bytes(b"new")
    package = staging / "package"
    package.mkdir()
    (package / "file.txt").write_text("new", encoding="utf-8")

    first = publish_render_outputs(
        staging_root=staging,
        output_root=output_root,
        run_id="job-1",
        final_name="final.mp4",
        package_name="package",
    )
    second_staging = tmp_path / "staging-2"
    second_staging.mkdir()
    (second_staging / "final.mp4").write_bytes(b"newer")
    second_package = second_staging / "package"
    second_package.mkdir()
    (second_package / "file.txt").write_text("newer", encoding="utf-8")

    second = publish_render_outputs(
        staging_root=second_staging,
        output_root=output_root,
        run_id="job-2",
        final_name="final.mp4",
        package_name="package",
    )

    assert second.mp4_path.read_bytes() == b"newer"
    assert first.package_path.exists()
    assert second.package_path.exists()


def test_package_copy_failure_keeps_previous_successful_mp4(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "08_output"
    output_root.mkdir()
    stable_mp4 = output_root / "final.mp4"
    stable_mp4.write_bytes(b"previous")
    staging = tmp_path / "staging"
    staging.mkdir()
    (staging / "final.mp4").write_bytes(b"new")
    (staging / "package").mkdir()

    def fail_copytree(*args, **kwargs):
        raise OSError("simulated package copy failure")

    monkeypatch.setattr(publish_module.shutil, "copytree", fail_copytree)

    with pytest.raises(OSError, match="package copy failure"):
        publish_render_outputs(
            staging_root=staging,
            output_root=output_root,
            run_id="job-failed",
            final_name="final.mp4",
            package_name="package",
        )

    assert stable_mp4.read_bytes() == b"previous"
    assert not (output_root / "latest.json").exists()
