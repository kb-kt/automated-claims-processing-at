from __future__ import annotations

import random
from datetime import date, timedelta

from .scenario_catalog import Scenario, scenarios_by_distribution_key
from .schemas import GenerationConfig, Product


class ClaimGenerator:
    def __init__(self, config: GenerationConfig, product: Product) -> None:
        self.config = config
        self.product = product

    def generate(self, split: str, count: int) -> list[dict]:
        rng = random.Random(self.config.seed + (0 if split.lower() == "dev" else 10_000))
        scenarios = self._scenario_plan(count, rng)
        claims = []
        for index, scenario in enumerate(scenarios, start=1):
            factory = getattr(self, f"_make_{scenario.factory_name}")
            claims.append(factory(split.upper(), index, rng))
        return claims

    def _scenario_plan(self, count: int, rng: random.Random) -> list[Scenario]:
        grouped = scenarios_by_distribution_key()
        allocation = _allocate_counts(count, self.config.decision_distribution)
        planned: list[Scenario] = []
        for distribution_key, scenario_count in allocation.items():
            candidates = grouped.get(distribution_key)
            if not candidates:
                continue
            for offset in range(scenario_count):
                planned.append(candidates[offset % len(candidates)])
        rng.shuffle(planned)
        return planned

    def _base(
        self,
        split: str,
        index: int,
        rng: random.Random,
        *,
        scenario_type: str,
        care_setting: str,
        benefit_category: str,
        treatment_code: str,
        diagnosis_code: str,
        claimed_amount: int,
        provider_type: str = "medical_institution",
        policy_status: str = "active",
        coverage_start_date: str = "2026-01-01",
        coverage_end_date: str = "2026-12-31",
        incident_date: date | None = None,
        treatment_delay_days: int = 0,
        treatment_days: int = 0,
        documents: list[str] | None = None,
        history: dict | None = None,
        signals: dict | None = None,
        receipt_id: str | None = None,
        receipt_hash: str | None = None,
        provider_id: str | None = None,
        extra_claim: dict | None = None,
    ) -> dict:
        incident = incident_date or _random_date(rng)
        treatment_start = incident + timedelta(days=treatment_delay_days)
        treatment_end = treatment_start + timedelta(days=treatment_days)
        claim_date = treatment_end + timedelta(days=rng.randint(1, 7))
        receipt = receipt_id or f"RCT-SYN-{split}-{index:06d}"
        receipt_token = receipt_hash or f"RH-SYN-{split}-{index:06d}"
        provider_token = provider_id or _provider_id(provider_type, index)
        age = rng.randint(18, 78)
        sex = rng.choice(["F", "M"])
        insured_id = f"INS-SYN-{split}-{index:06d}"
        claim = {
            "care_setting": care_setting,
            "benefit_category": benefit_category,
            "treatment_code": treatment_code,
            "diagnosis_code": diagnosis_code,
            "incident_date": incident.isoformat(),
            "treatment_start_date": treatment_start.isoformat(),
            "treatment_end_date": treatment_end.isoformat(),
            "claim_date": claim_date.isoformat(),
            "claimed_amount": claimed_amount,
            "receipt_id": receipt,
            "receipt_hash": receipt_token,
            "provider_id": provider_token,
            "provider_type": provider_type,
        }
        if extra_claim:
            claim.update(extra_claim)
        return {
            "claim_id": f"CLM-{split}-{index:06d}",
            "policy_id": f"POL-SYN-{split}-{index:06d}",
            "product_id": self.product.product_id,
            "scenario_type": scenario_type,
            "insured_profile": {
                "insured_id": insured_id,
                "age_at_service": age,
                "age_band": _age_band(age),
                "sex": sex,
                "policyholder_relation": _policyholder_relation(index),
            },
            "claimant": {
                "synthetic_person_id": insured_id,
                "age": age,
                "gender": sex,
            },
            "policy": {
                "status": policy_status,
                "coverage_start_date": coverage_start_date,
                "coverage_end_date": coverage_end_date,
            },
            "claim": claim,
            "documents": documents or self._required_docs_for_claim(care_setting, benefit_category, treatment_code),
            "claim_history": {
                "same_diagnosis_claims_90d": 0,
                "manual_therapy_count_180d": 0,
                "same_insured_provider_claims_30d": 0,
                "same_provider_claims_30d": 0,
                "prior_receipt_hashes": [],
                "prior_receipt_ids": [],
                **(history or {}),
            },
            "signals": {
                "cosmetic_purpose": False,
                "pre_existing_condition": False,
                "intentional_injury": False,
                "non_medical_provider": False,
                "suspected_duplicate_receipt": False,
                "document_claim_mismatch": False,
                **(signals or {}),
            },
        }

    def _required_docs_for_claim(
        self, care_setting: str, benefit_category: str, treatment_code: str
    ) -> list[str]:
        if benefit_category == "special_noncovered":
            if treatment_code.startswith("TRT-MRI"):
                coverage_code = "COV_SPECIAL_MRI_MRA"
            elif treatment_code.startswith("TRT-INJECTION"):
                coverage_code = "COV_SPECIAL_INJECTION"
            else:
                coverage_code = "COV_SPECIAL_MANUAL_THERAPY"
        elif care_setting == "pharmacy":
            coverage_code = "COV_PRESCRIPTION"
        elif care_setting == "outpatient" and benefit_category == "covered":
            coverage_code = "COV_OUTPATIENT_COVERED"
        elif care_setting == "outpatient":
            coverage_code = "COV_OUTPATIENT_NONCOVERED"
        elif care_setting == "inpatient" and benefit_category == "covered":
            coverage_code = "COV_INPATIENT_COVERED"
        else:
            coverage_code = "COV_INPATIENT_NONCOVERED"
        return list(self.product.coverages[coverage_code].required_documents)

    def _amount(self, key: str, rng: random.Random) -> int:
        ranges = self.config.amount_ranges.get(key) or {"min": 10_000, "max": 500_000}
        return rng.randint(int(ranges["min"]), int(ranges["max"]))

    def _make_normal_covered_outpatient(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="normal_covered_outpatient",
            care_setting="outpatient",
            benefit_category="covered",
            treatment_code="TRT-COLD-001",
            diagnosis_code="SYN-J10",
            claimed_amount=rng.randint(30_000, 190_000),
        )

    def _make_normal_noncovered_outpatient(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="normal_noncovered_outpatient",
            care_setting="outpatient",
            benefit_category="noncovered",
            treatment_code="TRT-NONCOV-001",
            diagnosis_code="SYN-M54",
            claimed_amount=rng.randint(70_000, 190_000),
        )

    def _make_normal_covered_inpatient(self, split: str, index: int, rng: random.Random) -> dict:
        days = rng.randint(2, 8)
        return self._base(
            split,
            index,
            rng,
            scenario_type="normal_covered_inpatient",
            care_setting="inpatient",
            benefit_category="covered",
            treatment_code="TRT-INP-002",
            diagnosis_code="SYN-K35",
            claimed_amount=rng.randint(400_000, 2_500_000),
            treatment_days=days - 1,
            extra_claim={"inpatient_days": days},
        )

    def _make_normal_prescription(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="normal_prescription",
            care_setting="pharmacy",
            benefit_category="covered",
            treatment_code="TRT-RX-001",
            diagnosis_code="SYN-J06",
            claimed_amount=rng.randint(12_000, 95_000),
            provider_type="pharmacy",
        )

    def _make_limit_exceeded_noncovered_outpatient(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="limit_exceeded_noncovered_outpatient",
            care_setting="outpatient",
            benefit_category="noncovered",
            treatment_code="TRT-NONCOV-001",
            diagnosis_code="SYN-M54",
            claimed_amount=rng.randint(210_000, 700_000),
        )

    def _make_limit_exceeded_covered_outpatient(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="limit_exceeded_covered_outpatient",
            care_setting="outpatient",
            benefit_category="covered",
            treatment_code="TRT-GASTRO-001",
            diagnosis_code="SYN-K30",
            claimed_amount=rng.randint(210_000, 350_000),
        )

    def _make_prescription_limit_exceeded(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="prescription_limit_exceeded",
            care_setting="pharmacy",
            benefit_category="covered",
            treatment_code="TRT-RX-001",
            diagnosis_code="SYN-J06",
            claimed_amount=rng.randint(105_000, 150_000),
            provider_type="pharmacy",
        )

    def _make_missing_required_document(self, split: str, index: int, rng: random.Random) -> dict:
        docs = self._required_docs_for_claim("outpatient", "covered", "TRT-GASTRO-001")
        docs.remove("diagnosis_note")
        return self._base(
            split,
            index,
            rng,
            scenario_type="missing_required_document",
            care_setting="outpatient",
            benefit_category="covered",
            treatment_code="TRT-GASTRO-001",
            diagnosis_code="SYN-K30",
            claimed_amount=rng.randint(40_000, 180_000),
            documents=docs,
        )

    def _make_missing_inpatient_document(self, split: str, index: int, rng: random.Random) -> dict:
        docs = self._required_docs_for_claim("inpatient", "covered", "TRT-INP-001")
        docs.remove("diagnosis_certificate")
        return self._base(
            split,
            index,
            rng,
            scenario_type="missing_inpatient_document",
            care_setting="inpatient",
            benefit_category="covered",
            treatment_code="TRT-INP-001",
            diagnosis_code="SYN-I20",
            claimed_amount=rng.randint(500_000, 3_000_000),
            documents=docs,
            extra_claim={"inpatient_days": rng.randint(2, 10)},
        )

    def _make_missing_special_document(self, split: str, index: int, rng: random.Random) -> dict:
        docs = self._required_docs_for_claim("outpatient", "special_noncovered", "TRT-MRI-001")
        docs.remove("physician_opinion")
        return self._base(
            split,
            index,
            rng,
            scenario_type="missing_special_document",
            care_setting="outpatient",
            benefit_category="special_noncovered",
            treatment_code="TRT-MRI-001",
            diagnosis_code="SYN-M51",
            claimed_amount=rng.randint(450_000, 1_200_000),
            documents=docs,
        )

    def _make_lapsed_policy(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="lapsed_policy",
            care_setting="inpatient",
            benefit_category="covered",
            treatment_code="TRT-INP-001",
            diagnosis_code="SYN-I20",
            claimed_amount=rng.randint(800_000, 4_000_000),
            policy_status="lapsed",
            extra_claim={"inpatient_days": rng.randint(3, 12)},
        )

    def _make_before_coverage_start(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="before_coverage_start",
            care_setting="outpatient",
            benefit_category="covered",
            treatment_code="TRT-ANKLE-001",
            diagnosis_code="SYN-S93",
            claimed_amount=rng.randint(50_000, 190_000),
            coverage_start_date="2026-04-01",
            incident_date=date(2026, 3, rng.randint(1, 27)),
        )

    def _make_cosmetic_exclusion(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="cosmetic_exclusion",
            care_setting="outpatient",
            benefit_category="noncovered",
            treatment_code="TRT-COSMETIC-001",
            diagnosis_code="SYN-Z41",
            claimed_amount=rng.randint(250_000, 650_000),
            signals={"cosmetic_purpose": True},
        )

    def _make_intentional_injury(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="intentional_injury",
            care_setting="outpatient",
            benefit_category="covered",
            treatment_code="TRT-WOUND-001",
            diagnosis_code="SYN-S61",
            claimed_amount=rng.randint(80_000, 260_000),
            signals={"intentional_injury": True},
        )

    def _make_non_medical_provider(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="non_medical_provider",
            care_setting="outpatient",
            benefit_category="noncovered",
            treatment_code="TRT-NONMED-001",
            diagnosis_code="SYN-R52",
            claimed_amount=rng.randint(70_000, 300_000),
            provider_type="non_medical_provider",
            signals={"non_medical_provider": True},
        )

    def _make_high_amount_noncovered_inpatient(self, split: str, index: int, rng: random.Random) -> dict:
        days = rng.randint(12, 35)
        return self._base(
            split,
            index,
            rng,
            scenario_type="high_amount_noncovered_inpatient",
            care_setting="inpatient",
            benefit_category="noncovered",
            treatment_code="TRT-INP-NONCOV-001",
            diagnosis_code="SYN-M17",
            claimed_amount=rng.randint(10_000_000, 15_000_000),
            treatment_days=days - 1,
            extra_claim={"inpatient_days": days},
        )

    def _make_frequent_manual_therapy(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="frequent_manual_therapy",
            care_setting="outpatient",
            benefit_category="special_noncovered",
            treatment_code="TRT-MANUAL-001",
            diagnosis_code="SYN-M54",
            claimed_amount=rng.randint(90_000, 190_000),
            history={"same_diagnosis_claims_90d": 2, "manual_therapy_count_180d": rng.randint(20, 45)},
            extra_claim={"visit_count": 1},
        )

    def _make_mri_document_claim_mismatch(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="mri_document_claim_mismatch",
            care_setting="outpatient",
            benefit_category="special_noncovered",
            treatment_code="TRT-MRI-001",
            diagnosis_code="SYN-K08",
            claimed_amount=rng.randint(600_000, 1_400_000),
            treatment_delay_days=rng.randint(31, 45),
            signals={"document_claim_mismatch": True},
        )

    def _make_repeated_same_diagnosis(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="repeated_same_diagnosis",
            care_setting="outpatient",
            benefit_category="covered",
            treatment_code="TRT-COLD-001",
            diagnosis_code="SYN-J10",
            claimed_amount=rng.randint(30_000, 170_000),
            history={"same_diagnosis_claims_90d": rng.randint(3, 6)},
        )

    def _make_high_outpatient_amount(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="high_outpatient_amount",
            care_setting="outpatient",
            benefit_category="noncovered",
            treatment_code="TRT-NONCOV-002",
            diagnosis_code="SYN-M25",
            claimed_amount=rng.randint(1_000_000, 1_500_000),
        )

    def _make_duplicate_receipt_suspected(self, split: str, index: int, rng: random.Random) -> dict:
        receipt_id = f"RCT-DUP-{split}-{index:06d}"
        receipt_hash = f"RH-DUP-{split}-{index:06d}"
        return self._base(
            split,
            index,
            rng,
            scenario_type="duplicate_receipt_suspected",
            care_setting="outpatient",
            benefit_category="covered",
            treatment_code="TRT-COLD-001",
            diagnosis_code="SYN-J10",
            claimed_amount=rng.randint(50_000, 180_000),
            receipt_id=receipt_id,
            receipt_hash=receipt_hash,
            provider_id="PROV-SYN-REPEAT-001",
            history={
                "same_diagnosis_claims_90d": 1,
                "same_insured_provider_claims_30d": 1,
                "prior_receipt_hashes": [receipt_hash],
                "prior_receipt_ids": [receipt_id],
            },
            signals={"suspected_duplicate_receipt": True},
        )

    def _make_fraudulent_document_suspected(self, split: str, index: int, rng: random.Random) -> dict:
        return self._base(
            split,
            index,
            rng,
            scenario_type="fraudulent_document_suspected",
            care_setting="inpatient",
            benefit_category="covered",
            treatment_code="TRT-INP-003",
            diagnosis_code="SYN-S72",
            claimed_amount=rng.randint(1_000_000, 5_000_000),
            signals={"fraudulent_document": True},
            extra_claim={"inpatient_days": rng.randint(3, 15)},
        )


