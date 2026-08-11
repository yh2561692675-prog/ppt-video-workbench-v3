from __future__ import annotations

from workbench.diagnostics.p2_privacy import scan_p2_summary


def test_p2_privacy_scan_returns_codes_without_echoing_sensitive_values() -> None:
    findings = scan_p2_summary(
        {
            "token": "Bearer do-not-leak",
            "prompt": "private body",
            "owner": "alice@example.com",
            "path": r"C:\Users\Alice\project\deck.pptx",
        }
    )
    codes = {item.code for item in findings}
    assert {"secret_key", "secret_value", "raw_body", "user_email", "absolute_path"} <= codes
    assert all("do-not-leak" not in item.field for item in findings)
