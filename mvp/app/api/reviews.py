from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from mvp.app.core.errors import MvpError, NotFound, ValidationFailed
from mvp.app.core.review_service import ReviewService

from .errors import raise_http_error


router = APIRouter(prefix="/reviews", tags=["reviews"]) if APIRouter else None


if router is not None:

    @router.post("")
    def run_review(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        claim_id = payload.get("claim_id")
        claim_payload = payload.get("claim")
        if not claim_id and not claim_payload:
            raise_http_error(ValidationFailed("claim_id or claim is required."))
        try:
            return _service(request).run_review(claim_id=claim_id, claim_payload=claim_payload)
        except MvpError as exc:
            raise_http_error(exc)

    @router.get("/queue")
    def list_review_queue(
        request: Request,
        limit: int = 50,
        sla_hours: int = 24,
    ) -> dict[str, Any]:
        try:
            return _service(request).list_review_queue(limit=limit, sla_hours=sla_hours)
        except MvpError as exc:
            raise_http_error(exc)

    @router.get("/{claim_id}")
    def get_review(claim_id: str, request: Request) -> dict[str, Any]:
        review = _service(request).get_review(claim_id)
        if review is None:
            raise_http_error(NotFound(f"Review not found: {claim_id}"))
        return {
            "claim_id": claim_id,
            "review_status": "found",
            "output": review,
        }

    @router.post("/{claim_id}/rerun")
    def rerun_review(claim_id: str, request: Request) -> dict[str, Any]:
        try:
            return _service(request).run_review(claim_id=claim_id)
        except MvpError as exc:
            raise_http_error(exc)

    @router.post("/{claim_id}/actions")
    def save_reviewer_action(
        claim_id: str,
        payload: dict[str, Any],
        request: Request,
    ) -> dict[str, Any]:
        try:
            return _service(request).save_reviewer_action(claim_id, payload)
        except MvpError as exc:
            raise_http_error(exc)

    @router.get("/{claim_id}/actions")
    def list_reviewer_actions(claim_id: str, request: Request) -> dict[str, Any]:
        try:
            return _service(request).list_reviewer_actions(claim_id)
        except MvpError as exc:
            raise_http_error(exc)

    @router.get("/{claim_id}/audit-logs")
    def list_claim_audit_logs(
        claim_id: str,
        request: Request,
        limit: int = 100,
    ) -> dict[str, Any]:
        try:
            return _service(request).list_audit_logs(claim_id=claim_id, limit=limit)
        except MvpError as exc:
            raise_http_error(exc)


def _service(request: Request) -> ReviewService:
    container = request.app.state.container
    return ReviewService(repository=container.repository, runtime=container.runtime)
