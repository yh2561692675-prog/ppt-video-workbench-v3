from enum import StrEnum


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRY_WAIT = "retry_wait"
    CANCELLING = "cancelling"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ActionType(StrEnum):
    CANCEL = "cancel"
    RETRY = "retry"


class ErrorCategory(StrEnum):
    ENVIRONMENT = "ENVIRONMENT"
    CONFIGURATION = "CONFIGURATION"
    AUTHENTICATION = "AUTHENTICATION"
    NETWORK = "NETWORK"
    PROVIDER = "PROVIDER"
    INPUT = "INPUT"
    PROCESSING = "PROCESSING"
    STORAGE = "STORAGE"
    QA = "QA"
    INTERNAL = "INTERNAL"
