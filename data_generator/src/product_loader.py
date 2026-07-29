from __future__ import annotations

from pathlib import Path

from .config import read_json
from .schemas import Coverage, DeductibleRule, Product


def _parse_coverage(raw: dict) -> Coverage:
    deductible = raw.get("deductible", {})
    return Coverage(
        coverage_code=raw["coverage_code"],
        name=raw["name"],
        care_setting=raw["care_setting"],
        benefit_category=raw["benefit_category"],
        required_documents=list(raw.get("required_documents", [])),
        deductible=DeductibleRule(
            type=deductible.get("type", "rate"),
            fixed_amount=deductible.get("fixed_amount"),
            rate=float(deductible.get("rate", 0)),
        ),
        limit_per_claim=raw.get("limit_per_claim"),
        annual_limit=raw.get("annual_limit"),
        annual_count_limit=raw.get("annual_count_limit"),
    )


def load_product(path: Path) -> Product:
    raw = read_json(path)
    coverages = {
        item["coverage_code"]: _parse_coverage(item)
        for item in raw.get("coverages", [])
    }
    return Product(
        product_id=raw["product_id"],
        product_name=raw["product_name"],
        product_type=raw["product_type"],
        currency=raw.get("currency", "KRW"),
        raw=raw,
        coverages=coverages,
    )


def resolve_coverage(product: Product, claim_record: dict) -> Coverage:
    claim = claim_record["claim"]
    care_setting = claim.get("care_setting")
    benefit_category = claim.get("benefit_category")
    treatment_code = claim.get("treatment_code", "")

    if benefit_category == "special_noncovered":
        if treatment_code.startswith("TRT-MANUAL"):
            return product.coverages["COV_SPECIAL_MANUAL_THERAPY"]
        if treatment_code.startswith("TRT-INJECTION"):
            return product.coverages["COV_SPECIAL_INJECTION"]
        if treatment_code.startswith("TRT-MRI"):
            return product.coverages["COV_SPECIAL_MRI_MRA"]
        return product.coverages["COV_SPECIAL_MANUAL_THERAPY"]

    if care_setting == "pharmacy":
        return product.coverages["COV_PRESCRIPTION"]
    if care_setting == "outpatient" and benefit_category == "covered":
        return product.coverages["COV_OUTPATIENT_COVERED"]
    if care_setting == "outpatient" and benefit_category == "noncovered":
        return product.coverages["COV_OUTPATIENT_NONCOVERED"]
    if care_setting == "inpatient" and benefit_category == "covered":
        return product.coverages["COV_INPATIENT_COVERED"]
    if care_setting == "inpatient" and benefit_category == "noncovered":
        return product.coverages["COV_INPATIENT_NONCOVERED"]

    raise ValueError(
        "Unsupported coverage mapping: "
        f"care_setting={care_setting}, benefit_category={benefit_category}"
    )
