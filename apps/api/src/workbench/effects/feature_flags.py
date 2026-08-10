from __future__ import annotations

import os
from dataclasses import dataclass


def _enabled(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class EffectFeatureFlags:
    persistence: bool = False
    preview: bool = False
    render: bool = False

    @classmethod
    def from_environment(cls) -> EffectFeatureFlags:
        flags = cls(
            persistence=_enabled("WORKBENCH_EFFECT_V2_PERSISTENCE"),
            preview=_enabled("WORKBENCH_EFFECT_V2_PREVIEW"),
            render=_enabled("WORKBENCH_EFFECT_V2_RENDER"),
        )
        if (flags.preview or flags.render) and not flags.persistence:
            raise ValueError("Effect Engine V2 preview/render requires persistence")
        return flags
