from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
except ModuleNotFoundError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    HTMLResponse = None  # type: ignore[assignment]
    JSONResponse = None  # type: ignore[assignment]

from .core.settings import Settings
from .core.template_runtime import TemplateRuntime
from .db.repository import ClaimReviewRepository
from .db.sqlite import SQLiteRepository
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import ApiAccessControl, validate_startup_configuration
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import ApiError
from ai_agent_template.developer_kit.claims_gateway.fastapi_errors import (
    api_error_response,
    install_api_error_handlers,
)


@dataclass
class AppContainer:
    settings: Settings
    repository: ClaimReviewRepository
    runtime: TemplateRuntime


def create_app(
    *,
    settings: Settings | None = None,
    repository: ClaimReviewRepository | None = None,
    runtime: TemplateRuntime | None = None,
):
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install fastapi and uvicorn first.")

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
        fail_closed=resolved_settings.fail_closed,
    )
    resolved_repository = repository or _build_repository(resolved_settings)
    resolved_runtime = runtime or TemplateRuntime.build(resolved_settings)
    container = AppContainer(
        settings=resolved_settings,
        repository=resolved_repository,
        runtime=resolved_runtime,
    )

    app = FastAPI(title="Insurance Claims Review MVP", version=resolved_settings.version)
    app.state.container = container
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

    install_api_error_handlers(app, logger_name="mvp.api")

    from .api import claims, configs, demo, evaluations, internal, products, reviews, standards

    app.include_router(claims.router)
    app.include_router(reviews.router)
    app.include_router(evaluations.router)
    app.include_router(standards.router)
    app.include_router(configs.router)
    app.include_router(demo.router)
    app.include_router(products.router)
    app.include_router(internal.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "service": resolved_settings.app_name,
            "version": resolved_settings.version,
        }

    @app.get("/ready")
    def ready() -> dict[str, object]:
        return {
            "status": "ready",
            "database": {
                "sqlite_path": str(resolved_settings.sqlite_path),
                "migrations": resolved_repository.applied_migrations(),
            },
            "template": resolved_runtime.readiness(),
            "startup_validation": startup_status,
        }

    @app.get("/ui/customer", response_class=HTMLResponse)
    def customer_ui() -> str:
        return _read_ui("customer_claim_screen.html")

    @app.get("/ui/reviewer", response_class=HTMLResponse)
    def reviewer_ui() -> str:
        return _read_ui("reviewer_assistant_screen.html")

    @app.get("/ui/demo", response_class=HTMLResponse)
    def demo_ui() -> str:
        return _read_ui("demo_scenario_builder.html")

    return app


def _build_repository(settings: Settings) -> ClaimReviewRepository:
    db_dir = settings.mvp_root / "app" / "db"
    return SQLiteRepository(
        db_path=settings.sqlite_path,
        schema_path=db_dir / "schema.sql",
        migrations_dir=db_dir / "migrations",
    )


def _read_ui(file_name: str) -> str:
    return (Path(__file__).resolve().parent / "ui" / file_name).read_text(encoding="utf-8")


app = create_app() if FastAPI is not None else None
