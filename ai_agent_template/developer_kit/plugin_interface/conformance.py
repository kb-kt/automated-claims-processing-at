from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from ai_agent_template.developer_kit.sdk.claim_agent_sdk.template_loader import TemplateBundle

from .errors import PluginContractError


class ToolPluginConformance:
    def __init__(self, template: TemplateBundle):
        self.template = template
        self.contracts = template.tool_contracts()

    def assert_conformant(
        self,
        plugin: Any,
        *,
        sample_payload: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> None:
        name = getattr(plugin, "name", None)
        if name not in self.contracts:
            raise PluginContractError(f"Unknown tool plugin: {name}")
        contract = self.contracts[name]
        required_attrs = [
            "name",
            "version",
            "contract_name",
            "contract_version",
            "owner",
            "timeout_ms",
            "failure_policy",
        ]
        for attr in required_attrs:
            if not getattr(plugin, attr, None):
                raise PluginContractError(f"{name}: missing attribute {attr}")
        if plugin.contract_name != contract["tool_name"]:
            raise PluginContractError(f"{name}: contract_name mismatch")
        if plugin.contract_version != contract["version"]:
            raise PluginContractError(f"{name}: contract_version mismatch")
        if plugin.failure_policy != contract["failure_policy"]:
            raise PluginContractError(f"{name}: failure_policy mismatch")

        _validate_schema(sample_payload, contract["input_schema"], f"{name}.input")
        envelope = plugin.run(sample_payload, context or {})
        _validate_envelope(envelope, name)
        if envelope["status"] == "success":
            _validate_schema(envelope["result"], contract["output_schema"], f"{name}.output")


class PolicyKnowledgePluginConformance:
    def __init__(self, template: TemplateBundle):
        self.template = template

    def assert_conformant(
        self,
        plugin: Any,
        *,
        sample_request: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> None:
        name = getattr(plugin, "name", None)
        if not name:
            raise PluginContractError("PolicyKnowledgePlugin: missing attribute name")
        for attr in ["version", "owner", "retrieval_modes"]:
            if not getattr(plugin, attr, None):
                raise PluginContractError(f"{name}: missing attribute {attr}")
        if not hasattr(plugin, "retrieve"):
            raise PluginContractError(f"{name}: missing retrieve method")

        _validate_schema(sample_request, self.template.retrieval_request_schema, f"{name}.request")
        result = plugin.retrieve(sample_request, context or {})
        _validate_schema(result, self.template.retrieval_result_schema, f"{name}.result")


def _validate_schema(payload: dict[str, Any], schema: dict[str, Any], name: str) -> None:
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda error: list(error.path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.path) or "$"
        raise PluginContractError(f"{name}:{location}: {first.message}")


def _validate_envelope(envelope: dict[str, Any], expected_name: str) -> None:
    for key in ["tool_name", "plugin_version", "status", "result", "error", "duration_ms", "metadata"]:
        if key not in envelope:
            raise PluginContractError(f"{expected_name}: envelope missing {key}")
    if envelope["tool_name"] != expected_name:
        raise PluginContractError(f"{expected_name}: envelope tool_name mismatch")
    if envelope["status"] not in {"success", "failed"}:
        raise PluginContractError(f"{expected_name}: invalid status")
    if envelope["status"] == "failed" and not envelope["error"]:
        raise PluginContractError(f"{expected_name}: failed envelope requires error")
