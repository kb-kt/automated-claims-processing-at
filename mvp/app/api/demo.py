from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from mvp.app.core.demo_scenario_service import DemoScenarioService
from mvp.app.core.errors import MvpError

from .errors import raise_http_error


router = APIRouter(prefix="/demo", tags=["demo"]) if APIRouter else None


if router is not None:

    @router.get("/scenarios")
    def list_demo_scenarios(request: Request) -> dict[str, Any]:
        try:
            return _service(request).list_scenarios()
        except MvpError as exc:
            raise_http_error(exc)

    @router.get("/scenarios/{scenario_id}")
    def get_demo_scenario(scenario_id: str, request: Request) -> dict[str, Any]:
        try:
            return _service(request).get_scenario(scenario_id)
        except MvpError as exc:
            raise_http_error(exc)


def _service(request: Request) -> DemoScenarioService:
    container = request.app.state.container
    return DemoScenarioService(
        settings=container.settings,
        runtime=container.runtime,
    )
