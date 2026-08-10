from __future__ import annotations


def test_p12_delivery_refuses_when_preflight_is_blocked() -> None:
    from workbench.business_modules.p12_delivery.runner import evaluate_delivery

    result = evaluate_delivery({"preflight_allowed": False, "rendered": True, "artifacts": []})

    assert result["decision"] == "blocked"
    assert "preflight_blocked" in result["reasons"]
