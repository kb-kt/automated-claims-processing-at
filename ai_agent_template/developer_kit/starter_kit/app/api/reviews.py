from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, HTTPException
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]

from ..core.review_service import ReviewService

router = APIRouter(prefix="/reviews", tags=["reviews"]) if APIRouter else None


if router:

    @router.post("")
    def create_review(payload: dict[str, Any]) -> dict[str, Any]:
        service = ReviewService()
        try:
            claim_payload = payload.get("claim")
            claim_id = payload.get("claim_id")
            if claim_payload:
                service.submit_claim(claim_payload)
                output = service.run_review(claim_payload=claim_payload)
            else:
                output = service.run_review(claim_id=claim_id)
            return {
                "claim_id": output["claim_id"],
                "status": "human_review_required" if output["requires_human_review"] else "completed",
                "agent_output": output,
                "errors": [],
            }
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/{claim_id}")
    def get_review(claim_id: str) -> dict[str, Any]:
        output = ReviewService().get_review(claim_id)
        if not output:
            raise HTTPException(status_code=404, detail="Review not found")
        return output

    @router.post("/{claim_id}/rerun")
    def rerun_review(claim_id: str) -> dict[str, Any]:
        try:
            output = ReviewService().run_review(claim_id=claim_id)
            return {"claim_id": claim_id, "agent_output": output, "errors": []}
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

