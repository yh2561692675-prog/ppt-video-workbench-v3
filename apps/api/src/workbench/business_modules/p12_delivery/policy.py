from __future__ import annotations

import hashlib
import re
import zipfile
from pathlib import Path, PurePosixPath

from workbench.business_modules.p12_delivery.models import (
    DeliveryPolicy,
    MediaProbe,
    QualityCheck,
)

_SECRET = re.compile(
    rb"(?i)(?:bearer\s+[a-z0-9._~+/=-]{8,}|api[_-]?key\s*[:=]\s*\S{8,}|"
    rb"eyJ[a-z0-9_-]{8,}\.[a-z0-9_-]{8,}\.[a-z0-9_-]{8,})"
)
_USER_PATH = re.compile(rb"(?i)(?:[a-z]:\\users\\[^\\\s]+|/home/[^/\s]+)")
_SRT_TIME = re.compile(
    rb"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s+-->\s+"
    rb"(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)


def verify_package(
    archive_path: Path,
    expected_sha256: str,
    expected_files: dict[str, tuple[int, str]],
    probe: MediaProbe,
    policy: DeliveryPolicy,
) -> list[QualityCheck]:
    checks = [
        QualityCheck(
            code="package_hash",
            passed=_sha256(archive_path) == expected_sha256,
            action="rebuild package if the hash changed",
        ),
        QualityCheck(code="video_codec", passed=probe.video_codec.casefold() == policy.video_codec),
        QualityCheck(code="audio_codec", passed=probe.audio_codec.casefold() == policy.audio_codec),
        QualityCheck(
            code="resolution", passed=(probe.width, probe.height) == (policy.width, policy.height)
        ),
        QualityCheck(code="frame_rate", passed=abs(probe.fps - policy.fps) <= 0.01),
        QualityCheck(
            code="av_duration",
            passed=abs(probe.duration_ms - probe.audio_duration_ms) <= policy.duration_tolerance_ms,
        ),
    ]
    try:
        with zipfile.ZipFile(archive_path) as archive:
            members = archive.infolist()
            unsafe = [item for item in members if _unsafe_member(item)]
            checks.append(QualityCheck(code="archive_paths", passed=not unsafe))
            checks.append(QualityCheck(code="archive_crc", passed=archive.testzip() is None))
            names = {item.filename for item in members if not item.is_dir()}
            for relative_path, (size, digest) in sorted(expected_files.items()):
                passed = relative_path in names
                if passed:
                    content = archive.read(relative_path)
                    passed = len(content) == size and hashlib.sha256(content).hexdigest() == digest
                checks.append(
                    QualityCheck(
                        code="manifest_file_hash",
                        passed=passed,
                        location=relative_path,
                        action="rebuild the production package",
                    )
                )
            secret_locations: list[str] = []
            srt_ok = True
            for item in members:
                if item.is_dir() or item.file_size > 8 * 1024 * 1024:
                    continue
                suffix = PurePosixPath(item.filename).suffix.casefold()
                if suffix not in {".json", ".md", ".txt", ".srt", ".log"}:
                    continue
                content = archive.read(item)
                if _SECRET.search(content) or _USER_PATH.search(content):
                    secret_locations.append(item.filename)
                if suffix == ".srt" and not _srt_within(content, probe.duration_ms):
                    srt_ok = False
            checks.append(
                QualityCheck(
                    code="secret_residue",
                    passed=not secret_locations,
                    location=secret_locations[0] if secret_locations else None,
                    action="remove credential or user-path residue and rebuild",
                )
            )
            checks.append(QualityCheck(code="srt_bounds", passed=srt_ok))
    except (OSError, zipfile.BadZipFile, RuntimeError):
        checks.append(QualityCheck(code="archive_readable", passed=False))
    return checks


def _unsafe_member(item: zipfile.ZipInfo) -> bool:
    path = PurePosixPath(item.filename.replace("\\", "/"))
    mode = (item.external_attr >> 16) & 0o170000
    return path.is_absolute() or ".." in path.parts or mode == 0o120000 or bool(item.flag_bits & 1)


def _srt_within(content: bytes, duration_ms: int) -> bool:
    previous_end = 0
    found = False
    for match in _SRT_TIME.finditer(content):
        found = True
        values = [int(item) for item in match.groups()]
        start = ((values[0] * 60 + values[1]) * 60 + values[2]) * 1000 + values[3]
        end = ((values[4] * 60 + values[5]) * 60 + values[6]) * 1000 + values[7]
        if start < previous_end or end <= start or end > duration_ms:
            return False
        previous_end = end
    return found


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
