from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_api_web_and_remotion_packages_are_discoverable() -> None:
    expected_manifests = (
        ROOT / "apps" / "api" / "pyproject.toml",
        ROOT / "apps" / "web" / "package.json",
        ROOT / "remotion" / "package.json",
    )

    missing = [str(path.relative_to(ROOT)) for path in expected_manifests if not path.is_file()]

    assert missing == [], f"Missing workspace packages: {', '.join(missing)}"