def _random_date(rng: random.Random) -> date:
    start = date(2026, 1, 5)
    return start + timedelta(days=rng.randint(0, 250))


def _age_band(age: int) -> str:
    if age >= 80:
        return "80plus"
    if age < 10:
        return "0-9"
    return f"{age // 10}0s"


def _policyholder_relation(index: int) -> str:
    relations = ["self", "spouse", "child", "parent", "other"]
    return relations[index % len(relations)]


def _provider_id(provider_type: str, index: int) -> str:
    prefix_by_type = {
        "medical_institution": "HOSP",
        "pharmacy": "PHARM",
        "non_medical_provider": "NONMED",
    }
    prefix = prefix_by_type.get(provider_type, "PROV")
    return f"PROV-SYN-{prefix}-{(index % 25) + 1:03d}"


def _allocate_counts(count: int, distribution: dict[str, float]) -> dict[str, int]:
    if count <= 0:
        return {key: 0 for key in distribution}
    raw = {key: count * value for key, value in distribution.items()}
    allocated = {key: int(value) for key, value in raw.items()}
    remaining = count - sum(allocated.values())
    remainders = sorted(
        raw.items(),
        key=lambda item: (item[1] - int(item[1]), item[0]),
        reverse=True,
    )
    for key, _ in remainders[:remaining]:
        allocated[key] += 1
    return allocated
