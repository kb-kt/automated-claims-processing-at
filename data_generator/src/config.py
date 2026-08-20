from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .constants import (
    BASE_DIR,
    DEFAULT_CLAIM_TYPE_DISTRIBUTION,
    DEFAULT_DECISION_DISTRIBUTION,
)
from .schemas import GenerationConfig


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def resolve_path(path_value: str | Path | None, default: Path) -> Path:
    if path_value is None:
        return default
    path = Path(path_value)
    if path.is_absolute():
        return path
    return (Path.cwd() / path).resolve()


def ensure_under_base(path: Path, label: str) -> Path:
    resolved = path.resolve()
    try:
        resolved.relative_to(BASE_DIR)
    except ValueError as exc:
        raise ValueError(f"{label} must be under {BASE_DIR}: {resolved}") from exc
    return resolved


def _validate_distribution(name: str, distribution: dict[str, float]) -> None:
    if not distribution:
        raise ValueError(f"{name} must not be empty")
    for key, value in distribution.items():
        if value < 0:
            raise ValueError(f"{name}.{key} must be >= 0")
    total = sum(distribution.values())
    if not 0.999 <= total <= 1.001:
        raise ValueError(f"{name} must sum to 1.0, got {total:.6f}")


def load_config(
    path: Path,
    *,
    dev_count: int | None = None,
    eval_count: int | None = None,
    seed: int | None = None,
) -> GenerationConfig:
    data = read_json(path)
    default_counts = data.get("default_output_counts", {})
    resolved_dev_count = dev_count
    if resolved_dev_count is None:
        resolved_dev_count = data.get("dev_count", default_counts.get("dev", 1000))
    resolved_eval_count = eval_count
    if resolved_eval_count is None:
        resolved_eval_count = data.get("eval_count", default_counts.get("eval", 200))
    if resolved_dev_count < 0 or resolved_eval_count < 0:
        raise ValueError("dev_count and eval_count must be >= 0")

    decision_distribution = dict(
        data.get("decision_distribution", DEFAULT_DECISION_DISTRIBUTION)
    )
    claim_type_distribution = dict(
        data.get("claim_type_distribution", DEFAULT_CLAIM_TYPE_DISTRIBUTION)
    )
    _validate_distribution("decision_distribution", decision_distribution)
    _validate_distribution("claim_type_distribution", claim_type_distribution)

    return GenerationConfig(
        seed=int(seed if seed is not None else data.get("seed", 20260616)),
        product_id=str(data.get("product_id", "SYN-MED-001")),
        dev_count=int(resolved_dev_count),
        eval_count=int(resolved_eval_count),
        decision_distribution=decision_distribution,
        claim_type_distribution=claim_type_distribution,
        amount_ranges=dict(data.get("amount_ranges", {})),
        split_policy=dict(data.get("split_policy", {})),
        fraud_generation=dict(data.get("fraud_generation", _default_fraud_generation())),
        medical_generation=dict(data.get("medical_generation", _default_medical_generation())),
        locale=str(data.get("locale", "ko-KR")),
        currency=str(data.get("currency", "KRW")),
    )


def _default_fraud_generation() -> dict[str, Any]:
    return {
        "enabled": True,
        "generate_pdfs": True,
        "scan_pdf_ratio": 0.35,
        "corrupt_document_ratio": 0.02,
        "base_date": "2026-07-01",
        "history_days": 180,
        "provider_count": 80,
        "insured_count": 400,
        "scenario_ratios": {
            "normal_clean": 0.08,
            "duplicate_receipt": 0.14,
            "document_forgery": 0.18,
            "repeat_pattern": 0.14,
            "provider_pattern": 0.14,
            "complex_fraud": 0.12,
            "hard_negative": 0.12,
            "document_failure": 0.08,
        },
    }


def _default_medical_generation() -> dict[str, Any]:
    return {
        "enabled": True,
        "base_date": "2026-07-01",
        "guarantee_scenarios": True,
        "include_policy_coverage_labels": True,
        "include_document_understanding_metadata": True,
    }
