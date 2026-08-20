from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .schemas import ValidationResult
from .writer import write_json, write_jsonl


CATALOG_SCHEMA_VERSION = "1.0.0"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


def recover_products_from_csv(path: Path) -> list[dict[str, Any]]:
    """Recover JSON product objects from the legacy one-column CSV export."""

    text = path.read_text(encoding="utf-8-sig")
    unescaped = text.replace('""', '"')
    decoder = json.JSONDecoder()
    products: list[dict[str, Any]] = []
    position = 0
    marker = '{"product_id"'
    while True:
        start = unescaped.find(marker, position)
        if start < 0:
            break
        try:
            product, end = decoder.raw_decode(unescaped, start)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Cannot recover product JSON at offset {start}: {exc}") from exc
        if not isinstance(product, dict):
            raise ValueError(f"Recovered product at offset {start} is not an object")
        products.append(product)
        position = end
    if not products:
        raise ValueError(f"No product JSON objects found in {path}")
    return products


def load_catalog_products(catalog_path: Path) -> list[dict[str, Any]]:
    if not catalog_path.exists():
        return []
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    entries = data.get("products", [])
    products: list[dict[str, Any]] = []
    for entry in entries:
        relative_path = entry.get("file_path")
        if not relative_path:
            raise ValueError(f"Catalog product has no file_path: {entry.get('product_id')}")
        product_path = (catalog_path.parent / relative_path).resolve()
        try:
            product_path.relative_to(catalog_path.parent.resolve())
        except ValueError as exc:
            raise ValueError(f"Product file escapes catalog directory: {relative_path}") from exc
        products.append(json.loads(product_path.read_text(encoding="utf-8")))
    return products


def write_product_catalog(products: list[dict[str, Any]], catalog_dir: Path) -> dict[str, Any]:
    validation = validate_products(products)
    if not validation.ok:
        raise ValueError("Invalid product catalog: " + "; ".join(validation.errors))
    catalog_dir.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []
    for product in sorted(products, key=lambda item: str(item["product_id"])):
        product_id = str(product["product_id"])
        file_name = f"{product_id}.json"
        write_json(catalog_dir / file_name, product)
        coverage_pairs = {
            (str(item.get("care_setting", "")), str(item.get("benefit_category", "")))
            for item in product.get("coverages", [])
        }
        medical_pairs = {
            ("outpatient", "covered"),
            ("outpatient", "noncovered"),
            ("outpatient", "special_noncovered"),
            ("inpatient", "covered"),
            ("inpatient", "noncovered"),
            ("pharmacy", "covered"),
        }
        entries.append(
            {
                "product_id": product_id,
                "product_name": product["product_name"],
                "product_type": product.get("product_type", "unknown"),
                "version": product.get("version", "unknown"),
                "currency": product.get("currency", "KRW"),
                "effective_date": product.get("effective_date"),
                "coverage_count": len(product.get("coverages", [])),
                "claim_generation_supported": bool(coverage_pairs & medical_pairs),
                "file_path": file_name,
            }
        )
    catalog = {
        "schema_version": CATALOG_SCHEMA_VERSION,
        "usage": "synthetic_development_and_evaluation_only",
        "products": entries,
    }
    write_json(catalog_dir / "product_catalog.json", catalog)
    return catalog


