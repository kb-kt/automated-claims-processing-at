from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import (
    AGENT_FORBIDDEN_KEYS,
    ALLOWED_DECISIONS,
    CLAIM_REQUIRED_FIELDS,
    LABEL_REQUIRED_FIELDS,
)
from .schemas import ValidationResult


def validate_dataset(claims: list[dict], labels: list[dict]) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    claim_ids: set[str] = set()

    for index, claim in enumerate(claims, start=1):
        missing = CLAIM_REQUIRED_FIELDS - set(claim)
        if missing:
            errors.append(f"claim row {index} missing fields: {sorted(missing)}")
        claim_id = claim.get("claim_id")
        if claim_id in claim_ids:
            errors.append(f"duplicate claim_id: {claim_id}")
        claim_ids.add(claim_id)
        forbidden = _find_forbidden_keys(claim)
        if forbidden:
            errors.append(f"claim {claim_id} contains agent-forbidden keys: {sorted(forbidden)}")
        try:
            json.dumps(claim, ensure_ascii=False)
        except TypeError as exc:
            errors.append(f"claim {claim_id} is not JSON serializable: {exc}")

    label_claim_ids: set[str] = set()
    for index, label in enumerate(labels, start=1):
        missing = LABEL_REQUIRED_FIELDS - set(label)
        if missing:
            errors.append(f"label row {index} missing fields: {sorted(missing)}")
        claim_id = label.get("claim_id")
        if claim_id in label_claim_ids:
            errors.append(f"duplicate label claim_id: {claim_id}")
        label_claim_ids.add(claim_id)
        if claim_id not in claim_ids:
            errors.append(f"label references unknown claim_id: {claim_id}")
        decision = label.get("expected_decision")
        if decision not in ALLOWED_DECISIONS:
            errors.append(f"label {claim_id} has invalid decision: {decision}")
        if int(label.get("expected_payable_amount", 0)) < 0:
            errors.append(f"label {claim_id} has negative payable amount")
        if decision == "request_documents" and not label.get("missing_documents"):
            errors.append(f"label {claim_id} requests documents but missing_documents is empty")
        if label.get("fraud_suspected") and not label.get("requires_human_review"):
            errors.append(f"label {claim_id} fraud_suspected requires human review")
        try:
            json.dumps(label, ensure_ascii=False)
        except TypeError as exc:
            errors.append(f"label {claim_id} is not JSON serializable: {exc}")

    unlabeled = claim_ids - label_claim_ids
    if unlabeled:
        errors.append(f"claims without labels: {sorted(unlabeled)[:5]}")

    return ValidationResult(errors=errors, warnings=warnings)


def validate_generated_dir(path: Path) -> ValidationResult:
    claims = _read_jsonl(path / "claims_dev.jsonl") + _read_jsonl(path / "claims_eval.jsonl")
    labels = _read_jsonl(path / "labels_dev.jsonl") + _read_jsonl(path / "labels_eval.jsonl")
    return validate_dataset(claims, labels)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                records.append(json.loads(line))
    return records


def _find_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in AGENT_FORBIDDEN_KEYS or key.startswith("expected_"):
                found.add(key)
            found.update(_find_forbidden_keys(nested))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden_keys(item))
    return found
