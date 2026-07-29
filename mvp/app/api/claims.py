from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from mvp.app.core.claim_service import ClaimService
from mvp.app.core.errors import MvpError, NotFound

from .errors import raise_http_error


router = APIRouter(prefix="/claims", tags=["claims"]) if APIRouter else None


if router is not None:

    @router.post("")
    def submit_claim(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        service = _service(request)
        try:
            return service.submit_claim(payload)
        except MvpError as exc:
            raise_http_error(exc)

    @router.get("")
    def list_claims(request: Request, limit: int = 50) -> dict[str, Any]:
        return _service(request).list_claims(limit=limit)

    @router.get("/{claim_id}")
    def get_claim(claim_id: str, request: Request) -> dict[str, Any]:
        claim = _service(request).get_claim(claim_id)
        if claim is None:
            raise_http_error(NotFound(f"Claim not found: {claim_id}"))
        return claim


def _service(request: Request) -> ClaimService:
    container = request.app.state.container
    return ClaimService(repository=container.repository, runtime=container.runtime)
