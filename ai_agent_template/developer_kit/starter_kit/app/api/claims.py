from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, HTTPException
except ModuleNotFoundError:  # pragma: no cover - exercised when FastAPI is installed.
    APIRouter = None  # type: ignore[assignment]
    HTTPException = Exception  # type: ignore[assignment]

from ..core.review_service import ReviewService

router = APIRouter(prefix="/claims", tags=["claims"]) if APIRouter else None


if router:

    @router.post("")
    def create_claim(payload: dict[str, Any]) -> dict[str, Any]:
        try:
            return ReviewService().submit_claim(payload)
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @router.get("/{claim_id}")
    def get_claim(claim_id: str) -> dict[str, Any]:
        service = ReviewService()
        claim = service.repository.get_claim(claim_id)
        if not claim:
            raise HTTPException(status_code=404, detail="Claim not found")
        return claim

