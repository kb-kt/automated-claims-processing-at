from __future__ import annotations


class MvpError(Exception):
    code = "MVP_ERROR"
    status_code = 500

    def __init__(self, message: str, details: list[str] | None = None):
        super().__init__(message)
        self.message = message
        self.details = details or []


class ValidationFailed(MvpError):
    code = "VALIDATION_ERROR"
    status_code = 400


class NotFound(MvpError):
    code = "NOT_FOUND"
    status_code = 404


class Conflict(MvpError):
    code = "CONFLICT"
    status_code = 409

