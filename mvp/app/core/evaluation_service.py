from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    EvaluationRunner,
    ReleaseGate,
    assert_no_label_leakage,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk.errors import (
    EvaluationError,
    SafetyValidationError,
)

from ..db.repository import ClaimReviewRepository
from .errors import NotFound, ValidationFailed
from .review_service import ReviewService
from .settings import Settings
from .template_runtime import TemplateRuntime


FORBIDDEN_LABEL_FIELDS = {
    "expected_decision",
    "expected_payable_amount",
    "expected_explanation",
    "recommended_decision",
    "recommended_payable_amount",
    "coverage_code",
    "coverage_name",
    "missing_documents",
    "reason_codes",
    "requires_human_review",
    "fraud_suspected",
    "confidence",
    "calculation",
    "policy_basis",
    "review_summary",
    "reviewer_notes",
}


class EvaluationService:
    def __init__(
        self,
        *,
        repository: ClaimReviewRepository,
        runtime: TemplateRuntime,
        settings: Settings,
        review_service: ReviewService | None = None,
    ):
        self.repository = repository
        self.runtime = runtime
        self.settings = settings
        self.review_service = review_service or ReviewService(
            repository=repository,
            runtime=runtime,
        )

    def run_evaluation(self, request: dict[str, Any] | None = None) -> dict[str, Any]:
        request = request or {}
        claims_path = _resolve_path(request.get("claims_path") or self.settings.claims_eval_path)
        labels_path = _resolve_path(request.get("labels_path") or self.settings.labels_eval_path)
        document_labels_path = _resolve_path(
            request.get("document_extraction_labels_path")
            or self.settings.document_extraction_labels_eval_path
        )
        if not document_labels_path.exists():
            document_labels_path = self.settings.fraud_generated_dir / "medical_document_metadata_eval.jsonl"
        code_mapping_labels_path = _resolve_path(
            request.get("code_mapping_labels_path")
            or self.settings.code_mapping_labels_eval_path
        )
        medical_labels_path = _resolve_path(
            request.get("medical_labels_path")
            or self.settings.medical_labels_eval_path
        )
        policy_coverage_labels_path = _resolve_path(
            request.get("policy_coverage_labels_path")
            or self.settings.policy_coverage_labels_eval_path
        )
        dataset_name = str(
            request.get("dataset_name")
            or request.get("dataset")
            or "synthetic-eval"
        )
        max_rows = _parse_max_rows(request.get("max_rows"))

        if not claims_path.exists():
            raise ValidationFailed(f"Claims file not found: {claims_path}")
        if not labels_path.exists():
            raise ValidationFailed(f"Labels file not found: {labels_path}")

        run_id = _run_id()
        output_dir = self.settings.reports_dir / run_id
        output_dir.mkdir(parents=True, exist_ok=True)
        outputs_path = output_dir / "agent_outputs.jsonl"
        labels_subset_path = output_dir / "labels_subset.jsonl"

        processed_claim_ids: list[str] = []
        with claims_path.open("r", encoding="utf-8") as source, outputs_path.open(
            "w",
            encoding="utf-8",
        ) as sink:
            for line in source:
                if max_rows is not None and len(processed_claim_ids) >= max_rows:
                    break
                if not line.strip():
                    continue
                claim_payload = json.loads(line)
                _assert_claim_has_no_label_fields(claim_payload)
                self.runtime.validator.validate_claim_input(claim_payload)
                processed_claim_ids.append(claim_payload["claim_id"])
                review_result = self.review_service.run_review(claim_payload=claim_payload)
                sink.write(json.dumps(review_result["output"], ensure_ascii=False) + "\n")

        if not processed_claim_ids:
            raise ValidationFailed("Evaluation claims file did not contain any claim rows.")

        _copy_matching_labels(labels_path, labels_subset_path, processed_claim_ids)
        try:
            result = EvaluationRunner(self.runtime.template).evaluate(
                outputs_path,
                labels_subset_path,
                document_labels_path=document_labels_path,
                code_mapping_labels_path=code_mapping_labels_path,
                medical_labels_path=medical_labels_path,
                policy_coverage_labels_path=policy_coverage_labels_path,
            )
        except EvaluationError as exc:
            raise ValidationFailed(str(exc)) from exc

        gate = ReleaseGate.from_file(self.runtime.template.root / "eval" / "thresholds.yaml")
        gate_result = gate.evaluate(result["metrics"])
        passed = gate_result["passed"]
        self.repository.save_evaluation_run(
            run_id=run_id,
            dataset_name=dataset_name,
            claims_path=str(claims_path),
            labels_path=str(labels_subset_path),
            output_path=str(outputs_path),
            metrics=result["metrics"],
            passed=passed,
        )
        return {
            "run_id": run_id,
            "dataset_name": dataset_name,
            "status": "completed",
            "passed": passed,
            "dataset_size": result["dataset_size"],
            "evaluated_outputs": result["evaluated_outputs"],
            "metrics": result["metrics"],
            "release_gate": gate_result,
            "failure_cases": result["failure_cases"],
            "outputs_path": str(outputs_path),
            "labels_path_redacted": True,
        }

    def get_evaluation_run(self, run_id: str) -> dict[str, Any]:
        stored = self.repository.get_evaluation_run(run_id)
        if stored is None:
            raise NotFound(f"Evaluation run not found: {run_id}")
        return _public_evaluation_run(stored)


def _assert_claim_has_no_label_fields(claim_payload: dict[str, Any]) -> None:
    try:
        assert_no_label_leakage(
            claim_payload,
            context="MVP evaluation claim",
            forbid_agent_output_fields=True,
        )
    except SafetyValidationError as exc:
        raise ValidationFailed(
            "Evaluation claims must not include answer-label or agent-output fields.",
            exc.findings,
        ) from exc


def _copy_matching_labels(source: Path, target: Path, claim_ids: list[str]) -> None:
    expected = set(claim_ids)
    written_ids: set[str] = set()
    with source.open("r", encoding="utf-8") as src, target.open("w", encoding="utf-8") as dst:
        for line in src:
            if not line.strip():
                continue
            row = json.loads(line)
            claim_id = row.get("claim_id")
            if claim_id in expected:
                dst.write(json.dumps(row, ensure_ascii=False) + "\n")
                written_ids.add(claim_id)
    missing = expected - written_ids
    if missing:
        raise ValidationFailed(
            "Labels file does not contain all evaluated claim IDs.",
            [f"missing label claim_id: {claim_id}" for claim_id in sorted(missing)],
        )


def _public_evaluation_run(stored: dict[str, Any]) -> dict[str, Any]:
    return {
        "run_id": stored["run_id"],
        "dataset_name": stored["dataset_name"],
        "status": "completed",
        "passed": stored["passed"],
        "claims_path": stored["claims_path"],
        "outputs_path": stored["output_path"],
        "metrics": stored["metrics"],
        "created_at": stored["created_at"],
        "labels_path_redacted": True,
    }


def _resolve_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _parse_max_rows(value: Any) -> int | None:
    if value in (None, ""):
        return None
    parsed = int(value)
    if parsed <= 0:
        raise ValidationFailed("max_rows must be a positive integer.")
    return parsed


def _run_id() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    return f"eval-{timestamp}-{uuid4().hex[:8]}"
