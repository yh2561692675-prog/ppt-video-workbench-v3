from __future__ import annotations


def test_registry_only_enables_whitelisted_modules() -> None:
    from workbench.business_modules.registry import business_registered_modules

    modules = business_registered_modules({"P03", "P04"})

    assert {item.manifest.module_name for item in modules} == {"p03-material", "p04-extract"}
    assert {job_type for item in modules for job_type in item.manifest.job_types} == {
        "material.ingest",
        "material.reorder",
        "document.extract",
        "document.ocr",
    }
