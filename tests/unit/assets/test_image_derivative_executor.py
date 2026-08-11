from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from PIL import Image
from workbench.assets.derivative_models import DerivativeOperation, DerivativeRequestV1
from workbench.assets.image_executor import ImageDerivativeError, ImageDerivativeExecutor
from workbench.assets.object_store import ContentAddressedObjectStore


def _request(operation: DerivativeOperation, parameters: dict[str, object]) -> DerivativeRequestV1:
    return DerivativeRequestV1(
        parent_asset_id=uuid4(),
        parent_revision=1,
        parent_content_hash="a" * 64,
        operation=operation,
        parameters=parameters,
        output_slot="preview",
        tool_fingerprint="b" * 64,
    )


def test_image_executor_crops_and_publishes_independent_object(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGBA", (100, 80), (255, 0, 0, 128)).save(source)
    store = ContentAddressedObjectStore(tmp_path / "store")
    executor = ImageDerivativeExecutor(store, tmp_path / "work")

    stored = executor.execute(
        _request(
            DerivativeOperation.CROP,
            {"x": 10, "y": 5, "width": 40, "height": 30, "format": "png"},
        ),
        source,
    )

    with Image.open(store.open_verified(stored)) as result:
        assert result.size == (40, 30)
        assert result.mode == "RGBA"
    assert Image.open(source).size == (100, 80)


def test_image_executor_rejects_out_of_bounds_and_unknown_parameters(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    Image.new("RGB", (20, 20), "blue").save(source)
    executor = ImageDerivativeExecutor(
        ContentAddressedObjectStore(tmp_path / "store"), tmp_path / "work"
    )

    with pytest.raises(ImageDerivativeError, match="exceeds"):
        executor.execute(
            _request(
                DerivativeOperation.CROP,
                {"x": 10, "y": 10, "width": 20, "height": 20},
            ),
            source,
        )
    with pytest.raises(ImageDerivativeError, match="unsupported image parameters"):
        executor.execute(
            _request(DerivativeOperation.THUMBNAIL, {"width": 10, "height": 10, "shell": True}),
            source,
        )
