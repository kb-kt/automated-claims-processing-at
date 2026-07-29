from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
except ModuleNotFoundError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    HTMLResponse = None  # type: ignore[assignment]

from .core.settings import Settings
from .core.template_runtime import TemplateRuntime
from .db.repository import ClaimReviewRepository
from .db.sqlite import SQLiteRepository


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
    resolved_repository = repository or _build_repository(resolved_settings)
    resolved_runtime = runtime or TemplateRuntime.build(resolved_settings)
    container = AppContainer(
        settings=resolved_settings,
        repository=resolved_repository,
        runtime=resolved_runtime,
    )

    app = FastAPI(title="Insurance Claims Review MVP", version=resolved_settings.version)
    app.state.container = container

    from .api import claims, configs, demo, evaluations, reviews, standards

    app.include_router(claims.router)
    app.include_router(reviews.router)
    app.include_router(evaluations.router)
    app.include_router(standards.router)
    app.include_router(configs.router)
    app.include_router(demo.router)

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
