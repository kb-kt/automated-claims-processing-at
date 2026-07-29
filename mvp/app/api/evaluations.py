from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from mvp.app.core.errors import MvpError
from mvp.app.core.evaluation_service import EvaluationService

from .errors import raise_http_error


router = APIRouter(prefix="/evaluations", tags=["evaluations"]) if APIRouter else None


if router is not None:

    @router.post("/runs")
    def create_evaluation_run(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        try:
            return _service(request).run_evaluation(payload)
        except MvpError as exc:
            raise_http_error(exc)

    @router.get("/runs/{run_id}")
    def get_evaluation_run(run_id: str, request: Request) -> dict[str, Any]:
        try:
            return _service(request).get_evaluation_run(run_id)
        except MvpError as exc:
            raise_http_error(exc)


def _service(request: Request) -> EvaluationService:
    container = request.app.state.container
    return EvaluationService(
        repository=container.repository,
        runtime=container.runtime,
        settings=container.settings,
    )
