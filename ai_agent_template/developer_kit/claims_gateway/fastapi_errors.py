from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk.api_errors import (
    ApiError,
    ValidationApiError,
    api_error_payload,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk.errors import (
    EvaluationError,
    SafetyValidationError,
    SchemaValidationError,
)

try:
    from fastapi import Request
    from fastapi.exceptions import RequestValidationError
    from fastapi.responses import JSONResponse
except ModuleNotFoundError:  # pragma: no cover
    Request = Any  # type: ignore[misc,assignment]
    RequestValidationError = Exception  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]


_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


def install_api_error_handlers(app: Any, *, logger_name: str) -> None:
    logger = logging.getLogger(logger_name)

    @app.middleware("http")
    async def attach_request_id(request: Request, call_next):
        request_id = request_id_for(request)
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(ApiError)
    async def handle_api_error(request: Request, exc: ApiError):
        logger.warning(
            "API request failed",
            extra={
                "request_id": request_id_for(request),
                "error_code": exc.code,
                "status_code": exc.status_code,
                "retryable": exc.retryable,
                "details_count": len(exc.details),
                "path": request.url.path,
            },
        )
        return api_error_response(request, exc)

    @app.exception_handler(SchemaValidationError)
    async def handle_schema_error(request: Request, exc: SchemaValidationError):
        return await handle_api_error(
            request,
            ValidationApiError("Payload does not match the required schema.", exc.errors),
        )

    @app.exception_handler(SafetyValidationError)
    async def handle_safety_error(request: Request, exc: SafetyValidationError):
        return await handle_api_error(
            request,
            ValidationApiError("Payload contains prohibited evaluation fields.", exc.findings),
        )

    @app.exception_handler(EvaluationError)
    async def handle_evaluation_error(request: Request, exc: EvaluationError):
        return await handle_api_error(
            request,
            ValidationApiError("Evaluation request is invalid.", [str(exc)]),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_request_validation(request: Request, exc: RequestValidationError):
        details = [
            {
                "path": ".".join(str(item) for item in error.get("loc", [])),
                "reason": str(error.get("msg", "invalid value")),
            }
            for error in exc.errors()
        ]
        return await handle_api_error(
            request,
            ValidationApiError("HTTP request validation failed.", details),
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception):
        request_id = request_id_for(request)
        logger.exception(
            "Unhandled API error",
            extra={
                "request_id": request_id,
                "error_code": "INTERNAL_ERROR",
                "status_code": 500,
                "exception_type": type(exc).__name__,
                "path": request.url.path,
            },
        )
        return api_error_response(
            request,
            ApiError("An unexpected internal error occurred."),
        )


def request_id_for(request: Any) -> str:
    existing = getattr(getattr(request, "state", None), "request_id", None)
    if existing:
        return str(existing)
    supplied = str(request.headers.get("x-request-id", "")) if hasattr(request, "headers") else ""
    if supplied and _REQUEST_ID_PATTERN.fullmatch(supplied):
        return supplied
    return f"REQ-API-{uuid.uuid4().hex[:20].upper()}"


def api_error_response(request: Any, error: ApiError):
    if JSONResponse is None:  # pragma: no cover
        raise error
    request_id = request_id_for(request)
    return JSONResponse(
        status_code=error.status_code,
        content=api_error_payload(error, request_id),
        headers={"X-Request-ID": request_id},
    )


def api_error_from_exception(error: Any) -> ApiError:
    return ApiError(
        str(getattr(error, "message", "Request failed.")),
        list(getattr(error, "details", []) or []),
        code=str(getattr(error, "code", "INTERNAL_ERROR")),
        status_code=int(getattr(error, "status_code", 500)),
        retryable=bool(getattr(error, "retryable", False)),
    )
