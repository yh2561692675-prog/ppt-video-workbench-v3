from __future__ import annotations


class RenderJobFailure(RuntimeError):
    code = "render_job_failed"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code is not None:
            self.code = code


class RenderInputStale(RenderJobFailure):
    code = "render_input_stale"


class RenderInputChanged(RenderJobFailure):
    code = "render_input_changed"


class RendererRuntimeUnavailable(RenderJobFailure):
    code = "renderer_runtime_unavailable"


class RenderPageFailed(RenderJobFailure):
    code = "render_page_failed"


class FfmpegMuxFailed(RenderJobFailure):
    code = "ffmpeg_mux_failed"


class FfmpegConcatFailed(RenderJobFailure):
    code = "ffmpeg_concat_failed"


class MediaValidationFailed(RenderJobFailure):
    code = "media_validation_failed"


class PackageValidationFailed(RenderJobFailure):
    code = "package_validation_failed"


class RenderDiskFull(RenderJobFailure):
    code = "render_disk_full"
