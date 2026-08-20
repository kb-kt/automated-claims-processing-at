from __future__ import annotations

from typing import Any

from .errors import SafetyValidationError


EVALUATION_ONLY_KEYS = {
    "answer_label",
    "fraud_label",
    "fraud_labels",
    "gold_label",
    "ground_truth",
    "target_decision",
}

AGENT_OUTPUT_KEYS = {
    "calculation",
    "confidence",
    "coverage_code",
    "coverage_name",
    "fraud_suspected",
    "missing_documents",
    "policy_basis",
    "reason_codes",
    "recommended_decision",
    "recommended_payable_amount",
    "requires_human_review",
    "review_summary",
    "reviewer_notes",
}


def find_label_leakage(
    value: Any,
    *,
    forbid_agent_output_fields: bool = False,
) -> list[str]:
    """Return JSON paths containing evaluation-only or answer-bearing fields."""

    findings: list[str] = []
    _scan(
        value,
        path="$",
        findings=findings,
        forbid_agent_output_fields=forbid_agent_output_fields,
    )
    return sorted(set(findings))


def assert_no_label_leakage(
    value: Any,
    *,
    context: str = "runtime payload",
    forbid_agent_output_fields: bool = False,
) -> None:
    findings = find_label_leakage(
        value,
        forbid_agent_output_fields=forbid_agent_output_fields,
    )
    if findings:
        raise SafetyValidationError(
            f"LABEL_LEAKAGE_DETECTED: {context} contains evaluation-only fields.",
            findings,
        )


def _scan(
    value: Any,
    *,
    path: str,
    findings: list[str],
    forbid_agent_output_fields: bool,
) -> None:
    if isinstance(value, dict):
        for key, nested in value.items():
            key_text = str(key)
            key_path = f"{path}.{key_text}"
            if (
                key_text.startswith("expected_")
                or key_text in EVALUATION_ONLY_KEYS
                or (
                    forbid_agent_output_fields
                    and path == "$"
                    and key_text in AGENT_OUTPUT_KEYS
                )
            ):
                findings.append(key_path)
            _scan(
                nested,
                path=key_path,
                findings=findings,
                forbid_agent_output_fields=forbid_agent_output_fields,
            )
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _scan(
                item,
                path=f"{path}[{index}]",
                findings=findings,
                forbid_agent_output_fields=forbid_agent_output_fields,
            )
