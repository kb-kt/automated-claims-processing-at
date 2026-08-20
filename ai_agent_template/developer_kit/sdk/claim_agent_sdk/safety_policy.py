from __future__ import annotations

from typing import Any


def apply_fail_closed_human_review(
    output: dict[str, Any],
    *,
    reason_code: str = "TOOL_FAILURE",
    reviewer_note: str,
) -> dict[str, Any]:
    """Apply the common fail-closed invariant without discarding provisional evidence."""

    output["recommended_decision"] = "human_review"
    output["requires_human_review"] = True
    output["reason_codes"] = _unique(
        list(output.get("reason_codes") or [])
        + [reason_code, "HUMAN_REVIEW_REQUIRED"]
    )
    output["reviewer_notes"] = _unique(
        list(output.get("reviewer_notes") or []) + [reviewer_note]
    )
    calculation = output.get("calculation") or {}
    if "payable_amount" in calculation:
        output["recommended_payable_amount"] = calculation["payable_amount"]
    return output


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))
