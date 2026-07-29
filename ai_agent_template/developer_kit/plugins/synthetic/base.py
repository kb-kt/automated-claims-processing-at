from __future__ import annotations

from typing import Any

from ai_agent_template.developer_kit.plugin_interface.tool_plugin import failure, success


class SyntheticToolPlugin:
    name = ""
    version = "1.0.0"
    contract_name = ""
    contract_version = "1.0.0"
    owner = "claim-review-template"
    timeout_ms = 3000
    failure_policy = "human_review"

    def ok(self, result: dict[str, Any]) -> dict[str, Any]:
        return success(
            self.name,
            result,
            plugin_version=self.version,
            contract_version=self.contract_version,
        )

    def fail(self, error_code: str, message: str) -> dict[str, Any]:
        return failure(
            self.name,
            error_code,
            message,
            plugin_version=self.version,
            contract_version=self.contract_version,
        )

