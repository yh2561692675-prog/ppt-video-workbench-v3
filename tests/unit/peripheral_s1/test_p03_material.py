from __future__ import annotations

import io
from pathlib import Path

import pytest
from PIL import Image


def _png_bytes(color: str = "red") -> bytes:
    image = Image.new("RGB", (4, 4), color=color)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_material_runner_validates_and_naturally_orders_images(tmp_path: Path) -> None:
    from workbench.business_modules.p03_material.runner import stage_material_bytes

    outputs = stage_material_bytes(
        [("10.png", _png_bytes()), ("2.png", _png_bytes("blue"))], tmp_path
    )

    assert [item["original_name"] for item in outputs] == ["2.png", "10.png"]
    assert [item["image_order"] for item in outputs] == [1, 2]
    assert (tmp_path / "2.png").is_file()
    assert (tmp_path / "10.png").is_file()


def test_material_runner_rejects_extension_mismatch_and_empty_file(tmp_path: Path) -> None:
    from workbench.business_modules.p03_material.runner import (
        MaterialRejected,
        stage_material_bytes,
    )

    with pytest.raises(MaterialRejected):
        stage_material_bytes([("bad.pdf", _png_bytes())], tmp_path)
    with pytest.raises(MaterialRejected):
        stage_material_bytes([("empty.png", b"")], tmp_path)


def test_material_runner_preserves_duplicate_names_with_suffix(tmp_path: Path) -> None:
    from workbench.business_modules.p03_material.runner import stage_material_bytes

    outputs = stage_material_bytes(
        [("cover.png", _png_bytes()), ("cover.png", _png_bytes("blue"))], tmp_path
    )

    assert [item["safe_name"] for item in outputs] == ["cover.png", "cover_2.png"]
