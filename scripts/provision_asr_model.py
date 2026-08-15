"""Provision an offline faster-whisper model into a Workbench workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

MODEL_REPOSITORIES = {
    "small": "Systran/faster-whisper-small",
}
MODEL_FILES = ("config.json", "tokenizer.json", "vocabulary.txt", "model.bin")
MODEL_SIZE_FALLBACKS = {"model.bin": 483_546_902}


def _curl_path() -> str | None:
    return shutil.which("curl.exe") if os.name == "nt" else shutil.which("curl")


def _remote_size(curl: str, url: str, filename: str) -> int:
    headers = subprocess.run(
        [curl, "--fail", "--silent", "--show-error", "--location", "--head", url],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    for line in reversed(headers.splitlines()):
        if line.lower().startswith("content-length:"):
            value = line.split(":", 1)[1].strip()
            if value.isdigit():
                return int(value)
    if filename in MODEL_SIZE_FALLBACKS:
        return MODEL_SIZE_FALLBACKS[filename]
    raise RuntimeError(f"model file size was not returned for {filename}")


def _download_large_file(curl: str, url: str, target: Path, total: int) -> None:
    # The managed Windows proxy reliably serves 1 MiB ranges but may stall on
    # larger Xet ranges; parallel small ranges keep the provisioner resumable.
    chunk_size = 1024 * 1024
    chunks_root = target.with_name(f"{target.name}.chunks")
    if chunks_root.exists():
        shutil.rmtree(chunks_root)
    chunks_root.mkdir(parents=True, exist_ok=False)
    ranges = [
        (start, min(start + chunk_size, total) - 1)
        for start in range(0, total, chunk_size)
    ]

    def fetch(item: tuple[int, int]) -> Path:
        start, end = item
        part = chunks_root / f"{start:012d}.part"
        subprocess.run(
            [
                curl,
                "--fail",
                "--silent",
                "--show-error",
                "--location",
                "--retry",
                "3",
                "--retry-delay",
                "2",
                "--retry-all-errors",
                "--connect-timeout",
                "30",
                "--max-time",
                "180",
                "--range",
                f"{start}-{end}",
                "--output",
                str(part),
                url,
            ],
            check=True,
        )
        expected = end - start + 1
        if part.stat().st_size != expected:
            raise RuntimeError(
                f"model range {start}-{end} returned {part.stat().st_size} bytes, "
                f"expected {expected}"
            )
        return part

    try:
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = [executor.submit(fetch, item) for item in ranges]
            for future in as_completed(futures):
                future.result()
        with target.open("wb") as output:
            for start, _ in ranges:
                part = chunks_root / f"{start:012d}.part"
                with part.open("rb") as source:
                    shutil.copyfileobj(source, output, length=1024 * 1024)
            output.flush()
            os.fsync(output.fileno())
    finally:
        shutil.rmtree(chunks_root, ignore_errors=True)
    if target.stat().st_size != total:
        raise RuntimeError(f"model file size mismatch for {target.name}")


def _download_snapshot(repository: str, target: Path, revision: str) -> None:
    """Download public model files without relying on Xet or a mutable cache."""
    for filename in MODEL_FILES:
        url = f"https://huggingface.co/{repository}/resolve/{revision}/{filename}?download=true"
        temporary = target / f".{filename}.part"
        curl = _curl_path()
        if curl:
            if filename == "model.bin":
                _download_large_file(curl, url, temporary, _remote_size(curl, url, filename))
                os.replace(temporary, target / filename)
                continue
            subprocess.run(
                [
                    curl,
                    "--fail",
                    "--location",
                    "--retry",
                    "3",
                    "--retry-delay",
                    "2",
                    "--output",
                    str(temporary),
                    url,
                ],
                check=True,
            )
            os.replace(temporary, target / filename)
            continue
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "PPT-Video-Workbench-ASR-Provisioner/1.0"},
        )
        with (
            urllib.request.urlopen(request, timeout=120) as response,
            temporary.open("wb") as handle,
        ):
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, target / filename)


def provision_model(
    root: Path,
    model: str,
    *,
    revision: str | None = None,
    downloader: Callable[..., Any] | None = None,
) -> Path:
    """Download a complete model snapshot into ``root/<model>`` atomically."""
    repository = MODEL_REPOSITORIES.get(model)
    if repository is None:
        raise ValueError(f"unsupported ASR model: {model}")
    selected_revision = revision or "main"
    target = (root / model).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if (target / "model.bin").is_file():
        manifest_path = target / "model-manifest.json"
        if manifest_path.is_file():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("revision") != selected_revision:
                raise RuntimeError("ASR model revision does not match the requested revision")
        else:
            _write_manifest(target, model=model, repository=repository, revision=selected_revision)
        return target
    temporary = target.with_name(f".{target.name}.download")
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True, exist_ok=False)
    try:
        if downloader is None:
            _download_snapshot(repository, temporary, selected_revision)
        else:
            downloader(
                repo_id=repository,
                revision=selected_revision,
                local_dir=str(temporary),
                local_dir_use_symlinks=False,
                allow_patterns=["config.json", "model.bin", "tokenizer.json", "vocabulary.*"],
            )
        required = [temporary / "config.json", temporary / "model.bin"]
        missing = [path.name for path in required if not path.is_file()]
        if missing:
            raise RuntimeError(f"ASR model snapshot is incomplete: {', '.join(missing)}")
        _write_manifest(temporary, model=model, repository=repository, revision=selected_revision)
        temporary.replace(target)
        return target
    except BaseException:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _write_manifest(target: Path, *, model: str, repository: str, revision: str) -> None:
    files = []
    for path in sorted(target.iterdir()):
        if not path.is_file() or path.name == "model-manifest.json":
            continue
        files.append(
            {
                "name": path.name,
                "size": path.stat().st_size,
                "sha256": _sha256(path),
            }
        )
    manifest = {
        "schema_version": "1.0",
        "model": model,
        "repository": repository,
        "revision": revision,
        "files": files,
    }
    temporary = target / ".model-manifest.json.part"
    temporary.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    temporary.replace(target / "model-manifest.json")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace-root", type=Path, required=True)
    parser.add_argument("--model", default="small", choices=sorted(MODEL_REPOSITORIES))
    parser.add_argument("--revision", required=True)
    args = parser.parse_args()
    target = provision_model(
        args.workspace_root / "settings" / "asr-models", args.model, revision=args.revision
    )
    manifest = json.loads((target / "model-manifest.json").read_text(encoding="utf-8"))
    print(
        json.dumps(
            {"model": args.model, "path": str(target), "status": "ready", "manifest": manifest},
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
