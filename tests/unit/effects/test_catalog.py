from workbench.effects.catalog import EFFECT_CATALOG, EFFECT_CATALOG_VERSION


def test_catalog_contains_twelve_public_templates_and_internal_safe_slide() -> None:
    public = [entry for entry in EFFECT_CATALOG if not entry["internal"]]

    assert EFFECT_CATALOG_VERSION == "effect-catalog-v2"
    assert len(public) == 12
    assert [entry["name"] for entry in EFFECT_CATALOG][-1] == "SafeSlide"
