from __future__ import annotations

from datetime import date
from typing import Any

from .base import SyntheticToolPlugin


class SyntheticRiskCheckerPlugin(SyntheticToolPlugin):
    name = "risk_checker"
    contract_name = "risk_checker"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        insured_profile = payload.get("insured_profile", {})
        claim = payload.get("claim", {})
        history = payload.get("claim_history", {})
        signals = payload.get("signals", {})
        reason_codes = _risk_reason_codes(insured_profile, claim, history, signals)
        return self.ok(
            {
                "requires_human_review": bool(reason_codes),
                "risk_reason_codes": reason_codes,
            }
        )


def _risk_reason_codes(
    insured_profile: dict[str, Any],
    claim: dict[str, Any],
    history: dict[str, Any],
    signals: dict[str, Any],
) -> list[str]:
    reasons: list[str] = []
    claimed_amount = int(claim.get("claimed_amount", 0))
    care_setting = claim.get("care_setting")
    if care_setting == "outpatient" and claimed_amount >= 1_000_000:
        reasons.append("HIGH_OUTPATIENT_AMOUNT")
    if care_setting == "inpatient" and claimed_amount >= 10_000_000:
        reasons.append("HIGH_INPATIENT_AMOUNT")
    age_at_service = int(insured_profile.get("age_at_service", -1))
    if age_at_service < 15 or age_at_service >= 80:
        reasons.append("AGE_BASED_REVIEW_REQUIRED")
    if int(history.get("same_diagnosis_claims_90d", 0)) >= 3:
        reasons.append("REPEATED_SAME_DIAGNOSIS")
    if int(history.get("manual_therapy_count_180d", 0)) >= 20:
        reasons.append("FREQUENT_MANUAL_THERAPY")
    if _days_between(claim.get("incident_date"), claim.get("treatment_start_date")) > 30:
        reasons.append("LATE_FIRST_TREATMENT")
    if signals.get("document_claim_mismatch"):
        reasons.append("DOCUMENT_CLAIM_MISMATCH")
    if signals.get("abnormal_document_dates"):
        reasons.append("DOCUMENT_CLAIM_MISMATCH")
    if signals.get("high_noncovered_ratio"):
        reasons.append("HUMAN_REVIEW_REQUIRED")
    return reasons


def _days_between(start: str | None, end: str | None) -> int:
    if not start or not end:
        return 0
    return (date.fromisoformat(end) - date.fromisoformat(start)).days
