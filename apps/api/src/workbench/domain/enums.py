from enum import StrEnum


class NodeStatus(StrEnum):
    NOT_STARTED = "not_started"
    RUNNING = "running"
    NEEDS_CONFIRMATION = "needs_confirmation"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    PAUSE_REQUESTED = "pause_requested"
    PAUSED = "paused"
    NEEDS_CONFIRMATION = "needs_confirmation"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobType(StrEnum):
    PARSE_MATERIALS = "parse_materials"
    GENERATE_NARRATION = "generate_narration"
    TRANSCRIBE_AUDIO = "transcribe_audio"
    SYNTHESIZE_PAGE = "synthesize_page"
    BUILD_SUBTITLES = "build_subtitles"
    RENDER_PAGE = "render_page"
    EXPORT_PACKAGE = "export_package"
    PRESENTER_SYNC = "presenter_sync"
    RENDER_PREVIEW = "render_preview"
    DERIVE_ASSET = "derive_asset"
    BUILD_PROXY = "build_proxy"
    BUILD_WAVEFORM = "build_waveform"
    TRANSLATE_SUBTITLES = "translate_subtitles"
    QUALITY_SCAN = "quality_scan"
    RENDER_EXPORT = "render_export"


class AttemptStatus(StrEnum):
    CLAIMED = "claimed"
    RUNNING = "running"
    PAUSED = "paused"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class LeaseStatus(StrEnum):
    ACTIVE = "active"
    RELEASED = "released"
    EXPIRED = "expired"


class WorkerStatus(StrEnum):
    ACTIVE = "active"
    DRAINING = "draining"
    OFFLINE = "offline"
