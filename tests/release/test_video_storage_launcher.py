from pathlib import Path

LAUNCHER = Path(__file__).parents[2] / "scripts" / "launcher.ps1"


def test_launcher_configures_and_probes_f_drive_video_storage() -> None:
    source = LAUNCHER.read_text(encoding="utf-8-sig")

    assert '$cacheRoot = "F:\\Video\\Cache"' in source
    assert '$outputRoot = "F:\\Video\\Output"' in source
    assert "function Assert-WritableDirectory" in source
    assert "$env:WORKBENCH_CACHE_ROOT = $cacheRoot" in source
    assert "$env:WORKBENCH_OUTPUT_ROOT = $outputRoot" in source
