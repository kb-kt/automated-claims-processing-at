from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


@lru_cache(maxsize=4)
def load_product(product_path: str | None = None) -> dict[str, Any]:
    if product_path:
        path = Path(product_path)
        if path.exists():
            return _read_json(path)
    for candidate in _product_candidates():
        if candidate.exists():
            return _read_json(candidate)
    return _fallback_product()


def find_coverage(product: dict[str, Any], coverage_code: str) -> dict[str, Any]:
    for coverage in product.get("coverages", []):
        if coverage.get("coverage_code") == coverage_code:
            return coverage
    raise KeyError(f"Unknown coverage code: {coverage_code}")


def resolve_coverage(product: dict[str, Any], claim: dict[str, Any]) -> dict[str, Any]:
    care_setting = claim.get("care_setting")
    benefit_category = claim.get("benefit_category")
    treatment_code = claim.get("treatment_code", "")
    if benefit_category == "special_noncovered":
        if treatment_code.startswith("TRT-MANUAL"):
            return find_coverage(product, "COV_SPECIAL_MANUAL_THERAPY")
        if treatment_code.startswith("TRT-INJECTION"):
            return find_coverage(product, "COV_SPECIAL_INJECTION")
        if treatment_code.startswith("TRT-MRI"):
            return find_coverage(product, "COV_SPECIAL_MRI_MRA")
        return find_coverage(product, "COV_SPECIAL_MANUAL_THERAPY")
    if care_setting == "pharmacy":
        return find_coverage(product, "COV_PRESCRIPTION")
    if care_setting == "outpatient" and benefit_category == "covered":
        return find_coverage(product, "COV_OUTPATIENT_COVERED")
    if care_setting == "outpatient" and benefit_category == "noncovered":
        return find_coverage(product, "COV_OUTPATIENT_NONCOVERED")
    if care_setting == "inpatient" and benefit_category == "covered":
        return find_coverage(product, "COV_INPATIENT_COVERED")
    if care_setting == "inpatient" and benefit_category == "noncovered":
        return find_coverage(product, "COV_INPATIENT_NONCOVERED")
    raise ValueError(f"Unsupported coverage mapping: {care_setting}/{benefit_category}")


def calculate_payable(coverage: dict[str, Any], claimed_amount: int) -> dict[str, Any]:
    limit = coverage.get("limit_per_claim") or coverage.get("annual_limit") or claimed_amount
    eligible_amount = min(int(claimed_amount), int(limit))
    limit_applied = eligible_amount < int(claimed_amount)
    deductible_rule = coverage.get("deductible", {})
    deductible_type = deductible_rule.get("type", "rate")
    if deductible_type == "max_of_fixed_and_rate":
        fixed = int(deductible_rule.get("fixed_amount") or 0)
        rate_amount = round(eligible_amount * float(deductible_rule.get("rate", 0)))
        deductible_amount = max(fixed, rate_amount)
    elif deductible_type == "rate":
        deductible_amount = round(eligible_amount * float(deductible_rule.get("rate", 0)))
    else:
        raise ValueError(f"Unsupported deductible type: {deductible_type}")
    return {
        "claimed_amount": int(claimed_amount),
        "eligible_amount": eligible_amount,
        "limit_applied": limit_applied,
        "deductible_amount": deductible_amount,
        "payable_amount": max(0, eligible_amount - deductible_amount),
    }


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _product_candidates() -> list[Path]:
    workspace = Path(__file__).resolve().parents[4]
    return [
        workspace / "data_generator" / "generated" / "products.json",
        workspace / "data_generator" / "samples" / "products.json",
    ]


def _fallback_product() -> dict[str, Any]:
    return {
        "product_id": "SYN-MED-001",
        "product_name": "Synthetic Medical Guard 4",
        "coverages": [
            _coverage("COV_OUTPATIENT_COVERED", "Covered outpatient", "outpatient", "covered", 200000, 10000, 0.2),
            _coverage(
                "COV_OUTPATIENT_NONCOVERED",
                "Noncovered outpatient",
                "outpatient",
                "noncovered",
                200000,
                30000,
                0.3,
            ),
            _coverage("COV_PRESCRIPTION", "Prescription", "pharmacy", "covered", 100000, 8000, 0.2),
            _coverage("COV_INPATIENT_COVERED", "Covered inpatient", "inpatient", "covered", None, 0, 0.2),
            _coverage("COV_INPATIENT_NONCOVERED", "Noncovered inpatient", "inpatient", "noncovered", None, 0, 0.3),
        ],
    }


def _coverage(
    code: str,
    name: str,
    care_setting: str,
    benefit_category: str,
    limit_per_claim: int | None,
    fixed_amount: int,
    rate: float,
) -> dict[str, Any]:
    return {
        "coverage_code": code,
        "name": name,
        "care_setting": care_setting,
        "benefit_category": benefit_category,
        "limit_per_claim": limit_per_claim,
        "annual_limit": 50000000,
        "deductible": {
            "type": "max_of_fixed_and_rate" if fixed_amount else "rate",
            "fixed_amount": fixed_amount,
            "rate": rate,
        },
        "required_documents": ["claim_form", "medical_receipt", "medical_statement"],
    }

