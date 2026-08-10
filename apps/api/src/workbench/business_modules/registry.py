from __future__ import annotations

import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import cast

from peripheral_contracts import ModuleManifest
from peripheral_host.module_runner import RegisteredModule

_MODULES: dict[str, tuple[str, tuple[str, ...], str]] = {
    "P03": ("p03-material", ("material.ingest", "material.reorder"), "p03_material"),
    "P04": ("p04-extract", ("document.extract", "document.ocr"), "p04_extract"),
    "P05": ("p05-match", ("content.match",), "p05_match"),
    "P06": (
        "p06-narration",
        ("narration.generate", "narration.import", "narration.export"),
        "p06_narration",
    ),
    "P07": (
        "p07-audio",
        ("audio.normalize", "audio.transcribe", "audio.synthesize", "audio.align"),
        "p07_audio",
    ),
    "P08": ("p08-subtitle", ("subtitle.build",), "p08_subtitle"),
    "P09": ("p09-effects", ("effect.plan", "video.props.build"), "p09_effects"),
    "P10": ("p10-preflight", ("preview.build", "preflight.run"), "p10_preflight"),
    "P11": ("p11-render", ("video.render", "video.assemble", "package.build"), "p11_render"),
    "P12": ("p12-delivery", ("quality.verify", "delivery.archive"), "p12_delivery"),
}


def business_registered_modules(enabled: set[str]) -> tuple[RegisteredModule, ...]:
    normalized = {item.upper() for item in enabled}
    unknown = normalized - _MODULES.keys()
    if unknown:
        raise ValueError(f"unknown S1 modules: {sorted(unknown)}")
    source_root = Path(__file__).resolve().parents[2]
    peripheral_root = source_root.parents[2] / "peripheral-platform" / "src"
    frozen = getattr(sys, "_MEIPASS", None) is not None
    registered: list[RegisteredModule] = []
    for module_id in sorted(normalized):
        module_name, job_types, slug = _MODULES[module_id]
        manifest = ModuleManifest(
            schema_version="1.0",
            module_name=module_name,
            module_version="1.0.0",
            job_types=job_types,
            max_runtime_seconds=86400 if module_id in {"P11", "P12"} else 3600,
        )
        command = (
            (sys.executable, "--run-module", module_id.lower())
            if frozen
            else (sys.executable, "-m", f"workbench.business_modules.{slug}")
        )
        environment = (
            ()
            if frozen
            else (("PYTHONPATH", os.pathsep.join((str(source_root), str(peripheral_root)))),)
        )
        registered.append(
            RegisteredModule(manifest=manifest, command=command, environment=environment)
        )
    return tuple(registered)


def enabled_module_ids() -> set[str]:
    value = os.environ.get("PERIPHERAL_S1_MODULES", "")
    return {item.strip().upper() for item in value.split(",") if item.strip()}


def validate_module_job_type(module_id: str, job_type: str) -> str:
    normalized = module_id.upper()
    try:
        job_types = _MODULES[normalized][1]
    except KeyError as error:
        raise ValueError(f"unknown S1 module: {module_id}") from error
    if job_type not in job_types:
        raise ValueError(f"job type {job_type} is not registered for {normalized}")
    return normalized


def module_main_for_id(module_id: str) -> Callable[[], int]:
    normalized = module_id.upper()
    try:
        slug = _MODULES[normalized][2]
    except KeyError as error:
        raise ValueError(f"unknown bundled peripheral module: {module_id}") from error
    module = __import__(f"workbench.business_modules.{slug}.__main__", fromlist=["main"])
    return cast("Callable[[], int]", module.main)
