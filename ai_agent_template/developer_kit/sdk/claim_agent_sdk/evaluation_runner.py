from __future__ import annotations

import json
from pathlib import Path
from statistics import mean
from typing import Any

from .errors import EvaluationError
from .schema_validator import SchemaValidator
from .template_loader import TemplateBundle


class EvaluationRunner:
    def __init__(self, template: TemplateBundle):
        self.template = template
        self.validator = SchemaValidator(template)

    def evaluate(self, outputs_path: str | Path, labels_path: str | Path) -> dict[str, Any]:
        outputs = {row["claim_id"]: row for row in _read_jsonl(outputs_path)}
        labels = {row["claim_id"]: row for row in _read_jsonl(labels_path)}
        if not labels:
            raise EvaluationError("EVALUATION_INPUT_ERROR: labels file is empty")

        total = len(labels)
        schema_valid = 0
        decision_matches = 0
        coverage_matches = 0
        payable_matches = 0
        payable_errors: list[int] = []
        missing_doc_matches = 0
        reason_overlaps: list[float] = []
        expected_human = 0
        hit_human = 0
        expected_fraud = 0
        hit_fraud = 0
        false_denials = 0
        false_payments = 0
        human_review_misses = 0

        failure_cases: list[dict[str, Any]] = []
        for claim_id, label in labels.items():
            output = outputs.get(claim_id)
            if not output:
                failure_cases.append({"claim_id": claim_id, "error": "missing_output"})
                continue
            try:
                self.validator.validate_agent_output(output)
                schema_valid += 1
            except Exception as exc:
                failure_cases.append({"claim_id": claim_id, "error": str(exc)})
                continue

            if output.get("recommended_decision") == label.get("expected_decision"):
                decision_matches += 1
            if output.get("coverage_code") == label.get("coverage_code"):
                coverage_matches += 1
            payable_error = abs(
                int(output.get("recommended_payable_amount", 0))
                - int(label.get("expected_payable_amount", 0))
            )
            payable_errors.append(payable_error)
            if payable_error == 0:
                payable_matches += 1
            if sorted(output.get("missing_documents", [])) == sorted(label.get("missing_documents", [])):
                missing_doc_matches += 1

            expected_reasons = set(label.get("reason_codes", []))
            actual_reasons = set(output.get("reason_codes", []))
            union = expected_reasons | actual_reasons
            reason_overlaps.append(len(expected_reasons & actual_reasons) / len(union) if union else 1.0)

            if label.get("requires_human_review"):
                expected_human += 1
                if output.get("requires_human_review"):
                    hit_human += 1
                else:
                    human_review_misses += 1
            if label.get("fraud_suspected"):
                expected_fraud += 1
                if output.get("fraud_suspected"):
                    hit_fraud += 1

            if label.get("expected_payable_amount", 0) > 0 and output.get("recommended_decision") == "deny":
                false_denials += 1
            if label.get("expected_decision") in {"deny", "request_documents"} and output.get(
                "recommended_payable_amount", 0
            ) > 0:
                false_payments += 1

        metrics = {
            "schema_validity": _ratio(schema_valid, total),
            "decision_accuracy": _ratio(decision_matches, total),
            "coverage_accuracy": _ratio(coverage_matches, total),
            "payable_amount_exact_match": _ratio(payable_matches, total),
            "payable_amount_mae": mean(payable_errors) if payable_errors else 0,
            "missing_document_exact_match": _ratio(missing_doc_matches, total),
            "reason_code_overlap": mean(reason_overlaps) if reason_overlaps else 0,
            "human_review_recall": _ratio(hit_human, expected_human) if expected_human else 1.0,
            "fraud_suspected_recall": _ratio(hit_fraud, expected_fraud) if expected_fraud else 1.0,
            "false_denial_rate": _ratio(false_denials, total),
            "false_payment_rate": _ratio(false_payments, total),
            "human_review_miss_rate": _ratio(human_review_misses, total),
        }
        return {
            "dataset_size": total,
            "evaluated_outputs": len(outputs),
            "metrics": metrics,
            "failure_cases": failure_cases,
        }


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as file:
        for line in file:
            stripped = line.strip()
            if stripped:
                rows.append(json.loads(stripped))
    return rows


def _ratio(numerator: int, denominator: int) -> float:
    return numerator / denominator if denominator else 0.0

