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
