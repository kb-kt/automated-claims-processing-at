from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    EvaluationRunner,
    ReleaseGate,
    NotFoundApiError,
    ValidationApiError,
    assert_no_label_leakage,
)

from .review_service import ReviewService


class EvaluationService:
    def __init__(self, review_service: ReviewService | None = None):
        self.review_service = review_service or ReviewService()

    def run_evaluation(
        self,
        *,
        claims_path: str | Path,
        labels_path: str | Path,
        dataset_name: str = "synthetic-eval",
        max_rows: int | None = None,
    ) -> dict[str, Any]:
        claims_path = Path(claims_path)
        labels_path = Path(labels_path)
        if not claims_path.exists() or not labels_path.exists():
            raise ValidationApiError(
                "Evaluation input file was not found.",
                [str(path) for path in (claims_path, labels_path) if not path.exists()],
            )
        run_id = f"eval-{uuid4().hex[:12]}"
        output_dir = self.review_service.settings.reports_dir / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs_path = output_dir / "agent_outputs_eval.jsonl"
        effective_labels_path = output_dir / "labels_eval_subset.jsonl"
        processed_claim_ids: list[str] = []

        with claims_path.open("r", encoding="utf-8") as source, outputs_path.open(
            "w", encoding="utf-8"
        ) as sink:
            for index, line in enumerate(source):
                if max_rows is not None and index >= max_rows:
                    break
                if not line.strip():
                    continue
                claim_payload = json.loads(line)
                assert_no_label_leakage(
                    claim_payload,
                    context="starter kit evaluation claim",
                    forbid_agent_output_fields=True,
                )
                processed_claim_ids.append(claim_payload["claim_id"])
                output = self.review_service.run_review(claim_payload=claim_payload)
                sink.write(json.dumps(output, ensure_ascii=False) + "\n")

        _copy_matching_labels(Path(labels_path), effective_labels_path, processed_claim_ids)

        generated_dir = self.review_service.settings.fraud_generated_dir
        result = EvaluationRunner(self.review_service.template).evaluate(
            outputs_path,
            effective_labels_path,
            document_labels_path=_optional(generated_dir / "document_extraction_labels_eval.jsonl"),
            code_mapping_labels_path=_optional(generated_dir / "code_mapping_labels_eval.jsonl"),
            medical_labels_path=_optional(generated_dir / "medical_labels_eval.jsonl"),
            policy_coverage_labels_path=_optional(generated_dir / "policy_coverage_labels_eval.jsonl"),
        )
        gate = ReleaseGate.from_file(self.review_service.template.root / "eval" / "thresholds.yaml")
        gate_result = gate.evaluate(result["metrics"])
        passed = gate_result["passed"]
        self.review_service.repository.save_evaluation_run(
            run_id=run_id,
            dataset_name=dataset_name,
            claims_path=str(claims_path),
            labels_path=str(effective_labels_path),
            output_path=str(outputs_path),
            metrics=result["metrics"],
            passed=passed,
        )
        return {
            "run_id": run_id,
            "dataset_name": dataset_name,
            "outputs_path": str(outputs_path),
            "passed": passed,
            "release_gate": gate_result,
            **result,
        }

    def get_evaluation_run(self, run_id: str) -> dict[str, Any]:
        stored = self.review_service.repository.get_evaluation_run(run_id)
        if stored is None:
            raise NotFoundApiError(f"Evaluation run not found: {run_id}")
        return {
            "run_id": stored["run_id"],
            "dataset_name": stored["dataset_name"],
            "passed": stored["passed"],
            "metrics": stored["metrics"],
            "created_at": stored["created_at"],
            "labels_path_redacted": True,
        }


def _copy_matching_labels(source: Path, target: Path, claim_ids: list[str]) -> None:
    expected = set(claim_ids)
    written_ids: set[str] = set()
    with source.open("r", encoding="utf-8") as src, target.open("w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("claim_id") in expected:
                dst.write(json.dumps(row, ensure_ascii=False) + "\n")
                written_ids.add(row["claim_id"])
    missing = expected - written_ids
    if missing:
        raise ValidationApiError(
            "Evaluation labels are incomplete.",
            [f"missing_claim_id={claim_id}" for claim_id in sorted(missing)],
        )


def _optional(path: Path) -> Path | None:
    return path if path.exists() else None
