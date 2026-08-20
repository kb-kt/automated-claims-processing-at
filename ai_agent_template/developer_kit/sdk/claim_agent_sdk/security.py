from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from typing import Any

from .errors import SecurityValidationError


_SECRET_KEYS = {"api_key", "authorization", "access_token", "refresh_token", "password", "secret"}
_DIRECT_IDENTIFIER_KEYS = {
    "insured_id",
    "synthetic_person_id",
    "resident_registration_number",
    "phone",
    "email",
}
_DIRECT_PII_KEYS = {
    "address",
    "birth_date",
    "date_of_birth",
    "full_name",
    "insured_name",
    "claimant_name",
    "patient_name",
}
_PUBLIC_PATHS = {"/health", "/ready", "/openapi.json", "/docs", "/redoc"}


@dataclass(frozen=True)
class AuthPrincipal:
    subject: str
    role: str


@dataclass(frozen=True)
class AccessDecision:
    allowed: bool
    status_code: int
    code: str
    principal: AuthPrincipal | None = None


class ApiAccessControl:
    """Environment-key RBAC baseline that never exposes or logs key values."""

    def __init__(
        self,
        *,
        enabled: bool,
        customer_api_key: str = "",
        reviewer_api_key: str = "",
        admin_api_key: str = "",
    ) -> None:
        self.enabled = enabled
        self._keys = {
            "customer": customer_api_key,
            "reviewer": reviewer_api_key,
            "admin": admin_api_key,
        }
        if enabled and not any(self._keys.values()):
            raise SecurityValidationError(
                "AUTH_CONFIGURATION_ERROR: at least one role API key is required when auth is enabled"
            )

    def authorize(self, *, method: str, path: str, authorization: str | None) -> AccessDecision:
        if not self.enabled or _is_public_path(path) or path.startswith("/internal/"):
            return AccessDecision(True, 200, "ACCESS_ALLOWED")
        principal = self._authenticate(authorization)
        if principal is None:
            return AccessDecision(False, 401, "AUTHENTICATION_REQUIRED")
        if principal.role not in _allowed_roles(method.upper(), path):
            return AccessDecision(False, 403, "ACCESS_FORBIDDEN", principal)
        return AccessDecision(True, 200, "ACCESS_ALLOWED", principal)

    def _authenticate(self, authorization: str | None) -> AuthPrincipal | None:
        if not authorization or not authorization.startswith("Bearer "):
            return None
        token = authorization[7:]
        for role, expected in self._keys.items():
            if expected and secrets.compare_digest(token, expected):
                return AuthPrincipal(subject=f"api-key:{role}", role=role)
        return None


def redact_sensitive_data(value: Any) -> Any:
    """Return a log-safe copy with secrets removed and identifiers tokenized."""

    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            normalized = str(key).lower()
            if normalized in _SECRET_KEYS:
                redacted[key] = "[REDACTED]"
            elif normalized in _DIRECT_IDENTIFIER_KEYS:
                redacted[key] = _tokenize(nested)
            elif normalized in _DIRECT_PII_KEYS:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive_data(nested)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    return value


def _tokenize(value: Any) -> str:
    if value in (None, ""):
        return "[REDACTED]"
    digest = hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:16]
    return f"tok_{digest}"


def _is_public_path(path: str) -> bool:
    return path in _PUBLIC_PATHS or path.startswith("/ui/") or path.startswith("/assets/")


def _allowed_roles(method: str, path: str) -> set[str]:
    if path == "/claims" and method == "POST":
        return {"customer", "reviewer", "admin"}
    if method == "POST" and path.startswith("/claims/") and path.endswith("/documents"):
        return {"customer", "reviewer", "admin"}
    if path.startswith("/claims") or path.startswith("/reviews"):
        return {"reviewer", "admin"}
    if path.startswith("/evaluations") or path.startswith("/demo"):
        return {"admin"}
    if path.startswith("/configs") or path.startswith("/standards"):
        return {"reviewer", "admin"}
    if method == "GET" and path.startswith("/products"):
        return {"customer", "reviewer", "admin"}
    return {"admin"}
