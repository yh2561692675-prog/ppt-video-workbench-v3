from __future__ import annotations

import argparse
import hashlib
import os
from datetime import UTC
from pathlib import Path
from typing import Any
from uuid import UUID, uuid5

from peripheral_contracts import BusinessResultManifest, ErrorCategory, JobEnvelope

from workbench.audio.alignment import PageNarration, align_pages, export_page_wavs
from workbench.audio.diff import NarrationText, compare
from workbench.audio.ffmpeg import AudioNormalizationError, normalize_audio
from workbench.audio.models import WhisperModelManager
from workbench.audio.transcriber import ModelUnavailable, Transcriber, TranscriptionError
from workbench.business_modules.p07_audio.models import (
    ArtifactDescriptor,
    AudioAlignParameters,
    AudioNormalizeParameters,
    AudioPipelinePayload,
    AudioSynthesizeParameters,
    AudioTranscribeParameters,
    PageAudioResult,
    RemoteRequestAudit,
)
from workbench.business_modules.p07_audio.policy import (
    PaidRequestCheckpoint,
    PaidRequestRecord,
    ensure_route,
    synthesis_cache_key,
)
from workbench.business_modules.runtime import (
    BusinessExecution,
    BusinessModuleError,
    StagedArtifact,
    business_input_fingerprint,
    business_parameters,
    execute_business_handler,
    project_revision,
)
from workbench.domain.audio import AudioImportRecord
from workbench.domain.enums import NodeStatus
from workbench.domain.models import AudioRecord, AuditEvent, ProjectManifest
from workbench.integrations.heygen.client import HeyGenClient, HeyGenIntegrationError


class AudioRejected(ValueError):
    pass


