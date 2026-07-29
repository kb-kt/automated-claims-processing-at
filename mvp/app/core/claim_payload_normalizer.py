from __future__ import annotations

import copy
from typing import Any


def normalize_claim_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Backfill privacy-minimized fields for legacy MVP demo payloads."""
    normalized = copy.deepcopy(payload)
    claim_id = str(normalized.get("claim_id") or "UNKNOWN")
    claimant = normalized.get("claimant") if isinstance(normalized.get("claimant"), dict) else {}
    claim = normalized.get("claim") if isinstance(normalized.get("claim"), dict) else {}
    history = (
        normalized.get("claim_history")
        if isinstance(normalized.get("claim_history"), dict)
        else {}
    )

    age = _int(
        (normalized.get("insured_profile") or {}).get("age_at_service")
        if isinstance(normalized.get("insured_profile"), dict)
        else None,
        _int(claimant.get("age"), 42),
    )
    sex = str(
        (
            (normalized.get("insured_profile") or {}).get("sex")
            if isinstance(normalized.get("insured_profile"), dict)
            else None
        )
        or claimant.get("gender")
        or "U"
    )
    if sex not in {"F", "M", "U"}:
        sex = "U"
    insured_id = str(
        (
            (normalized.get("insured_profile") or {}).get("insured_id")
            if isinstance(normalized.get("insured_profile"), dict)
            else None
        )
        or claimant.get("synthetic_person_id")
        or f"INS-{claim_id}"
    )

    normalized["insured_profile"] = {
        **(
            normalized.get("insured_profile")
            if isinstance(normalized.get("insured_profile"), dict)
            else {}
        ),
        "insured_id": insured_id,
        "age_at_service": age,
        "age_band": _age_band(age),
        "sex": sex,
        "policyholder_relation": (
            (normalized.get("insured_profile") or {}).get("policyholder_relation")
            if isinstance(normalized.get("insured_profile"), dict)
            else None
        )
        or "self",
    }

    if isinstance(normalized.get("claimant"), dict):
        normalized["claimant"] = {
            **normalized["claimant"],
            "synthetic_person_id": insured_id,
            "age": age,
            "gender": sex if sex in {"F", "M"} else "F",
        }

    if isinstance(normalized.get("claim"), dict):
        receipt_id = str(claim.get("receipt_id") or f"RCT-{claim_id}")
        normalized["claim"]["receipt_id"] = receipt_id
        normalized["claim"].setdefault("receipt_hash", f"RH-{receipt_id}")
        normalized["claim"].setdefault(
            "provider_id",
            _provider_id(claim_id, str(claim.get("provider_type") or "medical_institution")),
        )

    if isinstance(normalized.get("claim_history"), dict):
        receipt_hash = normalized.get("claim", {}).get("receipt_hash")
        prior_receipt_ids = list(history.get("prior_receipt_ids") or [])
        prior_receipt_hashes = list(history.get("prior_receipt_hashes") or [])
        if prior_receipt_ids and not prior_receipt_hashes:
            prior_receipt_hashes = [f"RH-{receipt_id}" for receipt_id in prior_receipt_ids]
        if history.get("prior_receipt_ids") and receipt_hash and receipt_hash not in prior_receipt_hashes:
            prior_receipt_hashes.append(receipt_hash)
        normalized["claim_history"] = {
            **history,
            "same_insured_provider_claims_30d": _int(
                history.get("same_insured_provider_claims_30d"), 0
            ),
            "same_provider_claims_30d": _int(history.get("same_provider_claims_30d"), 0),
            "prior_receipt_hashes": prior_receipt_hashes,
            "prior_receipt_ids": prior_receipt_ids,
        }

    return normalized


def _age_band(age: int) -> str:
    if age >= 80:
        return "80plus"
    if age < 10:
        return "0-9"
    return f"{age // 10}0s"


def _provider_id(claim_id: str, provider_type: str) -> str:
    prefix = {
        "medical_institution": "HOSP",
        "pharmacy": "PHARM",
        "non_medical_provider": "NONMED",
    }.get(provider_type, "PROV")
    number = sum((index + 1) * ord(char) for index, char in enumerate(claim_id)) % 25 + 1
    return f"PROV-MVP-{prefix}-{number:03d}"


def _int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default
