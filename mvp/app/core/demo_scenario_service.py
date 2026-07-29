from __future__ import annotations

import copy
import json
from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk.errors import SchemaValidationError

from .errors import NotFound, ValidationFailed
from .settings import Settings
from .template_runtime import TemplateRuntime


class DemoScenarioService:
    def __init__(self, *, settings: Settings, runtime: TemplateRuntime):
        self.settings = settings
        self.runtime = runtime

    def list_scenarios(self) -> dict[str, Any]:
        data = self._load()
        return {
            "version": data.get("version", "unknown"),
            "description": data.get("description", ""),
            "scenarios": [
                self._public_scenario(scenario)
                for scenario in data.get("scenarios", [])
            ],
        }

    def get_scenario(self, scenario_id: str) -> dict[str, Any]:
        for scenario in self._load().get("scenarios", []):
            if scenario.get("id") == scenario_id:
                return self._public_scenario(scenario)
        raise NotFound(f"Demo scenario not found: {scenario_id}")

    def _load(self) -> dict[str, Any]:
        path = self.settings.demo_scenarios_path
        if not path.exists():
            raise ValidationFailed(f"Demo scenarios file not found: {path}")
        with path.open("r", encoding="utf-8") as file:
            data = json.load(file)
        scenarios = data.get("scenarios")
        if not isinstance(scenarios, list) or not scenarios:
            raise ValidationFailed("Demo scenarios file must contain at least one scenario.")
        for scenario in scenarios:
            self._validate_scenario(scenario)
        return data

    def _validate_scenario(self, scenario: dict[str, Any]) -> None:
        required = ["id", "name", "expected_decision", "summary", "verification_points", "claim"]
        missing = [field for field in required if field not in scenario]
        if missing:
            raise ValidationFailed(
                "Demo scenario is missing required metadata.",
                [f"{scenario.get('id', 'unknown')}: missing {field}" for field in missing],
            )
        try:
            self.runtime.validator.validate_claim_input(scenario["claim"])
        except SchemaValidationError as exc:
            raise ValidationFailed(
                f"Demo scenario claim is not schema-valid: {scenario.get('id')}",
                exc.errors,
            ) from exc

    @staticmethod
    def _public_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "id": scenario["id"],
                "name": scenario["name"],
                "category": scenario.get("category", "demo"),
                "expected_decision": scenario["expected_decision"],
                "expected_fraud_suspected": bool(scenario.get("expected_fraud_suspected", False)),
                "summary": scenario.get("summary", ""),
                "verification_points": list(scenario.get("verification_points", [])),
                "claim": scenario["claim"],
            }
        )
