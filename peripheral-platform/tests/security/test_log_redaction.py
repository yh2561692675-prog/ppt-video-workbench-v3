from __future__ import annotations

from peripheral_host.logging_config import redact


def test_redact_hides_sensitive_keys_bearer_and_windows_user_paths() -> None:
    original = {
        "Authorization": "Bearer test-secret-token",
        "nested": {
            "API_KEY": "raw-api-key",
            "path": r"C:\Users\Alice\Documents\source.pptx",
        },
        "message": "request used bearer another-secret and C:/Users/Bob/video.mp4",
    }

    redacted = redact(original)
    rendered = repr(redacted)

    assert redacted["Authorization"] == "***"  # type: ignore[index]
    assert redacted["nested"]["API_KEY"] == "***"  # type: ignore[index]
    assert "test-secret-token" not in rendered
    assert "another-secret" not in rendered
    assert "Alice" not in rendered
    assert "Bob" not in rendered
    assert "%USERPROFILE%" in rendered


def test_redact_summarizes_parameter_text_without_raw_content() -> None:
    secret_text = "draft narration that must never reach logs"

    redacted = redact({"parameters": {"text": secret_text, "delay_ms": 0}})
    rendered = repr(redacted)

    summary = redacted["parameters"]["text"]  # type: ignore[index]
    assert summary["character_count"] == len(secret_text)
    assert len(summary["sha256_prefix"]) == 12
    assert secret_text not in rendered
    assert redacted["parameters"]["delay_ms"] == 0  # type: ignore[index]


def test_redact_handles_sequences_without_mutating_input() -> None:
    original = [{"token": "one"}, "Bearer two"]

    redacted = redact(original)

    assert redacted == [{"token": "***"}, "***"]
    assert original == [{"token": "one"}, "Bearer two"]
