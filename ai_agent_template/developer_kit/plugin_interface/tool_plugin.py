from __future__ import annotations

from typing import Any, Protocol


class ToolPlugin(Protocol):
    name: str
    version: str
    contract_name: str
    contract_version: str
    owner: str
    timeout_ms: int
    failure_policy: str

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...


def success(
    tool_name: str,
    result: dict[str, Any],
    *,
    plugin_version: str,
    contract_version: str,
    duration_ms: int = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "plugin_version": plugin_version,
        "status": "success",
        "result": result,
        "error": None,
        "duration_ms": duration_ms,
        "metadata": {"contract_version": contract_version, **(metadata or {})},
    }


def failure(
    tool_name: str,
    error_code: str,
    message: str,
    *,
    plugin_version: str,
    contract_version: str,
    retryable: bool = False,
    duration_ms: int = 0,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "plugin_version": plugin_version,
        "status": "failed",
        "result": None,
        "error": {
            "error_code": error_code,
            "message": message,
            "retryable": retryable,
        },
        "duration_ms": duration_ms,
        "metadata": {"contract_version": contract_version, **(metadata or {})},
    }

