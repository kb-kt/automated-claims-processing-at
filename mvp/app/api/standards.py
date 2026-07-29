from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import StandardsRegistry


router = APIRouter(prefix="/standards", tags=["standards"]) if APIRouter else None


if router is not None:

    @router.get("")
    def list_all_standards(request: Request) -> dict[str, Any]:
        registry = _registry(request)
        return {
            "decision_codes": registry.list_decision_codes(),
            "coverage_codes": registry.list_coverage_codes(),
            "document_codes": registry.list_document_codes(),
            "reason_codes": registry.list_reason_codes(),
        }

    @router.get("/decision-codes")
    def list_decision_codes(request: Request) -> dict[str, Any]:
        return {"codes": _registry(request).list_decision_codes()}

    @router.get("/coverage-codes")
    def list_coverage_codes(request: Request) -> dict[str, Any]:
        return {"codes": _registry(request).list_coverage_codes()}

    @router.get("/document-codes")
    def list_document_codes(request: Request) -> dict[str, Any]:
        return {"codes": _registry(request).list_document_codes()}

    @router.get("/reason-codes")
    def list_reason_codes(request: Request) -> dict[str, Any]:
        return {"codes": _registry(request).list_reason_codes()}


def _registry(request: Request) -> StandardsRegistry:
    return StandardsRegistry(request.app.state.container.runtime.template)
