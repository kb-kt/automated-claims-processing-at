from __future__ import annotations

from typing import Any

try:
    from fastapi import APIRouter, Request
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]
    Request = Any  # type: ignore[misc,assignment]


router = APIRouter(prefix="/configs", tags=["configs"]) if APIRouter else None


if router is not None:

    @router.get("")
    def list_configs(request: Request) -> dict[str, Any]:
        return {
            "model": _model_config(request),
            "runtime": _runtime_config(request),
        }

    @router.get("/model")
    def get_model_config(request: Request) -> dict[str, Any]:
        return _model_config(request)

    @router.get("/runtime")
    def get_runtime_config(request: Request) -> dict[str, Any]:
        return _runtime_config(request)


def _model_config(request: Request) -> dict[str, Any]:
    container = request.app.state.container
    provider = container.runtime.model_provider
    return {
        "provider_name": getattr(provider, "provider_name", "unknown"),
        "model_id": getattr(provider, "model_id", "unknown"),
        "version": getattr(provider, "version", "unknown"),
        "config_path": str(container.settings.model_config_path),
        "secret_fields_redacted": ["api_key"],
    }


def _runtime_config(request: Request) -> dict[str, Any]:
    container = request.app.state.container
    settings = container.settings
    return {
        "app_name": settings.app_name,
        "environment": settings.environment,
        "version": settings.version,
        "template_root": str(settings.template_root),
        "sqlite_path": str(settings.sqlite_path),
        "reports_dir": str(settings.reports_dir),
        "retrieval": {
            "enabled": settings.retrieval_enabled,
            "mode": settings.retrieval_mode,
            "top_k": settings.retrieval_top_k,
            "readiness": container.runtime.policy_knowledge.readiness(),
        },
        "workflow": {
            "fail_closed": settings.fail_closed,
            "low_confidence_threshold": settings.low_confidence_threshold,
        },
    }
