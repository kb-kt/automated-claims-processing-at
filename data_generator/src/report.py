from __future__ import annotations

from collections import Counter
from pathlib import Path

from .schemas import GenerationConfig, Product, ValidationResult


def build_report(
    *,
    config: GenerationConfig,
    product: Product,
    output_dir: Path,
    dev_claims: list[dict],
    eval_claims: list[dict],
    dev_labels: list[dict],
    eval_labels: list[dict],
    validation: ValidationResult,
    config_path: Path,
) -> dict:
    claims = dev_claims + eval_claims
    labels = dev_labels + eval_labels
    return {
        "generated_at": "deterministic-2026-01-01T00:00:00Z",
        "seed": config.seed,
        "config_path": str(config_path),
        "product_id": product.product_id,
        "output_dir": str(output_dir),
        "counts": {
            "dev_claims": len(dev_claims),
            "eval_claims": len(eval_claims),
            "total_claims": len(claims),
            "dev_labels": len(dev_labels),
            "eval_labels": len(eval_labels),
            "total_labels": len(labels),
        },
        "decision_distribution_actual": _counter_ratio(
            label["expected_decision"] for label in labels
        ),
        "scenario_distribution_actual": _counter_ratio(
            claim["scenario_type"] for claim in claims
        ),
        "coverage_distribution_actual": _counter_ratio(
            label["coverage_code"] for label in labels
        ),
        "validation_summary": validation.to_summary(),
    }


def _counter_ratio(values) -> dict:
    counter = Counter(values)
    total = sum(counter.values())
    return {
        key: {"count": count, "ratio": round(count / total, 6) if total else 0}
        for key, count in sorted(counter.items())
    }
