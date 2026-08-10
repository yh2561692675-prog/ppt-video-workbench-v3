from __future__ import annotations

import hashlib
import json
from typing import Any


def render_input_fingerprint(preflight: Any) -> str:
    """Return the canonical fingerprint used by submit and export validation."""

    payload = {
        "props": preflight.props.model_dump(mode="json"),
        "input_fingerprint": getattr(preflight, "input_fingerprint", None),
        "renderer_runtime": "workbench-renderer-v1",
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
