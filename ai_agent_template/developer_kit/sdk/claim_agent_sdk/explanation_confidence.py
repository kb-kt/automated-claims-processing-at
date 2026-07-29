from __future__ import annotations

from typing import Any


def evaluate_explanation_confidence(agent_output: dict[str, Any]) -> dict[str, Any]:
    """Score whether LLM-facing explanations stay faithful to tool/rule output."""

    issues: list[str] = []
    text = _combined_explanation_text(agent_output)
    calculation_alignment = _calculation_alignment(agent_output, issues)
    citation_alignment = _citation_alignment(agent_output.get("policy_basis") or [], issues)
    unsupported_claims_detected = _detect_unsupported_claims(agent_output, text, issues)
    _check_required_signal_mentions(agent_output, text, issues)

    score = _score(
        issues=issues,
        citation_alignment=citation_alignment,
        calculation_alignment=calculation_alignment,
        unsupported_claims_detected=unsupported_claims_detected,
    )
    return {
        "score": score,
        "source": "llm_output_validation",
        "faithfulness_to_tools": _level(score),
        "citation_alignment": citation_alignment,
        "calculation_alignment": calculation_alignment,
        "unsupported_claims_detected": unsupported_claims_detected,
        "uncertainty_level": (agent_output.get("confidence_assessment") or {}).get(
            "uncertainty_level",
            "medium",
        ),
        "validation_issues": issues[:8],
    }


def _combined_explanation_text(agent_output: dict[str, Any]) -> str:
    parts = [str(agent_output.get("review_summary") or "")]
    notes = agent_output.get("reviewer_notes") or []
    if isinstance(notes, list):
        parts.extend(str(note) for note in notes)
    return " ".join(parts).lower()


def _calculation_alignment(agent_output: dict[str, Any], issues: list[str]) -> str:
    calculation = agent_output.get("calculation") or {}
    if agent_output.get("recommended_payable_amount") != calculation.get("payable_amount"):
        issues.append("recommended_payable_amount does not match calculation.payable_amount")
        return "fail"
    return "pass"


def _citation_alignment(policy_basis: list[dict[str, Any]], issues: list[str]) -> str:
    if not policy_basis:
        issues.append("policy_basis is missing")
        return "low"
    citation_count = sum(1 for item in policy_basis if item.get("citation_id") or item.get("clause_id"))
    if citation_count == len(policy_basis):
        return "high"
    if citation_count > 0:
        issues.append("some policy_basis entries lack citation_id or clause_id")
        return "medium"
    issues.append("policy_basis lacks citation_id or clause_id")
    return "low"


def _detect_unsupported_claims(agent_output: dict[str, Any], text: str, issues: list[str]) -> bool:
    unsupported = False
    finalization_terms = [
        "final payment confirmed",
        "payment is confirmed",
        "claim is approved",
        "지급 확정",
        "최종 지급",
        "승인 확정",
    ]
    if any(term in text for term in finalization_terms):
        issues.append("explanation uses final-decision language")
        unsupported = True

    decision = agent_output.get("recommended_decision")
    if decision in {"pay", "partial_pay"} and any(term in text for term in ["deny", "부지급"]):
        issues.append("explanation mentions denial while recommendation is payable")
        unsupported = True
    if decision == "deny" and any(term in text for term in ["pay recommended", "지급 권고"]):
        issues.append("explanation mentions payment while recommendation is denial")
        unsupported = True
    return unsupported


def _check_required_signal_mentions(agent_output: dict[str, Any], text: str, issues: list[str]) -> None:
    if agent_output.get("requires_human_review") and not _has_any(
        text,
        ["human review", "reviewer", "confirmation", "사람 심사", "심사자", "확인"],
    ):
        issues.append("human review requirement is not reflected in explanation")
    if agent_output.get("fraud_suspected") and not _has_any(
        text,
        ["fraud", "duplicate", "suspicious", "사기", "중복", "위조", "의심"],
    ):
        issues.append("fraud signal is not reflected in explanation")
    if agent_output.get("missing_documents") and not _has_any(
        text,
        ["document", "documents", "서류", "보완"],
    ):
        issues.append("missing document requirement is not reflected in explanation")


def _score(
    *,
    issues: list[str],
    citation_alignment: str,
    calculation_alignment: str,
    unsupported_claims_detected: bool,
) -> float:
    score = 1.0
    score -= 0.30 if calculation_alignment == "fail" else 0
    score -= 0.20 if citation_alignment == "medium" else 0
    score -= 0.35 if citation_alignment == "low" else 0
    score -= 0.30 if unsupported_claims_detected else 0
    score -= min(0.30, 0.08 * len(issues))
    return round(max(0.0, min(1.0, score)), 2)


def _level(score: float) -> str:
    if score >= 0.9:
        return "high"
    if score >= 0.75:
        return "medium"
    return "low"


def _has_any(text: str, terms: list[str]) -> bool:
    return any(term in text for term in terms)
