from __future__ import annotations

from effects.batch import BatchEffectRunner, PageRenderError


def test_batch_recovery_retries_page_then_falls_back_and_continues() -> None:
    attempts: list[str] = []

    def render(page_id: str) -> str:
        attempts.append(page_id)
        if page_id == "p2" and attempts.count(page_id) == 1:
            raise PageRenderError("template", "synthetic failure")
        return f"rendered:{page_id}"

    runner = BatchEffectRunner(render, max_retries=1)
    result = runner.run(["p1", "p2", "p3"])

    assert result.completed == {"p1", "p2", "p3"}
    assert result.failed == set()
    assert attempts == ["p1", "p2", "p2", "p3"]
    assert result.records["p2"].retries == 1


def test_batch_recovery_uses_safe_fallback_after_retry_budget() -> None:
    def render(_: str) -> str:
        raise PageRenderError("background", "persistent failure")

    result = BatchEffectRunner(render, max_retries=1).run(["p1", "p2"])

    assert result.completed == {"p1", "p2"}
    assert result.records["p1"].status == "fallback"
    assert result.records["p1"].fallback_template == "SafeSlide"
