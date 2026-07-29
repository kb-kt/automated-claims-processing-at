from __future__ import annotations

from typing import Any

from .base import SyntheticToolPlugin


class SyntheticExclusionCheckerPlugin(SyntheticToolPlugin):
    name = "exclusion_checker"
    contract_name = "exclusion_checker"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        claim = payload.get("claim", {})
        signals = payload.get("signals", {})
        reason = _exclusion_reason(claim, signals)
        if not reason:
            return self.ok({"excluded": False, "exclusion_reason_codes": [], "explanation": ""})
        code, explanation = reason
        return self.ok(
            {
                "excluded": True,
                "exclusion_reason_codes": [code],
                "explanation": explanation,
            }
        )


def _exclusion_reason(claim: dict[str, Any], signals: dict[str, Any]) -> tuple[str, str] | None:
    if signals.get("cosmetic_purpose"):
        return "COSMETIC_TREATMENT_EXCLUDED", "Cosmetic-purpose treatment is excluded."
    if signals.get("pre_existing_condition"):
        return "PRE_EXISTING_CONDITION_EXCLUDED", "Pre-existing condition exclusion applies."
    if signals.get("intentional_injury"):
        return "INTENTIONAL_INJURY_EXCLUDED", "Intentional injury exclusion applies."
    if signals.get("non_medical_provider") or claim.get("provider_type") == "non_medical_provider":
        return "NON_MEDICAL_PROVIDER_EXCLUDED", "Non-medical provider expenses are excluded."
    if signals.get("preventive_purpose"):
        return "UNSUPPORTED_TREATMENT_EXCLUDED", "Preventive or unclear treatment purpose is excluded."
    if signals.get("unsupported_treatment"):
        return "UNSUPPORTED_TREATMENT_EXCLUDED", "Unsupported treatment code is excluded."
    return None

