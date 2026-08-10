from __future__ import annotations

from dataclasses import dataclass, field
from collections.abc import Callable, Iterable


class PageRenderError(RuntimeError):
    def __init__(self, stage: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage


@dataclass
class PageRecord:
    page_id: str
    status: str = "pending"
    retries: int = 0
    output: str | None = None
    fallback_template: str | None = None
    error_stage: str | None = None


@dataclass
class BatchResult:
    records: dict[str, PageRecord] = field(default_factory=dict)

    @property
    def completed(self) -> set[str]:
        return {page_id for page_id, record in self.records.items() if record.status in {"success", "fallback"}}

    @property
    def failed(self) -> set[str]:
        return {page_id for page_id, record in self.records.items() if record.status == "failed"}


class BatchEffectRunner:
    def __init__(self, render_page: Callable[[str], str], *, max_retries: int = 1) -> None:
        self.render_page = render_page
        self.max_retries = max(0, max_retries)

    def run(self, page_ids: Iterable[str], *, existing: BatchResult | None = None) -> BatchResult:
        result = existing or BatchResult()
        for page_id in page_ids:
            record = result.records.setdefault(page_id, PageRecord(page_id))
            if record.status in {"success", "fallback"}:
                continue
            record.status = "rendering"
            while True:
                try:
                    record.output = self.render_page(page_id)
                    record.status = "success"
                    record.error_stage = None
                    break
                except PageRenderError as error:
                    record.error_stage = error.stage
                    if record.retries < self.max_retries:
                        record.retries += 1
                        continue
                    record.status = "fallback"
                    record.fallback_template = "SafeSlide"
                    record.output = None
                    break
                except Exception:
                    record.error_stage = "unknown"
                    if record.retries < self.max_retries:
                        record.retries += 1
                        continue
                    record.status = "fallback"
                    record.fallback_template = "SafeSlide"
                    break
        return result
