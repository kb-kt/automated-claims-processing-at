from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover - exercised when FastAPI is installed.
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from ai_agent_template.developer_kit.claims_gateway import (
    DocumentUploadError,
    DocumentUploadService,
    read_limited_request_body,
)
from ai_agent_template.developer_kit.claims_gateway.fastapi_errors import api_error_from_exception
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import NotFoundApiError
from ..core.review_service import ReviewService
from ..core.settings import Settings

router = APIRouter(prefix="/claims", tags=["claims"]) if APIRouter else None


if router:

    @router.post("")
    def create_claim(payload: dict[str, Any], request: Request) -> dict[str, Any]:
        return _review_service(request).submit_claim(payload)

    @router.get("")
    def list_claims(request: Request, limit: int = 50) -> dict[str, Any]:
        return _review_service(request).list_claims(limit=limit)

    @router.get("/{claim_id}")
    def get_claim(claim_id: str, request: Request) -> dict[str, Any]:
        service = _review_service(request)
        claim = service.repository.get_claim(claim_id)
        if not claim:
            raise NotFoundApiError(f"Claim not found: {claim_id}")
        return claim

    @router.post("/{claim_id}/documents", status_code=201)
    async def upload_claim_document(
        claim_id: str,
        document_type: str,
        request: Request,
    ) -> dict[str, Any]:
        settings = getattr(request.app.state, "settings", None) or Settings.load()
        review_service = _review_service(request)
        upload_service = DocumentUploadService(
            repository=review_service.repository,
            documents_root=settings.uploaded_documents_dir,
            max_document_bytes=settings.max_document_bytes,
        )
        try:
            content = await read_limited_request_body(request, settings.max_document_bytes)
            principal = getattr(request.state, "auth_principal", None)
            document = upload_service.upload_pdf(
                claim_id=claim_id,
                document_type=document_type,
                content=content,
                mime_type=request.headers.get("content-type", ""),
                actor_id=getattr(principal, "subject", None),
            )
            return {"status": "uploaded", "document": document}
        except DocumentUploadError as exc:
            raise api_error_from_exception(exc) from exc


def _review_service(request: Request) -> ReviewService:
    settings = getattr(request.app.state, "settings", None) or Settings.load()
    return ReviewService(settings=settings)
