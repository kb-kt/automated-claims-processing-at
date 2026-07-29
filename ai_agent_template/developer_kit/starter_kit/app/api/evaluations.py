from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, HTTPException
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]

from ..core.evaluation_service import EvaluationService

router = APIRouter(prefix="/evaluations", tags=["evaluations"]) if APIRouter else None


if router:

    @router.post("/runs")
    def create_evaluation_run(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return EvaluationService().run_evaluation(
                claims_path=payload["claims_path"],
                labels_path=payload["labels_path"],
                dataset_name=payload.get("dataset_name", "synthetic-eval"),
                max_rows=payload.get("max_rows"),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

