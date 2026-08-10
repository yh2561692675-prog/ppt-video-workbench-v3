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
            "audio_pipeline": json_projector("s1-audio-pipeline.json", "timeline"),
            "subtitle_timeline": json_projector("s1-subtitle-timeline.json", "cues"),
            "effect_plan_v2": _effect_plan_projector,
            "project_video_props": json_projector("s1-video-props.json", "props"),
            "video_preview": json_projector("s1-video-preview.json", "preview"),
            "preflight_report": _preflight_report_projector,
            "package_manifest": json_projector("s1-package-manifest.json", "manifest"),
            "quality_report": json_projector("s1-quality-report.json", "report"),
            "delivery_decision": json_projector("s1-delivery-decision.json", "decision"),
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


def _effect_plan_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p09_effects.runner import project_effect_plan

    project_effect_plan(result, project_dir)


def _preflight_report_projector(result: BusinessResultManifest, project_dir: Path) -> None:
    from workbench.business_modules.p10_preflight.runner import project_preflight_report

    project_preflight_report(result, project_dir)
