from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    PluginLoader,
    TemplateBundle,
    ToolCallResult,
    ToolRegistry,
)


@dataclass(frozen=True)
class RecordedToolCall:
    tool_name: str
    request: dict[str, Any]
    result: ToolCallResult


class RecordingToolRegistry(ToolRegistry):
    def __init__(self, template: TemplateBundle):
        super().__init__(template)
        self.records: list[RecordedToolCall] = []

    def run(
        self,
        tool_name: str,
        payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> ToolCallResult:
        result = super().run(tool_name, payload, context)
        self.records.append(
            RecordedToolCall(
                tool_name=tool_name,
                request=payload,
                result=result,
            )
        )
        return result


def build_recording_registry(template: TemplateBundle, plugin_config_path) -> RecordingToolRegistry:
    registry = RecordingToolRegistry(template)
    for plugin in PluginLoader(template).load_plugins(plugin_config_path):
        registry.register(plugin)
    registry.validate_registered_plugins()
    return registry
