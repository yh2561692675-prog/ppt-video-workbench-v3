from __future__ import annotations

import struct
import wave
from pathlib import Path
from uuid import uuid4

from workbench.assets.audio_executor import WaveformDerivativeExecutor
from workbench.assets.derivative_models import DerivativeOperation, DerivativeRequestV1
from workbench.assets.object_store import ContentAddressedObjectStore


def test_audio_executor_publishes_waveform_manifest(tmp_path: Path) -> None:
    source = tmp_path / "voice.wav"
    with wave.open(str(source), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(8_000)
        output.writeframes(struct.pack("<8h", -1000, 0, 1000, 0, -1000, 0, 1000, 0))
    store = ContentAddressedObjectStore(tmp_path / "store")
    executor = WaveformDerivativeExecutor(store, tmp_path / "work")
    request = DerivativeRequestV1(
        parent_asset_id=uuid4(),
        parent_revision=1,
        parent_content_hash="a" * 64,
        operation=DerivativeOperation.WAVEFORM,
        parameters={"bucket_sizes": [4, 8]},
        output_slot="waveform",
        tool_fingerprint="b" * 64,
    )

    stored = executor.execute(request, source)

    payload = store.open_verified(stored).read_text(encoding="utf-8")
    assert '"sample_count": 8' in payload
    assert '"samples_per_bucket": 4' in payload
