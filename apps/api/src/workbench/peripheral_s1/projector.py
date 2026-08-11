from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from peripheral_contracts import BusinessResultManifest

ProjectorFn = Callable[[BusinessResultManifest, Path], None]


class ProjectorRegistry:
    def __init__(self) -> None:
        self._projectors: dict[str, ProjectorFn] = {
            "material_sources": _material_sources_projector,
            "document_extraction": _document_extraction_projector,
            "page_matches": _page_matches_projector,
            "narration_revisions": _narration_revisions_projector,
            "narration_docx": _narration_docx_projector,
            "audio_pipeline": _audio_pipeline_projector,
            "subtitle_timeline": _subtitle_timeline_projector,
            "effect_plan_v2": _effect_plan_projector,
            "project_video_props": _project_video_props_projector,
            "video_preview": _video_preview_projector,
            "preflight_report": _preflight_report_projector,
            "page_segments": _page_segments_projector,
            "video_assembled": _video_assembled_projector,
            "package_manifest": _package_manifest_projector,
            "quality_report": _quality_report_projector,
            "delivery_decision": _delivery_decision_projector,
        }

    def register(self, result_type: str, projector: ProjectorFn) -> None:
        self._projectors[result_type] = projector

    def apply(self, payload: bytes, project_dir: Path) -> BusinessResultManifest:
        result = BusinessResultManifest.model_validate_json(payload)
        try:
            projector = self._projectors[result.result_type]
        except KeyError as error:
            raise ValueError(f"unregistered business result type: {result.result_type}") from error
        projector(result, project_dir)
        return result


def json_projector(filename: str, key: str) -> ProjectorFn:
    def apply(result: BusinessResultManifest, project_dir: Path) -> None:
        target = project_dir / filename
        temporary = target.with_name(f".{target.name}.tmp")
        value = result.payload.get(key, result.payload)
        temporary.write_text(
            json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        temporary.replace(target)

    return apply


def _material_sources_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p03_material.runner import project_material_sources

    project_material_sources(result, project_dir)


def _document_extraction_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p04_extract.runner import project_document_extraction

    project_document_extraction(result, project_dir)


def _page_matches_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p05_match.runner import project_page_matches

    project_page_matches(result, project_dir)


def _narration_revisions_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p06_narration.runner import project_narration_revisions

    project_narration_revisions(result, project_dir)


def _narration_docx_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p06_narration.models import NarrationDocxPayload

    payload = NarrationDocxPayload.model_validate(result.payload)
    target = project_dir / "s1-narration-export.json"
    temporary = target.with_name(f".{target.name}.tmp")
    temporary.write_text(payload.model_dump_json(indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)


def _audio_pipeline_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p07_audio.runner import project_audio_pipeline

    project_audio_pipeline(result, project_dir)


def _subtitle_timeline_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p08_subtitle.runner import project_subtitle_timeline

    project_subtitle_timeline(result, project_dir)


def _effect_plan_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p09_effects.runner import project_effect_plan

    project_effect_plan(result, project_dir)


def _project_video_props_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p09_effects.runner import project_video_props

    project_video_props(result, project_dir)


def _preflight_report_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p10_preflight.runner import project_preflight_report

    project_preflight_report(result, project_dir)


def _video_preview_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p10_preflight.runner import project_video_preview

    project_video_preview(result, project_dir)


def _page_segments_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p11_render.runner import project_page_segments

    project_page_segments(result, project_dir)


def _video_assembled_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p11_render.runner import project_video_assembled

    project_video_assembled(result, project_dir)


def _package_manifest_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p11_render.runner import project_package_manifest

    project_package_manifest(result, project_dir)


def _quality_report_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p12_delivery.runner import project_quality_report

    project_quality_report(result, project_dir)


def _delivery_decision_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p12_delivery.runner import project_delivery_decision

    project_delivery_decision(result, project_dir)
