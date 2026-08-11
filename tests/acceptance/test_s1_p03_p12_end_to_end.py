from __future__ import annotations


def test_all_s1_modules_have_unique_jobs_and_projectors() -> None:
    from workbench.business_modules.registry import business_registered_modules
    from workbench.peripheral_s1.projector import ProjectorRegistry

    module_ids = {f"P{index:02d}" for index in range(3, 13)}
    modules = business_registered_modules(module_ids)
    job_types = [job_type for module in modules for job_type in module.manifest.job_types]

    assert len(modules) == 10
    assert len(job_types) == len(set(job_types)) == 22
    assert {module.manifest.module_name for module in modules} == {
        "p03-material",
        "p04-extract",
        "p05-match",
        "p06-narration",
        "p07-audio",
        "p08-subtitle",
        "p09-effects",
        "p10-preflight",
        "p11-render",
        "p12-delivery",
    }
    assert set(ProjectorRegistry()._projectors) == {
        "material_sources",
        "document_extraction",
        "page_matches",
        "narration_revisions",
        "narration_docx",
        "audio_pipeline",
        "subtitle_timeline",
        "effect_plan_v2",
        "project_video_props",
        "video_preview",
        "preflight_report",
        "page_segments",
        "video_assembled",
        "package_manifest",
        "quality_report",
        "delivery_decision",
    }


def test_s1_module_commands_resolve_without_runtime_downloads() -> None:
    from workbench.business_modules.registry import business_registered_modules

    modules = business_registered_modules({f"P{index:02d}" for index in range(3, 13)})

    for module in modules:
        assert module.command[1] == "-m"
        assert module.command[2].startswith("workbench.business_modules.p")
        assert dict(module.environment)["PYTHONPATH"]
