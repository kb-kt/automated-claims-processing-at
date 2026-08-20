from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]

from ..core.evaluation_service import EvaluationService

router = APIRouter(prefix="/evaluations", tags=["evaluations"]) if APIRouter else None


if router:

    @router.post("/runs")
    def create_evaluation_run(payload: dict[str, Any]) -> dict[str, Any]:
        from ai_agent_template.developer_kit.sdk.claim_agent_sdk import ValidationApiError
        if "claims_path" not in payload or "labels_path" not in payload:
            raise ValidationApiError("claims_path and labels_path are required.")
        return EvaluationService().run_evaluation(
            claims_path=payload["claims_path"],
            labels_path=payload["labels_path"],
            dataset_name=payload.get("dataset_name", "synthetic-eval"),
            max_rows=payload.get("max_rows"),
        )

    @router.get("/runs/{run_id}")
    def get_evaluation_run(run_id: str) -> dict[str, Any]:
        return EvaluationService().get_evaluation_run(run_id)
