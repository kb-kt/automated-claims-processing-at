from __future__ import annotations

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import ApiError


class MvpError(ApiError):
    code = "MVP_ERROR"
    status_code = 500

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message, details)


class ValidationFailed(MvpError):
    code = "VALIDATION_ERROR"
    status_code = 400


class NotFound(MvpError):
    code = "NOT_FOUND"
    status_code = 404


class Conflict(MvpError):
    code = "CONFLICT"
    status_code = 409
