from __future__ import annotations

try:
    from fastapi import APIRouter
except ModuleNotFoundError:  # pragma: no cover
    APIRouter = None  # type: ignore[assignment]

from ..core.settings import Settings

router = APIRouter(prefix="/configs", tags=["configs"]) if APIRouter else None


if router:

    @router.get("/model")
    def get_model_config() -> dict[str, str]:
        settings = Settings.load()
        return {
            "active_provider": "mock",
            "template_root": str(settings.template_root),
        }