def build_policies(
    products: list[dict[str, Any]],
    claims: list[dict[str, Any]],
    *,
    policies_per_product: int = 3,
) -> list[dict[str, Any]]:
    if policies_per_product < 1:
        raise ValueError("policies_per_product must be at least 1")
    product_by_id = {str(item["product_id"]): item for item in products}
    policies: dict[str, dict[str, Any]] = {}
    ordered_products = sorted(products, key=lambda item: str(item["product_id"]))
    for product in ordered_products:
        product_id = str(product["product_id"])
        coverage_codes = [str(item["coverage_code"]) for item in product.get("coverages", [])]
        for policy_index in range(1, policies_per_product + 1):
            policy_id = f"POL-SYN-{product_id}-{policy_index:04d}"
            policies[policy_id] = {
                "policy_id": policy_id,
                "product_id": product_id,
                "product_name": product["product_name"],
                "status": "active" if policy_index != policies_per_product else "lapsed",
                "coverage_start_date": "2026-01-01",
                "coverage_end_date": "2026-12-31",
                "selected_coverage_codes": coverage_codes,
                "synthetic": True,
                "source": "catalog_baseline",
            }
    for claim in claims:
        policy_id = str(claim.get("policy_id", ""))
        product_id = str(claim.get("product_id", ""))
        if not policy_id or product_id not in product_by_id:
            continue
        existing = policies.get(policy_id)
        if existing and existing["product_id"] != product_id:
            raise ValueError(
                f"Policy {policy_id} maps to both {existing['product_id']} and {product_id}"
            )
        product = product_by_id[product_id]
        claim_policy = claim.get("policy", {})
        policies[policy_id] = {
            "policy_id": policy_id,
            "product_id": product_id,
            "product_name": product["product_name"],
            "status": claim_policy.get("status", "active"),
            "coverage_start_date": claim_policy.get("coverage_start_date", "2026-01-01"),
            "coverage_end_date": claim_policy.get("coverage_end_date", "2026-12-31"),
            "selected_coverage_codes": [
                str(item["coverage_code"]) for item in product.get("coverages", [])
            ],
            "synthetic": True,
            "source": "generated_claim",
        }
    return [policies[key] for key in sorted(policies)]


def write_policies(path: Path, policies: list[dict[str, Any]]) -> None:
    write_jsonl(path, policies)


def validate_products(products: list[dict[str, Any]]) -> ValidationResult:
    errors: list[str] = []
    product_ids: set[str] = set()
    for index, product in enumerate(products, start=1):
        missing = {"product_id", "product_name", "product_type", "coverages"} - set(product)
        if missing:
            errors.append(f"product row {index} missing fields: {sorted(missing)}")
            continue
        product_id = str(product["product_id"])
        if not _SAFE_ID.fullmatch(product_id):
            errors.append(f"product_id is not file-safe: {product_id}")
        if product_id in product_ids:
            errors.append(f"duplicate product_id: {product_id}")
        product_ids.add(product_id)
        coverage_codes: set[str] = set()
        for coverage in product.get("coverages", []):
            code = str(coverage.get("coverage_code", ""))
            if not code:
                errors.append(f"product {product_id} has coverage without coverage_code")
            elif code in coverage_codes:
                errors.append(f"product {product_id} has duplicate coverage_code: {code}")
            coverage_codes.add(code)
    return ValidationResult(errors=errors, warnings=[])


def validate_product_policy_relationships(
    products: list[dict[str, Any]],
    policies: list[dict[str, Any]],
    claims: list[dict[str, Any]],
) -> ValidationResult:
    errors: list[str] = []
    product_ids = {str(item.get("product_id", "")) for item in products}
    policy_to_product: dict[str, str] = {}
    product_policy_counts = {product_id: 0 for product_id in product_ids}
    for policy in policies:
        policy_id = str(policy.get("policy_id", ""))
        product_id = str(policy.get("product_id", ""))
        if not policy_id:
            errors.append("policy row missing policy_id")
            continue
        if product_id not in product_ids:
            errors.append(f"policy {policy_id} references unknown product_id: {product_id}")
        if policy_id in policy_to_product and policy_to_product[policy_id] != product_id:
            errors.append(f"policy {policy_id} has conflicting product relationships")
        policy_to_product[policy_id] = product_id
        if product_id in product_policy_counts:
            product_policy_counts[product_id] += 1
    for product_id, count in product_policy_counts.items():
        if count < 2:
            errors.append(f"product {product_id} must have at least two policies, got {count}")
    for claim in claims:
        claim_id = claim.get("claim_id")
        policy_id = str(claim.get("policy_id", ""))
        product_id = str(claim.get("product_id", ""))
        if product_id not in product_ids:
            errors.append(f"claim {claim_id} references unknown product_id: {product_id}")
        mapped_product = policy_to_product.get(policy_id)
        if mapped_product is None:
            errors.append(f"claim {claim_id} references unknown policy_id: {policy_id}")
        elif mapped_product != product_id:
            errors.append(
                f"claim {claim_id} product_id {product_id} does not match policy {policy_id} product_id {mapped_product}"
            )
    return ValidationResult(errors=errors, warnings=[])
