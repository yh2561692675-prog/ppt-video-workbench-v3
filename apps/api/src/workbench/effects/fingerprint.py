from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel


def calculate_input_fingerprint(value: BaseModel) -> str:
    payload = value.model_dump(mode="json", exclude={"source_path"})
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
