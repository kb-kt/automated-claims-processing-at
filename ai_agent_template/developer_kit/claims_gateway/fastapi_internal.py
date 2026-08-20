from __future__ import annotations

import hmac
import os
from collections.abc import Callable
from typing import Any

from .fraud_context import ClaimsInternalError, FraudContextService
from .fastapi_errors import api_error_from_exception, api_error_response
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import ApiError

try:
    from fastapi import APIRouter, Request, Response
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]
    Response = Any  # type: ignore[misc,assignment]
    JSONResponse = None  # type: ignore[assignment]


ServiceFactory = Callable[[Request], FraudContextService]


def create_internal_router(service_factory: ServiceFactory):
    if APIRouter is None:
        return None

    router = APIRouter(prefix="/internal/v1", tags=["internal-fraud"])

    @router.get("/fraud-context/claims/{claim_id}")
    def get_fraud_context(claim_id: str, request: Request):
        auth_error = _authorize(request)
        if auth_error is not None:
            return auth_error
        try:
            return service_factory(request).get_fraud_context(claim_id)
        except ClaimsInternalError as exc:
            return api_error_response(request, api_error_from_exception(exc))

    @router.get("/claims/{claim_id}/documents")
    def list_claim_documents(claim_id: str, request: Request):
        auth_error = _authorize(request)
        if auth_error is not None:
            return auth_error
        try:
            return {
                "schema_version": "1.0.0",
                "claim_id": claim_id,
                "documents": service_factory(request).list_documents(claim_id),
            }
        except ClaimsInternalError as exc:
            return api_error_response(request, api_error_from_exception(exc))

    @router.get("/documents/{document_id}/content")
    def get_document_content(document_id: str, request: Request):
        auth_error = _authorize(request)
        if auth_error is not None:
            return auth_error
        try:
            document = service_factory(request).get_document_content(document_id)
        except ClaimsInternalError as exc:
            return api_error_response(request, api_error_from_exception(exc))
        return Response(
            content=document.content,
            media_type=document.mime_type,
            headers={
                "Content-Length": str(document.file_size),
                "ETag": f'"{document.content_hash}"',
                "X-Content-Hash": document.content_hash,
            },
        )

    return router


def _authorize(request: Request):
    expected = os.environ.get("CLAIMS_INTERNAL_API_KEY")
    if not expected:
        return None
    authorization = request.headers.get("authorization", "")
    if not authorization:
        return api_error_response(request, ApiError("Internal API authorization is required.", code="AUTHENTICATION_REQUIRED", status_code=401))
    prefix = "Bearer "
    if not authorization.startswith(prefix):
        return api_error_response(request, ApiError("Invalid internal API authorization scheme.", code="AUTHENTICATION_REQUIRED", status_code=401))
    token = authorization[len(prefix):]
    if not hmac.compare_digest(token, expected):
        return api_error_response(request, ApiError("Invalid internal API token.", code="ACCESS_FORBIDDEN", status_code=403))
    return None

