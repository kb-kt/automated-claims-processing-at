from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import EvaluationRunner

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
        run_id = f"eval-{uuid4().hex[:12]}"
        output_dir = self.review_service.settings.reports_dir / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs_path = output_dir / "agent_outputs_eval.jsonl"
        effective_labels_path = output_dir / "labels_eval_subset.jsonl"
        processed_claim_ids: list[str] = []

        with Path(claims_path).open("r", encoding="utf-8") as source, outputs_path.open(
            "w", encoding="utf-8"
        ) as sink:
            for index, line in enumerate(source):
                if max_rows is not None and index >= max_rows:
                    break
                if not line.strip():
                    continue
                claim_payload = json.loads(line)
                processed_claim_ids.append(claim_payload["claim_id"])
                output = self.review_service.run_review(claim_payload=claim_payload)
                sink.write(json.dumps(output, ensure_ascii=False) + "\n")

        _copy_matching_labels(Path(labels_path), effective_labels_path, processed_claim_ids)

        result = EvaluationRunner(self.review_service.template).evaluate(outputs_path, effective_labels_path)
        passed = _passes_minimum(result["metrics"])
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
            **result,
        }


def _passes_minimum(metrics: dict[str, Any]) -> bool:
    return bool(
        metrics.get("schema_validity", 0) == 1.0
        and metrics.get("coverage_accuracy", 0) >= 0.90
        and metrics.get("human_review_recall", 0) >= 0.90
    )


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
        raise ValueError(f"Missing labels for claim_ids: {sorted(missing)}")
