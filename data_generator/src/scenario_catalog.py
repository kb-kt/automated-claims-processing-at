from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scenario:
    scenario_type: str
    distribution_key: str
    factory_name: str
    coverage_hint: str


SCENARIOS: tuple[Scenario, ...] = (
    Scenario(
        "normal_covered_outpatient",
        "pay",
        "normal_covered_outpatient",
        "COV_OUTPATIENT_COVERED",
    ),
    Scenario(
        "normal_covered_inpatient",
        "pay",
        "normal_covered_inpatient",
        "COV_INPATIENT_COVERED",
    ),
    Scenario("normal_prescription", "pay", "normal_prescription", "COV_PRESCRIPTION"),
    Scenario(
        "normal_noncovered_outpatient",
        "pay",
        "normal_noncovered_outpatient",
        "COV_OUTPATIENT_NONCOVERED",
    ),
    Scenario(
        "limit_exceeded_noncovered_outpatient",
        "partial_pay",
        "limit_exceeded_noncovered_outpatient",
        "COV_OUTPATIENT_NONCOVERED",
    ),
    Scenario(
        "limit_exceeded_covered_outpatient",
        "partial_pay",
        "limit_exceeded_covered_outpatient",
        "COV_OUTPATIENT_COVERED",
    ),
    Scenario(
        "prescription_limit_exceeded",
        "partial_pay",
        "prescription_limit_exceeded",
        "COV_PRESCRIPTION",
    ),
    Scenario(
        "missing_required_document",
        "request_documents",
        "missing_required_document",
        "COV_OUTPATIENT_COVERED",
    ),
    Scenario(
        "missing_inpatient_document",
        "request_documents",
        "missing_inpatient_document",
        "COV_INPATIENT_COVERED",
    ),
    Scenario(
        "missing_special_document",
        "request_documents",
        "missing_special_document",
        "COV_SPECIAL_MRI_MRA",
    ),
    Scenario("lapsed_policy", "deny", "lapsed_policy", "COV_INPATIENT_COVERED"),
    Scenario(
        "before_coverage_start",
        "deny",
        "before_coverage_start",
        "COV_OUTPATIENT_COVERED",
    ),
    Scenario(
        "cosmetic_exclusion",
        "deny",
        "cosmetic_exclusion",
        "COV_OUTPATIENT_NONCOVERED",
    ),
    Scenario(
        "intentional_injury",
        "deny",
        "intentional_injury",
        "COV_OUTPATIENT_COVERED",
    ),
    Scenario(
        "non_medical_provider",
        "deny",
        "non_medical_provider",
        "COV_OUTPATIENT_NONCOVERED",
    ),
    Scenario(
        "high_amount_noncovered_inpatient",
        "human_review",
        "high_amount_noncovered_inpatient",
        "COV_INPATIENT_NONCOVERED",
    ),
    Scenario(
        "frequent_manual_therapy",
        "human_review",
        "frequent_manual_therapy",
        "COV_SPECIAL_MANUAL_THERAPY",
    ),
    Scenario(
        "mri_document_claim_mismatch",
        "human_review",
        "mri_document_claim_mismatch",
        "COV_SPECIAL_MRI_MRA",
    ),
    Scenario(
        "repeated_same_diagnosis",
        "human_review",
        "repeated_same_diagnosis",
        "COV_OUTPATIENT_COVERED",
    ),
    Scenario(
        "high_outpatient_amount",
        "human_review",
        "high_outpatient_amount",
        "COV_OUTPATIENT_NONCOVERED",
    ),
    Scenario(
        "duplicate_receipt_suspected",
        "fraud_suspected_human_review",
        "duplicate_receipt_suspected",
        "COV_OUTPATIENT_COVERED",
    ),
    Scenario(
        "fraudulent_document_suspected",
        "fraud_suspected_human_review",
        "fraudulent_document_suspected",
        "COV_INPATIENT_COVERED",
    ),
)


def scenarios_by_distribution_key() -> dict[str, list[Scenario]]:
    grouped: dict[str, list[Scenario]] = {}
    for scenario in SCENARIOS:
        grouped.setdefault(scenario.distribution_key, []).append(scenario)
    return grouped
