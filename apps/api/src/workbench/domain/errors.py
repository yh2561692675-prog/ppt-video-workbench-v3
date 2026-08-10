class WorkbenchError(Exception):
    """Base class for errors that are safe to map to ProblemDetails."""

    code = "workbench_error"
    action = "请检查输入后重试"
    blocking = True


class UnsupportedManifestVersion(WorkbenchError):
    code = "unsupported_manifest_version"
    action = "请先使用兼容版本完成项目迁移"


class ProjectPathViolation(WorkbenchError):
    code = "project_path_violation"
    action = "请选择工作区内的项目目录"


class ManifestRecoveryError(WorkbenchError):
    code = "manifest_recovery_failed"
    action = "请从项目备份恢复或联系技术支持"
