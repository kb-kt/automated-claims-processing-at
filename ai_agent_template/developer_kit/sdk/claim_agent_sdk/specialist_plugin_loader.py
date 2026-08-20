from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from .errors import PluginError


class SpecialistPluginLoader:
    """Load optional specialist-agent plugins from a small YAML subset."""

    def load_plugins(
        self,
        config_path: str | Path | None,
        *,
        model_provider: Any | None = None,
    ) -> list[Any]:
        if config_path is None:
            return []
        path = Path(config_path)
        if not path.exists():
            return []
        config = _parse_specialist_yaml(path)
        plugins: list[Any] = []
        for agent_name, entry in config.items():
            module_name = entry.get("module")
            class_name = entry.get("class")
            if not module_name or not class_name:
                raise PluginError(f"PLUGIN_LOAD_ERROR: {agent_name} requires module and class")
            module = importlib.import_module(module_name)
            plugin_class = getattr(module, class_name)
            try:
                plugins.append(plugin_class(model_provider=model_provider))
            except TypeError:
                plugins.append(plugin_class())
        return plugins


def _parse_specialist_yaml(path: Path) -> dict[str, dict[str, str]]:
    plugins: dict[str, dict[str, str]] = {}
    current: str | None = None
    in_agents = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0 and stripped == "specialist_agents:":
            in_agents = True
            continue
        if not in_agents:
            continue
        if indent == 2 and stripped.endswith(":"):
            current = stripped[:-1]
            plugins[current] = {}
            continue
        if current and indent >= 4 and ":" in stripped:
            key, value = stripped.split(":", 1)
            plugins[current][key.strip()] = _clean(value)
    return plugins


def _clean(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value
