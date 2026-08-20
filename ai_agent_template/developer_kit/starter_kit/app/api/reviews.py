from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from ..core.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"]) if APIRouter else None


if router:

    @router.post("")
    def create_review(payload: dict[str, Any]) -> dict[str, Any]:
        service = ReviewService()
        claim_payload = payload.get("claim")
        claim_id = payload.get("claim_id")
        if claim_payload:
            service.submit_claim(claim_payload)
            output = service.run_review(claim_payload=claim_payload)
        else:
            output = service.run_review(claim_id=claim_id)
        return _review_response(output)

    @router.get("/queue")
    def list_review_queue(limit: int = 50, sla_hours: int = 24) -> dict[str, Any]:
        return ReviewService().list_review_queue(limit=limit, sla_hours=sla_hours)

    @router.get("/{claim_id}")
    def get_review(claim_id: str) -> dict[str, Any]:
        output = ReviewService().get_review(claim_id)
        if not output:
            from ai_agent_template.developer_kit.sdk.claim_agent_sdk import NotFoundApiError
            raise NotFoundApiError(f"Review not found: {claim_id}")
        return {
            "claim_id": claim_id,
            "review_status": "found",
            "output": output,
            "agent_output": output,
        }

    @router.post("/{claim_id}/rerun")
    def rerun_review(claim_id: str) -> dict[str, Any]:
        return _review_response(ReviewService().run_review(claim_id=claim_id))

    @router.post("/{claim_id}/actions")
    def save_reviewer_action(claim_id: str, payload: dict[str, Any], request: Request) -> dict[str, Any]:
        principal = getattr(request.state, "auth_principal", None)
        if principal is not None:
            payload = {**payload, "reviewer_id": principal.subject}
        return ReviewService().save_reviewer_action(claim_id, payload)

    @router.get("/{claim_id}/actions")
    def list_reviewer_actions(claim_id: str) -> dict[str, Any]:
        return ReviewService().list_reviewer_actions(claim_id)

    @router.get("/{claim_id}/specialist-reports")
    def list_specialist_agent_reports(claim_id: str) -> dict[str, Any]:
        return ReviewService().list_specialist_agent_reports(claim_id)

    @router.get("/{claim_id}/audit-logs")
    def list_claim_audit_logs(claim_id: str, limit: int = 100) -> dict[str, Any]:
        return ReviewService().list_audit_logs(claim_id=claim_id, limit=limit)


def _review_response(output: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim_id": output["claim_id"],
        "review_status": "human_review_required" if output["requires_human_review"] else "completed",
        "status": "human_review_required" if output["requires_human_review"] else "completed",
        "output": output,
        "agent_output": output,
        "errors": [],
    }
