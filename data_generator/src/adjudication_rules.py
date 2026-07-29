from __future__ import annotations

from datetime import date

from .product_loader import resolve_coverage
from .schemas import CalculationResult, Coverage, Product


def _parse_date(value: str) -> date:
    return date.fromisoformat(value)


def calculate_payable(coverage: Coverage, claim_record: dict) -> CalculationResult:
    claimed_amount = int(claim_record["claim"].get("claimed_amount", 0))
    applicable_limit = coverage.limit_per_claim or coverage.annual_limit or claimed_amount
    eligible_amount = min(claimed_amount, int(applicable_limit))
    limit_applied = eligible_amount < claimed_amount
    deductible = coverage.deductible
    if deductible.type == "max_of_fixed_and_rate":
        fixed = int(deductible.fixed_amount or 0)
        rate_amount = round(eligible_amount * deductible.rate)
        deductible_amount = max(fixed, rate_amount)
    elif deductible.type == "rate":
        deductible_amount = round(eligible_amount * deductible.rate)
    else:
        raise ValueError(f"Unsupported deductible type: {deductible.type}")
    payable_amount = max(0, eligible_amount - deductible_amount)
    return CalculationResult(
        claimed_amount=claimed_amount,
        eligible_amount=eligible_amount,
        limit_applied=limit_applied,
        deductible_amount=deductible_amount,
        payable_amount=payable_amount,
    )


def _empty_calculation(claim_record: dict) -> CalculationResult:
    return CalculationResult(
        claimed_amount=int(claim_record["claim"].get("claimed_amount", 0)),
        eligible_amount=0,
        limit_applied=False,
        deductible_amount=0,
        payable_amount=0,
    )


def _label(
    claim_record: dict,
    *,
    decision: str,
    coverage_code: str,
    reason_codes: list[str],
    explanation: str,
    calculation: CalculationResult | None = None,
    missing_documents: list[str] | None = None,
    requires_human_review: bool = False,
    fraud_suspected: bool = False,
) -> dict:
    calc = calculation or _empty_calculation(claim_record)
    return {
        "claim_id": claim_record["claim_id"],
        "expected_decision": decision,
        "expected_payable_amount": calc.payable_amount,
        "coverage_code": coverage_code,
        "missing_documents": missing_documents or [],
        "reason_codes": reason_codes,
        "requires_human_review": requires_human_review,
        "fraud_suspected": fraud_suspected,
        "calculation": calc.to_dict(),
        "expected_explanation": explanation,
    }


def _has_fraud_signal(claim_record: dict) -> bool:
    return bool(_fraud_reason_codes(claim_record))


def _fraud_reason_codes(claim_record: dict) -> list[str]:
    signals = claim_record.get("signals", {})
    claim = claim_record.get("claim", {})
    history = claim_record.get("claim_history", {})
    receipt_id = claim.get("receipt_id")
    receipt_hash = claim.get("receipt_hash")
    prior_receipt_ids = set(history.get("prior_receipt_ids", []))
    prior_receipt_hashes = set(history.get("prior_receipt_hashes", []))
    reasons: list[str] = []
    if (
        signals.get("suspected_duplicate_receipt")
        or (receipt_hash and receipt_hash in prior_receipt_hashes)
        or (receipt_id and receipt_id in prior_receipt_ids)
    ):
        reasons.append("DUPLICATE_RECEIPT_SUSPECTED")
    if signals.get("fraudulent_document"):
        reasons.append("FRAUD_SIGNAL")
    if int(history.get("same_insured_provider_claims_30d", 0)) >= 3:
        reasons.append("SAME_INSURED_PROVIDER_REPEAT_SUSPECTED")
    if int(history.get("same_provider_claims_30d", 0)) >= 50:
        reasons.append("PROVIDER_PATTERN_ANOMALY_SUSPECTED")
    return reasons


def _policy_invalid_reason(claim_record: dict) -> tuple[str, str] | None:
    policy = claim_record["policy"]
    claim = claim_record["claim"]
    if policy.get("status") != "active":
        return "LAPSED_POLICY", "청구 시점의 계약 상태가 유효하지 않아 보장대상이 아니다."

    coverage_start = _parse_date(policy["coverage_start_date"])
    coverage_end = _parse_date(policy["coverage_end_date"])
    incident_date = _parse_date(claim["incident_date"])
    treatment_start = _parse_date(claim["treatment_start_date"])
    if incident_date < coverage_start or treatment_start < coverage_start:
        return "INCIDENT_BEFORE_COVERAGE_START", "사고일 또는 진료일이 보장개시일 이전이다."
    if incident_date > coverage_end or treatment_start > coverage_end:
        return "INCIDENT_AFTER_COVERAGE_END", "사고일 또는 진료일이 보장종료일 이후이다."
    return None


def _missing_documents(coverage: Coverage, claim_record: dict) -> list[str]:
    submitted = set(claim_record.get("documents", []))
    return [doc for doc in coverage.required_documents if doc not in submitted]


def _exclusion_reason(claim_record: dict) -> tuple[str, str] | None:
    signals = claim_record.get("signals", {})
    claim = claim_record.get("claim", {})
    if signals.get("cosmetic_purpose"):
        return "COSMETIC_TREATMENT_EXCLUDED", "미용 목적 치료는 면책 사항에 해당한다."
    if signals.get("pre_existing_condition"):
        return "PRE_EXISTING_CONDITION_EXCLUDED", "기왕증 면책 기간 내 청구로 판단된다."
    if signals.get("intentional_injury"):
        return "INTENTIONAL_INJURY_EXCLUDED", "고의 사고는 면책 사항에 해당한다."
    if signals.get("non_medical_provider") or claim.get("provider_type") == "non_medical_provider":
        return "NON_MEDICAL_PROVIDER_EXCLUDED", "비의료기관에서 발생한 비용은 보장대상이 아니다."
    if signals.get("preventive_purpose"):
        return "PREVENTIVE_PURPOSE_EXCLUDED", "치료 목적이 불명확한 예방성 비용은 면책 사항이다."
    if signals.get("unsupported_treatment"):
        return "UNSUPPORTED_TREATMENT_EXCLUDED", "약관상 보장하지 않는 치료 코드로 판단된다."
    return None


