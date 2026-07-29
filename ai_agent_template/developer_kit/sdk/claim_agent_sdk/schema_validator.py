from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

from .errors import SchemaValidationError
from .template_loader import TemplateBundle


class SchemaValidator:
    def __init__(self, template: TemplateBundle):
        self.template = template
        self._format_checker = FormatChecker()

    def validate_claim_input(self, payload: dict[str, Any]) -> None:
        self._validate(payload, self.template.input_schema, "claim_review_input")

    def validate_agent_output(self, payload: dict[str, Any]) -> None:
        self._validate(payload, self.template.output_schema, "claim_review_output")
        errors = self._business_output_errors(payload)
        if errors:
            raise SchemaValidationError("Agent output failed business validation.", errors)

    def validate_policy_chunk(self, payload: dict[str, Any]) -> None:
        self._validate(payload, self.template.policy_chunk_schema, "policy_chunk")

    def validate_retrieval_request(self, payload: dict[str, Any]) -> None:
        self._validate(payload, self.template.retrieval_request_schema, "retrieval_request")

    def validate_retrieval_result(self, payload: dict[str, Any]) -> None:
        self._validate(payload, self.template.retrieval_result_schema, "retrieval_result")

    def validate_tool_input(self, tool_name: str, payload: dict[str, Any]) -> None:
        contract = self.template.tool_contracts()[tool_name]
        self._validate(payload, contract["input_schema"], f"{tool_name}.input")

    def validate_tool_output(self, tool_name: str, payload: dict[str, Any]) -> None:
        contract = self.template.tool_contracts()[tool_name]
        self._validate(payload, contract["output_schema"], f"{tool_name}.output")

    def is_valid_agent_output(self, payload: dict[str, Any]) -> bool:
        try:
            self.validate_agent_output(payload)
        except SchemaValidationError:
            return False
        return True

    def _validate(self, payload: dict[str, Any], schema: dict[str, Any], name: str) -> None:
        validator = Draft202012Validator(schema, format_checker=self._format_checker)
        errors = sorted(validator.iter_errors(payload), key=lambda error: list(error.path))
        if errors:
            messages = []
            for error in errors:
                location = ".".join(str(part) for part in error.path) or "$"
                messages.append(f"{name}:{location}: {error.message}")
            raise SchemaValidationError(f"{name} schema validation failed.", messages)

    @staticmethod
    def _business_output_errors(payload: dict[str, Any]) -> list[str]:
        errors: list[str] = []
        calculation = payload.get("calculation", {})
        if payload.get("recommended_payable_amount") != calculation.get("payable_amount"):
            errors.append("recommended_payable_amount must equal calculation.payable_amount")
        if payload.get("recommended_decision") == "request_documents" and not payload.get(
            "missing_documents"
        ):
            errors.append("request_documents requires at least one missing document")
        if payload.get("requires_human_review") and payload.get("recommended_decision") != "human_review":
            errors.append("requires_human_review=true requires recommended_decision=human_review")
        if payload.get("fraud_suspected") and not payload.get("requires_human_review"):
            errors.append("fraud_suspected=true requires requires_human_review=true")
        return errors
