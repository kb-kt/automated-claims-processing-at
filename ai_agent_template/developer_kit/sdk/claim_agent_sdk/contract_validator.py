from __future__ import annotations

from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError

from .errors import TemplateError
from .template_loader import TemplateBundle
from .workflow_loader import WorkflowLoader, WorkflowStep


class TemplateContractValidator:
    """Validate cross-artifact contracts owned by the AI Agent Template."""

    def __init__(self, template: TemplateBundle):
        self.template = template

    def validate(self) -> dict[str, Any]:
        errors: list[str] = []
        schemas = {
            path.name: self.template.read_json(path.relative_to(self.template.root))
            for path in sorted((self.template.root / "schemas").glob("*.schema.json"))
        }
        for name, schema in schemas.items():
            try:
                Draft202012Validator.check_schema(schema)
            except SchemaError as exc:
                errors.append(f"invalid JSON Schema {name}: {exc.message}")
            if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
                errors.append(f"{name} must declare JSON Schema Draft 2020-12")

        contracts = self.template.tool_contracts()
        workflow = WorkflowLoader(self.template).load()
        steps = [step for step in workflow.get("steps", []) if isinstance(step, WorkflowStep)]
        workflow_tools = {
            step.attributes.get("tool", "")
            for step in steps
            if step.type == "tool"
        }
        if workflow_tools != set(contracts):
            errors.append(
                "workflow/tool contract mismatch: "
                f"workflow_only={sorted(workflow_tools - set(contracts))}, "
                f"contract_only={sorted(set(contracts) - workflow_tools)}"
            )
        for step in steps:
            if step.type == "tool" and step.attributes.get("on_failure") != "human_review":
                errors.append(f"workflow step {step.id} must fail closed to human_review")
        for name, contract in contracts.items():
            if contract.get("tool_name") != name:
                errors.append(f"tool contract name mismatch: {name}")
            if contract.get("failure_policy") != "human_review":
                errors.append(f"tool contract {name} must use failure_policy=human_review")
            for schema_key in ("input_schema", "output_schema"):
                try:
                    Draft202012Validator.check_schema(contract[schema_key])
                except (KeyError, SchemaError) as exc:
                    errors.append(f"invalid {name}.{schema_key}: {exc}")

        for step in steps:
            prompt = step.attributes.get("prompt")
            if prompt and not self.template.path(prompt).exists():
                errors.append(f"workflow prompt not found: {prompt}")

        specialist_dir = self.template.root / "tools" / "specialist_contracts"
        for path in sorted(specialist_dir.glob("*.contract.json")):
            contract = self.template.read_json(path.relative_to(self.template.root))
            if contract.get("failure_policy") != "human_review":
                errors.append(f"specialist contract {path.name} must fail closed to human_review")
            for schema_key in ("input_schema", "output_schema"):
                try:
                    Draft202012Validator.check_schema(contract[schema_key])
                except (KeyError, SchemaError) as exc:
                    errors.append(f"invalid {path.name}.{schema_key}: {exc}")

        api_contract = self.template.read_json("schemas/api_surface.contract.json")
        if api_contract.get("contract_version") != "1.0.0":
            errors.append("API surface contract must declare contract_version=1.0.0")
        operations = api_contract.get("required_operations") or []
        operation_keys = {
            (str(item.get("method", "")).upper(), str(item.get("path", "")))
            for item in operations
            if isinstance(item, dict)
        }
        if len(operation_keys) != len(operations):
            errors.append("API surface contract contains duplicate or malformed operations")
        if not api_contract.get("canonical_review_response_fields"):
            errors.append("API surface contract requires canonical review response fields")

        if errors:
            raise TemplateError("TEMPLATE_CONTRACT_VALIDATION_FAILED:\n- " + "\n- ".join(errors))
        return {
            "status": "valid",
            "schema_count": len(schemas),
            "tool_contract_count": len(contracts),
            "workflow_tool_count": len(workflow_tools),
            "specialist_contract_count": len(list(specialist_dir.glob("*.contract.json"))),
            "api_operation_count": len(operation_keys),
        }
