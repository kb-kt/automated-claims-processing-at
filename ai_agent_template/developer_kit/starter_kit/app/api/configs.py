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
        active_provider = _read_active_provider(settings.model_config_path)
        return {
            "active_provider": active_provider,
            "template_root": str(settings.template_root),
            "model_config_path": str(settings.model_config_path),
        }


def _read_active_provider(path) -> str:
    if not path or not path.exists():
        return "mock"
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("active_provider:"):
            return stripped.split(":", 1)[1].strip() or "mock"
    return "mock"
