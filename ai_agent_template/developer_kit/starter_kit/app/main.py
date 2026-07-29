from __future__ import annotations

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse
except ModuleNotFoundError:  # pragma: no cover
    FastAPI = None  # type: ignore[assignment]
    HTMLResponse = None  # type: ignore[assignment]

from .api import claims, configs, evaluations, reviews


def create_app():
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install starter_kit/requirements.txt first.")
    app = FastAPI(title="Claim Review Agent Starter Kit", version="0.1.0")
    app.include_router(claims.router)
    app.include_router(reviews.router)
    app.include_router(evaluations.router)
    app.include_router(configs.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

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