def build_audio_pipeline(metadata: dict[str, Any], pages: list[dict[str, Any]]) -> dict[str, Any]:
    """Legacy pure helper retained for compatibility with older callers."""
    duration_ms = int(metadata.get("duration_ms", 0))
    sample_rate = int(metadata.get("sample_rate", 0))
    channels = int(metadata.get("channels", 0))
    if duration_ms <= 0 or sample_rate <= 0 or channels not in {1, 2}:
        raise AudioRejected("audio metadata is invalid")
    if not pages:
        raise AudioRejected("audio pipeline requires page durations")
    total = sum(int(page.get("duration_ms", 0)) for page in pages)
    if total != duration_ms:
        raise AudioRejected("page durations do not cover the audio duration")
    start = 0
    segments: list[dict[str, Any]] = []
    for page in pages:
        page_duration = int(page["duration_ms"])
        if page_duration <= 0 or not isinstance(page.get("page_id"), str):
            raise AudioRejected("page audio duration is invalid")
        segments.append(
            {"page_id": page["page_id"], "start_ms": start, "end_ms": start + page_duration}
        )
        start += page_duration
    return {
        "normalized": {
            "duration_ms": duration_ms,
            "sample_rate": sample_rate,
            "channels": channels,
        },
        "segments": segments,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    job = JobEnvelope.model_validate_json(args.request.read_text(encoding="utf-8-sig"))
    execution = execute_business_handler(job, args.result.parent, args.result, "P07", _handle)
    return 0 if execution.outcome == "succeeded" else 1


def _handle(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    if job.job_type == "audio.normalize":
        return _normalize(job, attempt_root)
    if job.job_type == "audio.transcribe":
        return _transcribe(job, attempt_root)
    if job.job_type == "audio.align":
        return _align(job, attempt_root)
    if job.job_type == "audio.synthesize":
        return _synthesize(job, attempt_root)
    raise AudioRejected(f"unsupported P07 job type: {job.job_type}")


def _normalize(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = AudioNormalizeParameters.model_validate(business_parameters(job))
    ensure_route("local", parameters.existing_route)
    source = _single_input(job, attempt_root)
    try:
        normalized = normalize_audio(source, attempt_root / "normalized")
    except AudioNormalizationError as error:
        raise BusinessModuleError(
            str(error),
            category=ErrorCategory.PROCESSING,
            code="AUDIO_NORMALIZATION_FAILED",
            retryable=False,
        ) from error
    fingerprint = business_input_fingerprint(job)
    relative_path = "05_音频/规范化/audio.normalized.wav"
    descriptor = _descriptor("normalized-audio", relative_path, normalized.wav_path)
    imported = AudioImportRecord(
        id=uuid5(job.project_id, f"P07:audio-import:{fingerprint}"),
        original_relative_path=parameters.source_name,
        normalized_relative_path=relative_path,
        duration_ms=normalized.duration_ms,
        sample_rate=normalized.sample_rate,
        channels=normalized.channels,
        sha256=normalized.sha256,
        peak_dbfs=normalized.quality.peak_dbfs,
        silence_ratio=normalized.quality.silence_ratio,
        silence_intervals_ms=normalized.quality.silence_intervals_ms,
        needs_confirmation=normalized.quality.needs_confirmation,
        imported_at=job.created_at,
    )
    payload = AudioPipelinePayload(
        operation="normalize",
        route="local",
        generated_at=job.created_at,
        audio_import=imported,
        artifacts=(descriptor,),
    )
    return _execution(
        job,
        payload,
        (StagedArtifact("normalized-audio", "wav", normalized.wav_path),),
    )


def _transcribe(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = AudioTranscribeParameters.model_validate(business_parameters(job))
    ensure_route("local", parameters.existing_route)
    source = _single_input(job, attempt_root)
    model_root_value = os.environ.pop("WORKBENCH_WHISPER_MODEL_ROOT", "")
    if not model_root_value:
        raise BusinessModuleError(
            "local transcription model root is unavailable",
            category=ErrorCategory.ENVIRONMENT,
            code="ASR_MODEL_ROOT_UNAVAILABLE",
            retryable=False,
        )
    try:
        transcript = Transcriber(
            WhisperModelManager(Path(model_root_value)), model=parameters.model
        ).transcribe(
            source,
            language=parameters.language,
            device=parameters.device,
            checkpoint=attempt_root / "recovery" / "transcription.json",
        )
    except ModelUnavailable as error:
        raise BusinessModuleError(
            str(error),
            category=ErrorCategory.ENVIRONMENT,
            code="ASR_MODEL_UNAVAILABLE",
            retryable=False,
        ) from error
    except TranscriptionError as error:
        raise BusinessModuleError(
            str(error),
            category=ErrorCategory.PROCESSING,
            code="ASR_TRANSCRIPTION_FAILED",
            retryable=False,
        ) from error
    payload = AudioPipelinePayload(
        operation="transcribe",
        route="local",
        generated_at=job.created_at,
        transcript=transcript,
    )
    return _execution(job, payload)


def _align(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = AudioAlignParameters.model_validate(business_parameters(job))
    ensure_route("local", parameters.existing_route)
    source = _single_input(job, attempt_root)
    narrations = [
        PageNarration(page_id=item.page_id, text=item.text) for item in parameters.narrations
    ]
    timeline = align_pages(
        parameters.transcript,
        narrations,
        silence_intervals_ms=parameters.audio_import.silence_intervals_ms,
        duration_ms=parameters.audio_import.duration_ms,
        min_page_ms=parameters.min_page_ms,
    )
    differences = compare(
        parameters.transcript,
        [NarrationText(page_id=item.page_id, text=item.text) for item in parameters.narrations],
    )
    exported = export_page_wavs(source, timeline, attempt_root / "pages")
    by_page = {item.page_id: item for item in parameters.narrations}
    artifacts: list[StagedArtifact] = []
    descriptors: list[ArtifactDescriptor] = []
    page_audio: list[PageAudioResult] = []
    for order, item in enumerate(exported, start=1):
        narration = by_page[item.page_id]
        logical_name = f"page-audio-{order:03d}"
        relative_path = f"05_音频/分页面/page-{order:03d}.wav"
        descriptors.append(_descriptor(logical_name, relative_path, item.path))
        artifacts.append(StagedArtifact(logical_name, "wav", item.path))
        cache_key = hashlib.sha256(
            f"{parameters.audio_import.sha256}|{narration.revision_id}|{item.start_ms}|{item.end_ms}".encode()
        ).hexdigest()
        page_audio.append(
            PageAudioResult(
                id=uuid5(item.page_id, f"P07:local:{cache_key}"),
                page_id=item.page_id,
                source="local",
                relative_path=relative_path,
                duration_ms=item.duration_ms,
                cache_key=cache_key,
                narration_revision_id=narration.revision_id,
            )
        )
    payload = AudioPipelinePayload(
        operation="align",
        route="local",
        generated_at=job.created_at,
        transcript=parameters.transcript,
        differences=tuple(differences),
        timeline=timeline,
        page_audio=tuple(page_audio),
        artifacts=tuple(descriptors),
    )
    return _execution(job, payload, tuple(artifacts))


def _synthesize(job: JobEnvelope, attempt_root: Path) -> BusinessExecution:
    parameters = AudioSynthesizeParameters.model_validate(business_parameters(job))
    ensure_route("heygen", parameters.existing_route)
    profile_id, base_url, api_key = _consume_heygen_environment(parameters.profile_id)
    existing = {item.page_id: item for item in parameters.existing_page_audio}
    checkpoint = PaidRequestCheckpoint(attempt_root / "recovery" / "paid-requests.json")
    remote_state = checkpoint.load()
    client = HeyGenClient()
    page_audio: list[PageAudioResult] = []
    audits: list[RemoteRequestAudit] = []
    artifacts: list[StagedArtifact] = []
    descriptors: list[ArtifactDescriptor] = []
    for narration in parameters.narrations:
        cache_key = synthesis_cache_key(
            narration.revision_id, parameters.voice_id, parameters.speed
        )
        prior = existing.get(narration.page_id)
        if prior is not None and prior.cache_key == cache_key:
            page_audio.append(
                PageAudioResult(
                    id=uuid5(narration.page_id, f"P07:heygen:{cache_key}"),
                    page_id=narration.page_id,
                    source="heygen",
                    relative_path=prior.relative_path,
                    duration_ms=prior.duration_ms,
                    cache_key=cache_key,
                    narration_revision_id=narration.revision_id,
                    voice_id=prior.voice_id,
                    remote_request_id=prior.remote_request_id,
                    cached=True,
                )
            )
            audits.append(
                RemoteRequestAudit(
                    page_id=narration.page_id,
                    cache_key=cache_key,
                    request_id=prior.remote_request_id,
                    reused=True,
                )
            )
            continue
        recovered = remote_state.get(narration.page_id)
        reused = recovered is not None and recovered.cache_key == cache_key
        try:
            if not reused:
                speech = client.generate_speech(
                    api_key,
                    text=narration.text,
                    voice_id=parameters.voice_id,
                    speed=parameters.speed,
                    language="zh",
                    base_url=base_url,
                )
                recovered = PaidRequestRecord(
                    page_id=narration.page_id,
                    cache_key=cache_key,
                    request_id=speech.request_id,
                    audio_url=str(speech.audio_url),
                )
                remote_state[narration.page_id] = recovered
                checkpoint.save(remote_state)
            if recovered is None:
                raise AssertionError("paid request recovery state unexpectedly missing")
            downloaded = client.download(recovered.audio_url)
        except HeyGenIntegrationError as error:
            raise _heygen_error(error) from error
        suffix = ".wav" if "wav" in downloaded.content_type else ".mp3"
        remote = attempt_root / "remote" / f"{narration.page_order:03d}{suffix}"
        remote.parent.mkdir(parents=True, exist_ok=True)
        remote.write_bytes(downloaded.content)
        try:
            normalized = normalize_audio(remote, attempt_root / "normalized")
        except AudioNormalizationError as error:
            raise BusinessModuleError(
                str(error),
                category=ErrorCategory.PROCESSING,
                code="HEYGEN_AUDIO_INVALID",
                retryable=True,
            ) from error
        logical_name = f"page-audio-{narration.page_order:03d}"
        relative_path = f"05_音频/HeyGen/page-{narration.page_order:03d}.wav"
        artifacts.append(StagedArtifact(logical_name, "wav", normalized.wav_path))
        descriptors.append(_descriptor(logical_name, relative_path, normalized.wav_path))
        page_audio.append(
            PageAudioResult(
                id=uuid5(narration.page_id, f"P07:heygen:{cache_key}"),
                page_id=narration.page_id,
                source="heygen",
                relative_path=relative_path,
                duration_ms=normalized.duration_ms,
                cache_key=cache_key,
                narration_revision_id=narration.revision_id,
                voice_id=parameters.voice_id,
                remote_request_id=recovered.request_id,
                cached=reused,
            )
        )
        audits.append(
            RemoteRequestAudit(
                page_id=narration.page_id,
                cache_key=cache_key,
                request_id=recovered.request_id,
                reused=reused,
            )
        )
    payload = AudioPipelinePayload(
        operation="synthesize",
        route="heygen",
        generated_at=job.created_at,
        page_audio=tuple(page_audio),
        remote_requests=tuple(audits),
        artifacts=tuple(descriptors),
    )
    _ = profile_id  # Profile identity is validated but credentials never enter the result.
    return _execution(job, payload, tuple(artifacts))


def _execution(
    job: JobEnvelope,
    payload: AudioPipelinePayload,
    artifacts: tuple[StagedArtifact, ...] = (),
) -> BusinessExecution:
    fingerprint = business_input_fingerprint(job)
    result = BusinessResultManifest(
        schema_version="1.0",
        module_id="P07",
        job_type=job.job_type,
        project_id=job.project_id,
        project_revision=project_revision(job),
        input_fingerprint=fingerprint,
        cache_key=hashlib.sha256(f"{fingerprint}:{job.job_type}".encode()).hexdigest(),
        result_type="audio_pipeline",
        payload=payload.model_dump(mode="json"),
    )
    return BusinessExecution(result, artifacts)


def _single_input(job: JobEnvelope, attempt_root: Path) -> Path:
    if len(job.inputs) != 1:
        raise AudioRejected("audio job requires exactly one staged input")
    reference = job.inputs[0]
    source = (attempt_root / reference.path).resolve()
    if not source.is_relative_to(attempt_root.resolve()) or not source.is_file():
        raise AudioRejected("audio input escapes the attempt directory")
    content = source.read_bytes()
    if (
        len(content) != reference.size_bytes
        or hashlib.sha256(content).hexdigest() != reference.sha256
    ):
        raise AudioRejected("audio input changed after host staging")
    return source


def _descriptor(logical_name: str, relative_path: str, path: Path) -> ArtifactDescriptor:
    content = path.read_bytes()
    return ArtifactDescriptor(
        logical_name=logical_name,
        relative_path=relative_path,
        size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
    )


def _consume_heygen_environment(expected_profile_id: UUID) -> tuple[UUID, str, str]:
    values = {
        name: os.environ.pop(name, "")
        for name in (
            "WORKBENCH_HEYGEN_PROFILE_ID",
            "WORKBENCH_HEYGEN_BASE_URL",
            "WORKBENCH_HEYGEN_API_KEY",
        )
    }
    try:
        profile_id = UUID(values["WORKBENCH_HEYGEN_PROFILE_ID"])
    except ValueError as error:
        raise BusinessModuleError(
            "HeyGen credential environment is unavailable",
            category=ErrorCategory.ENVIRONMENT,
            code="HEYGEN_CREDENTIAL_UNAVAILABLE",
            retryable=False,
        ) from error
    if profile_id != expected_profile_id or not all(values.values()):
        raise BusinessModuleError(
            "HeyGen credential environment does not match the requested profile",
            category=ErrorCategory.ENVIRONMENT,
            code="HEYGEN_CREDENTIAL_MISMATCH",
            retryable=False,
        )
    return profile_id, values["WORKBENCH_HEYGEN_BASE_URL"], values["WORKBENCH_HEYGEN_API_KEY"]


def _heygen_error(error: HeyGenIntegrationError) -> BusinessModuleError:
    if error.code == "heygen_authentication_failed":
        category, retryable = ErrorCategory.AUTHENTICATION, False
    elif error.code == "heygen_quota_exhausted":
        category, retryable = ErrorCategory.PROVIDER, False
    elif error.code == "heygen_rate_limited":
        category, retryable = ErrorCategory.PROVIDER, True
    else:
        category, retryable = ErrorCategory.NETWORK, True
    return BusinessModuleError(
        str(error), category=category, code=error.code.upper(), retryable=retryable
    )


def project_audio_pipeline(result: BusinessResultManifest, project_dir: Path) -> None:
    payload = AudioPipelinePayload.model_validate(result.payload)
    manifest_path = project_dir / "project.json"
    manifest = ProjectManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    pages = {page.id: page for page in manifest.pages}
    if manifest.pages and any(
        page.narration is None or page.narration.confirmed_revision_id != page.narration.revision_id
        for page in manifest.pages
    ):
        raise ValueError("P07_GATE_BLOCKED: every current narration revision must be confirmed")
    existing_routes = {
        page.audio.source
        for page in manifest.pages
        if page.audio is not None and page.audio.status is NodeStatus.COMPLETED
    }
    if existing_routes and existing_routes != {payload.route}:
        raise ValueError("AUDIO_ROUTE_CONFLICT: current project uses another audio route")
    for item in payload.page_audio:
        page = pages.get(item.page_id)
        if page is None:
            raise ValueError(f"audio page does not exist: {item.page_id}")
        narration = page.narration
        if (
            narration is None
            or narration.revision_id != item.narration_revision_id
            or narration.confirmed_revision_id != item.narration_revision_id
        ):
            raise ValueError("STALE_NARRATION_REVISION: page audio targets an unconfirmed revision")

    changed_page_ids: list[str] = []
    for item in payload.page_audio:
        page = pages[item.page_id]
        existing = page.audio
        if existing is None or existing.cache_key != item.cache_key:
            changed_page_ids.append(str(item.page_id))
        pages[item.page_id] = page.model_copy(
            update={
                "audio": AudioRecord(
                    id=item.id,
                    status=NodeStatus.COMPLETED,
                    source=item.source,
                    relative_path=item.relative_path,
                    duration_ms=item.duration_ms,
                    cache_key=item.cache_key,
                    narration_revision_id=item.narration_revision_id,
                    voice_id=item.voice_id,
                    remote_request_id=item.remote_request_id,
                )
            }
        )
    updates: dict[str, Any] = {
        "pages": sorted(pages.values(), key=lambda page: page.order),
        "audit_log": [
            *manifest.audit_log,
            AuditEvent(
                action=f"audio_{payload.operation}_projected",
                occurred_at=payload.generated_at.astimezone(UTC),
                details={
                    "route": payload.route,
                    "changed_page_ids": changed_page_ids,
                    "remote_request_ids": [item.request_id for item in payload.remote_requests],
                },
            ),
        ],
    }
    if payload.audio_import is not None:
        updates["audio_import"] = payload.audio_import
    if payload.transcript is not None:
        updates["transcript"] = payload.transcript
    if payload.operation == "align":
        updates["audio_differences"] = list(payload.differences)
        updates["audio_timeline"] = payload.timeline
    if changed_page_ids:
        updates["subtitle_artifact"] = None
        updates["video_preflight"] = None
        updates["video_export"] = None
    updated = manifest.model_copy(update=updates)
    temporary = manifest_path.with_name(".project.json.s1.tmp")
    temporary.write_text(updated.model_dump_json(indent=2) + "\n", encoding="utf-8", newline="\n")
    os.replace(temporary, manifest_path)


if __name__ == "__main__":
    raise SystemExit(main())
