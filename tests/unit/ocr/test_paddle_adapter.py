from __future__ import annotations

from pathlib import Path

import pytest
from workbench.ocr.paddle_adapter import prepare_paddle_cache


def test_prepare_paddle_cache_avoids_read_only_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", "/read-only-home")
    monkeypatch.delenv("PADDLE_PDX_CACHE_HOME", raising=False)
    monkeypatch.delenv("WORKBENCH_CACHE_DIR", raising=False)

    selected = prepare_paddle_cache(fallback_root=tmp_path)

    assert selected == tmp_path / "paddlex"
    assert selected.is_dir()
