from __future__ import annotations

from typing import Any


class ApiError(Exception):
    code = "INTERNAL_ERROR"
    status_code = 500
    retryable = False

    def __init__(
        self,
        message: str,
        details: list[Any] | None = None,
        *,
        code: str | None = None,
        status_code: int | None = None,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = list(details or [])
        if code is not None:
            self.code = code
        if status_code is not None:
            self.status_code = int(status_code)
        if retryable is not None:
            self.retryable = bool(retryable)


class ValidationApiError(ApiError):
    code = "VALIDATION_ERROR"
    status_code = 400


class NotFoundApiError(ApiError):
    code = "NOT_FOUND"
    status_code = 404


class ConflictApiError(ApiError):
    code = "CONFLICT"
    status_code = 409


class DependencyApiError(ApiError):
    code = "DEPENDENCY_UNAVAILABLE"
    status_code = 503
    retryable = True


def api_error_payload(error: ApiError, request_id: str) -> dict[str, Any]:
    return {
        "error": {
            "code": error.code,
            "message": error.message,
            "details": error.details,
            "retryable": bool(error.retryable),
            "request_id": request_id,
        }
    }
