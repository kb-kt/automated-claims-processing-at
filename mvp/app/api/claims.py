from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]

from mvp.app.core.claim_service import ClaimService
from mvp.app.core.errors import MvpError, NotFound
from ai_agent_template.developer_kit.claims_gateway import (
    DocumentUploadError,
    DocumentUploadService,
    read_limited_request_body,
)
from ai_agent_template.developer_kit.claims_gateway.fastapi_errors import api_error_from_exception

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

    @router.post("/{claim_id}/documents", status_code=201)
    async def upload_claim_document(
        claim_id: str,
        document_type: str,
        request: Request,
    ) -> dict[str, Any]:
        container = request.app.state.container
        service = DocumentUploadService(
            repository=container.repository,
            documents_root=container.settings.uploaded_documents_dir,
            max_document_bytes=container.settings.max_document_bytes,
        )
        try:
            content = await read_limited_request_body(request, container.settings.max_document_bytes)
            principal = getattr(request.state, "auth_principal", None)
            document = service.upload_pdf(
                claim_id=claim_id,
                document_type=document_type,
                content=content,
                mime_type=request.headers.get("content-type", ""),
                actor_id=getattr(principal, "subject", None),
            )
            return {"status": "uploaded", "document": document}
        except DocumentUploadError as exc:
            raise api_error_from_exception(exc) from exc


def _service(request: Request) -> ClaimService:
    container = request.app.state.container
    return ClaimService(repository=container.repository, runtime=container.runtime)
