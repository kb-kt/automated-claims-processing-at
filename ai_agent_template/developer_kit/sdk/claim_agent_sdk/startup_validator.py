from __future__ import annotations

from pathlib import Path
from typing import Any

from .contract_validator import TemplateContractValidator
from .errors import StartupValidationError
from .model_provider import HostedLLMProvider, load_model_provider_from_config
from .plugin_loader import PluginLoader
from .specialist_plugin_loader import SpecialistPluginLoader
from .template_loader import TemplateBundle
from .tool_registry import ToolRegistry


def validate_startup_configuration(
    *,
    template_root: str | Path,
    plugin_config_path: str | Path | None,
    specialist_config_path: str | Path | None,
    model_config_path: str | Path | None,
    retrieval_enabled: bool,
    retrieval_mode: str,
    retrieval_top_k: int,
    max_document_bytes: int,
    fail_closed: bool = True,
) -> dict[str, Any]:
    errors: list[str] = []
    try:
        template = TemplateBundle.load(template_root)
        contract_status = TemplateContractValidator(template).validate()
    except Exception as exc:
        raise StartupValidationError("STARTUP_VALIDATION_FAILED", [str(exc)]) from exc

    if not fail_closed:
        errors.append("workflow.fail_closed must be true")
    if retrieval_enabled and retrieval_mode not in {"keyword", "hybrid", "vector"}:
        errors.append("retrieval.mode must be keyword, hybrid, or vector")
    if retrieval_top_k < 1 or retrieval_top_k > 100:
        errors.append("retrieval.top_k must be between 1 and 100")
    if max_document_bytes <= 0:
        errors.append("max_document_bytes must be positive")

    plugin_names: list[str] = []
    if plugin_config_path is None or not Path(plugin_config_path).exists():
        errors.append(f"plugin config not found: {plugin_config_path}")
    else:
        try:
            registry = ToolRegistry(template)
            for plugin in PluginLoader(template).load_plugins(plugin_config_path):
                registry.register(plugin)
            registry.validate_registered_plugins()
            plugin_names = sorted(registry._plugins)
        except Exception as exc:
            errors.append(f"plugin configuration invalid: {exc}")

    provider_name = "unknown"
    if model_config_path is None or not Path(model_config_path).exists():
        errors.append(f"model config not found: {model_config_path}")
    else:
        try:
            provider = load_model_provider_from_config(model_config_path)
            provider_name = getattr(provider, "provider_name", "unknown")
            if isinstance(provider, HostedLLMProvider):
                if not provider.base_url.startswith(("http://", "https://")):
                    errors.append("active hosted model provider requires an HTTP(S) base_url")
                if not provider.model_id:
                    errors.append("active hosted model provider requires model_id")
                if not provider.api_key:
                    errors.append("active hosted model provider requires api_key or environment resolution")
                if provider.timeout_ms <= 0:
                    errors.append("active hosted model provider timeout_ms must be positive")
        except Exception as exc:
            errors.append(f"model configuration invalid: {exc}")

    specialist_names: list[str] = []
    if specialist_config_path is None or not Path(specialist_config_path).exists():
        errors.append(f"specialist plugin config not found: {specialist_config_path}")
    else:
        try:
            provider = load_model_provider_from_config(model_config_path)  # type: ignore[arg-type]
            specialists = SpecialistPluginLoader().load_plugins(
                specialist_config_path,
                model_provider=provider,
            )
            specialist_names = sorted(getattr(item, "name", "unknown") for item in specialists)
            if not specialist_names:
                errors.append("at least one specialist agent must be configured")
        except Exception as exc:
            errors.append(f"specialist configuration invalid: {exc}")

    if errors:
        raise StartupValidationError("STARTUP_VALIDATION_FAILED", errors)
    return {
        "status": "ready",
        "contracts": contract_status,
        "registered_tools": plugin_names,
        "specialist_agents": specialist_names,
        "model_provider": provider_name,
        "fail_closed": True,
    }
