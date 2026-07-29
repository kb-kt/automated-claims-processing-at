from __future__ import annotations

from typing import Any

from jsonschema import Draft202012Validator

from .base import SyntheticToolPlugin


class SyntheticDecisionValidatorPlugin(SyntheticToolPlugin):
    name = "decision_validator"
    contract_name = "decision_validator"
    failure_policy = "fail"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        agent_output = payload.get("agent_output", {})
        errors = _validate_output_invariants(agent_output)
        schema = context.get("output_schema")
        if schema:
            for error in Draft202012Validator(schema).iter_errors(agent_output):
                errors.append(error.message)
        return self.ok({"valid": not errors, "errors": errors, "warnings": []})


def _validate_output_invariants(output: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    calculation = output.get("calculation", {})
    if output.get("recommended_payable_amount") != calculation.get("payable_amount"):
        errors.append("recommended_payable_amount must equal calculation.payable_amount")
    if output.get("requires_human_review") and output.get("recommended_decision") != "human_review":
        errors.append("requires_human_review requires human_review decision")
    if output.get("fraud_suspected") and not output.get("requires_human_review"):
        errors.append("fraud_suspected requires human review")
    if output.get("recommended_decision") == "request_documents" and not output.get("missing_documents"):
        errors.append("request_documents requires missing_documents")
    return errors