def _human_review_reasons(claim_record: dict) -> list[str]:
    insured_profile = claim_record.get("insured_profile") or {}
    claimant = claim_record.get("claimant") or {}
    claim = claim_record["claim"]
    history = claim_record.get("claim_history", {})
    signals = claim_record.get("signals", {})
    reasons: list[str] = []
    claimed_amount = int(claim.get("claimed_amount", 0))
    care_setting = claim.get("care_setting")
    age_at_service = int(insured_profile.get("age_at_service", claimant.get("age", -1)))

    if care_setting == "outpatient" and claimed_amount >= 1_000_000:
        reasons.append("HIGH_OUTPATIENT_AMOUNT")
    if care_setting == "inpatient" and claimed_amount >= 10_000_000:
        reasons.append("HIGH_INPATIENT_AMOUNT")
    if age_at_service < 15 or age_at_service >= 80:
        reasons.append("AGE_BASED_REVIEW_REQUIRED")
    if int(history.get("same_diagnosis_claims_90d", 0)) >= 3:
        reasons.append("REPEATED_SAME_DIAGNOSIS")
    if int(history.get("manual_therapy_count_180d", 0)) >= 20:
        reasons.append("FREQUENT_MANUAL_THERAPY")

    incident_date = _parse_date(claim["incident_date"])
    treatment_start = _parse_date(claim["treatment_start_date"])
    if (treatment_start - incident_date).days > 30:
        reasons.append("LATE_FIRST_TREATMENT")

    if signals.get("document_claim_mismatch"):
        reasons.append("DOCUMENT_CLAIM_MISMATCH")
    if signals.get("abnormal_document_dates"):
        reasons.append("ABNORMAL_DOCUMENT_DATES")
    if signals.get("high_noncovered_ratio"):
        reasons.append("HIGH_NONCOVERED_RATIO")
    return reasons


def adjudicate(product: Product, claim_record: dict) -> dict:
    coverage = resolve_coverage(product, claim_record)
    coverage_code = coverage.coverage_code

    fraud_reason_codes = _fraud_reason_codes(claim_record)
    if fraud_reason_codes:
        return _label(
            claim_record,
            decision="human_review",
            coverage_code=coverage_code,
            reason_codes=list(dict.fromkeys(fraud_reason_codes + ["FRAUD_SIGNAL", "HUMAN_REVIEW_REQUIRED"])),
            explanation="중복 영수증 또는 허위 서류 의심 신호가 있어 자동 지급하지 않고 사람 심사 대상으로 분류한다.",
            requires_human_review=True,
            fraud_suspected=True,
        )

    policy_reason = _policy_invalid_reason(claim_record)
    if policy_reason:
        code, explanation = policy_reason
        return _label(
            claim_record,
            decision="deny",
            coverage_code=coverage_code,
            reason_codes=[code],
            explanation=explanation,
        )

    missing = _missing_documents(coverage, claim_record)
    if missing:
        return _label(
            claim_record,
            decision="request_documents",
            coverage_code=coverage_code,
            reason_codes=["MISSING_REQUIRED_DOCUMENT"],
            explanation="필수서류가 누락되어 추가서류 요청 대상이다.",
            missing_documents=missing,
        )

    exclusion_reason = _exclusion_reason(claim_record)
    if exclusion_reason:
        code, explanation = exclusion_reason
        return _label(
            claim_record,
            decision="deny",
            coverage_code=coverage_code,
            reason_codes=[code],
            explanation=explanation,
        )

    calculation = calculate_payable(coverage, claim_record)
    human_review_reasons = _human_review_reasons(claim_record)
    if human_review_reasons:
        reason_codes = human_review_reasons + [
            "HUMAN_REVIEW_REQUIRED",
            "PROVISIONAL_CALCULATION_AVAILABLE",
        ]
        return _label(
            claim_record,
            decision="human_review",
            coverage_code=coverage_code,
            reason_codes=reason_codes,
            explanation=(
                "산정상 지급예상금액은 "
                f"{calculation.payable_amount:,}원이지만, 사람 심사 조건에 해당한다."
            ),
            calculation=calculation,
            requires_human_review=True,
        )

    if calculation.limit_applied:
        return _label(
            claim_record,
            decision="partial_pay",
            coverage_code=coverage_code,
            reason_codes=[
                "COVERED_INCIDENT",
                "PER_CLAIM_LIMIT_APPLIED",
                "DEDUCTIBLE_APPLIED",
            ],
            explanation=(
                "보장대상이지만 담보 한도를 초과하여 한도 적용 후 "
                f"{calculation.payable_amount:,}원을 지급한다."
            ),
            calculation=calculation,
        )

    return _label(
        claim_record,
        decision="pay",
        coverage_code=coverage_code,
        reason_codes=["COVERED_INCIDENT", "DOCUMENTS_COMPLETE", "DEDUCTIBLE_APPLIED"],
        explanation=(
            "보장대상이며 필수서류가 모두 제출되었다. "
            f"자기부담금을 차감하여 {calculation.payable_amount:,}원을 지급한다."
        ),
        calculation=calculation,
    )
