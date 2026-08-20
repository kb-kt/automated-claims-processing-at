from __future__ import annotations

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
except ModuleNotFoundError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    HTMLResponse = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]

from .api import claims, configs, evaluations, internal, products, reviews
from .core.settings import Settings
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import ApiAccessControl, ApiError, validate_startup_configuration
from ai_agent_template.developer_kit.claims_gateway.fastapi_errors import (
    api_error_response,
    install_api_error_handlers,
)


def create_app(*, settings: Settings | None = None):
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install starter_kit/requirements.txt first.")
    resolved_settings = settings or Settings.load()
    startup_status = validate_startup_configuration(
        template_root=resolved_settings.template_root,
        plugin_config_path=resolved_settings.plugin_config_path,
        specialist_config_path=resolved_settings.specialist_config_path,
        model_config_path=resolved_settings.model_config_path,
        retrieval_enabled=resolved_settings.retrieval_enabled,
        retrieval_mode=resolved_settings.retrieval_mode,
        retrieval_top_k=resolved_settings.retrieval_top_k,
        max_document_bytes=resolved_settings.max_document_bytes,
        fail_closed=True,
    )
    app = FastAPI(title="Claim Review Agent Starter Kit", version="0.1.0")
    app.state.startup_validation = startup_status
    app.state.settings = resolved_settings
    access_control = ApiAccessControl(
        enabled=resolved_settings.auth_enabled,
        customer_api_key=resolved_settings.customer_api_key,
        reviewer_api_key=resolved_settings.reviewer_api_key,
        admin_api_key=resolved_settings.admin_api_key,
    )

    @app.middleware("http")
    async def enforce_access_control(request, call_next):
        decision = access_control.authorize(
            method=request.method,
            path=request.url.path,
            authorization=request.headers.get("Authorization"),
        )
        if not decision.allowed:
            return api_error_response(
                request,
                ApiError(
                    "Access denied.",
                    code=decision.code,
                    status_code=decision.status_code,
                ),
            )
        request.state.auth_principal = decision.principal
        return await call_next(request)
    install_api_error_handlers(app, logger_name="claim_agent_starter.api")
    app.include_router(claims.router)
    app.include_router(reviews.router)
    app.include_router(evaluations.router)
    app.include_router(configs.router)
    app.include_router(products.router)
    app.include_router(internal.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/ready")
    def ready() -> dict[str, object]:
        return startup_status

    @app.get("/ui/customer", response_class=HTMLResponse)
    def customer_ui() -> str:
        return _read_ui("customer_claim_screen.html")

    @app.get("/ui/reviewer", response_class=HTMLResponse)
    def reviewer_ui() -> str:
        return _read_ui("reviewer_assistant_screen.html")

    return app


def _read_ui(file_name: str) -> str:
    from pathlib import Path

    return (Path(__file__).resolve().parent / "ui" / file_name).read_text(encoding="utf-8")


app = create_app() if FastAPI is not None else None
