from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .errors import PluginError
from .schema_validator import SchemaValidator
from .template_loader import TemplateBundle


@dataclass(frozen=True)
class ToolCallResult:
    tool_name: str
    status: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None
    duration_ms: int
    metadata: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


class ToolRegistry:
    def __init__(self, template: TemplateBundle):
        self.template = template
        self.contracts = template.tool_contracts()
        self.validator = SchemaValidator(template)
        self._plugins: dict[str, Any] = {}

    def register(self, plugin: Any) -> None:
        name = getattr(plugin, "name", None)
        if not name:
            raise PluginError("PLUGIN_LOAD_ERROR: plugin.name is required")
        if name not in self.contracts:
            raise PluginError(f"PLUGIN_CONTRACT_MISMATCH: unknown tool {name}")
        contract = self.contracts[name]
        if getattr(plugin, "contract_name", name) != name:
            raise PluginError(f"PLUGIN_CONTRACT_MISMATCH: {name} contract_name mismatch")
        if getattr(plugin, "contract_version", contract["version"]) != contract["version"]:
            raise PluginError(f"PLUGIN_CONTRACT_MISMATCH: {name} version mismatch")
        self._plugins[name] = plugin

    def validate_registered_plugins(self, require_all: bool = True) -> None:
        if require_all:
            missing = sorted(set(self.contracts) - set(self._plugins))
            if missing:
                raise PluginError(f"Missing required tool plugins: {', '.join(missing)}")

    def get(self, tool_name: str) -> Any:
        try:
            return self._plugins[tool_name]
        except KeyError as exc:
            raise PluginError(f"Plugin not registered: {tool_name}") from exc

    def run(
        self,
        tool_name: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        context = context or {}
        contract = self.contracts[tool_name]
        plugin = self.get(tool_name)
        start = time.perf_counter()
        try:
            self.validator.validate_tool_input(tool_name, payload)
            envelope = plugin.run(payload, context)
            duration_ms = int((time.perf_counter() - start) * 1000)
            result = _normalize_envelope(tool_name, envelope, duration_ms, contract["version"])
            if result.status == "success":
                self.validator.validate_tool_output(tool_name, result.result or {})
            return result
        except Exception as exc:  # Plugin boundary: convert to standard failure envelope.
            duration_ms = int((time.perf_counter() - start) * 1000)
            return ToolCallResult(
                tool_name=tool_name,
                status="failed",
                result=None,
                error={
                    "error_code": f"{tool_name.upper()}_ERROR",
                    "message": str(exc),
                    "retryable": False,
                },
                duration_ms=duration_ms,
                metadata={
                    "contract_version": contract["version"],
                    "failure_policy": contract["failure_policy"],
                },
            )


def _normalize_envelope(
    tool_name: str,
    envelope: dict[str, Any],
    duration_ms: int,
    contract_version: str,
) -> ToolCallResult:
    status = envelope.get("status", "success")
    return ToolCallResult(
        tool_name=envelope.get("tool_name", tool_name),
        status=status,
        result=envelope.get("result"),
        error=envelope.get("error"),
        duration_ms=int(envelope.get("duration_ms", duration_ms)),
        metadata={
            "contract_version": contract_version,
            **dict(envelope.get("metadata") or {}),
        },
    )

