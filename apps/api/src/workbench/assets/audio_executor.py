from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from workbench.assets.derivative_models import DerivativeOperation, DerivativeRequestV1
from workbench.assets.object_store import ContentAddressedObjectStore, StoredObject
from workbench.media.waveform import build_waveform


class AudioDerivativeError(ValueError):
    pass


class WaveformDerivativeExecutor:
    def __init__(self, object_store: ContentAddressedObjectStore, work_root: Path) -> None:
        self.object_store = object_store
        self.work_root = work_root

    def execute(self, request: DerivativeRequestV1, source: Path) -> StoredObject:
        if request.operation is not DerivativeOperation.WAVEFORM:
            raise AudioDerivativeError(f"unsupported audio operation: {request.operation.value}")
        unknown = sorted(set(request.parameters) - {"bucket_sizes"})
        if unknown:
            raise AudioDerivativeError(f"unsupported audio parameters: {', '.join(unknown)}")
        raw_sizes = request.parameters.get("bucket_sizes", [256, 1024, 4096])
        if not isinstance(raw_sizes, list):
            raise AudioDerivativeError("bucket_sizes must be a list")
        try:
            bucket_sizes = tuple(int(value) for value in raw_sizes)
        except (TypeError, ValueError) as error:
            raise AudioDerivativeError("bucket_sizes must contain integers") from error
        manifest = build_waveform(
            source,
            source_hash=request.parent_content_hash,
            bucket_sizes=bucket_sizes,
        )
        self.work_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="waveform-", dir=self.work_root) as temporary:
            output = Path(temporary) / "waveform.json"
            output.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
            return self.object_store.ingest_file(output, suffix=".json")
