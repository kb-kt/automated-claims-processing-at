from __future__ import annotations

import copy
import json
from typing import Any

from ai_agent_template.developer_kit.sdk.claim_agent_sdk.errors import SchemaValidationError

from .errors import NotFound, ValidationFailed
from .settings import Settings
from .template_runtime import TemplateRuntime


_FRAUD_PRESET_SPECS = (
    ("fraud_clean", "Clean baseline", "CLM-EVAL-900001", False, "continue_claim_review", [], "No duplicate, mismatch, or threshold signal."),
    ("fraud_exact_duplicate", "Exact duplicate receipt", "CLM-EVAL-900002", True, "human_review", ["DUPLICATE_RECEIPT_SUSPECTED"], "Reuses an identical receipt hash from claim history."),
    ("fraud_legacy_receipt", "Legacy receipt ID duplicate", "CLM-EVAL-900003", True, "human_review", ["DUPLICATE_RECEIPT_SUSPECTED"], "Reuses a receipt ID while the binary hash differs."),
    ("fraud_altered_duplicate", "Altered duplicate receipt", "CLM-EVAL-900004", True, "human_review", ["ALTERED_DUPLICATE_RECEIPT_SUSPECTED"], "Changes document content while retaining matching text or visual fingerprint evidence."),
    ("fraud_amount_mismatch", "Document amount mismatch", "CLM-EVAL-900005", True, "human_review", ["DOCUMENT_AMOUNT_MISMATCH"], "Claimed amount differs from the receipt evidence."),
    ("fraud_date_mismatch", "Document date mismatch", "CLM-EVAL-900006", True, "human_review", ["DOCUMENT_DATE_MISMATCH"], "Treatment dates differ between claim and document evidence."),
    ("fraud_provider_mismatch", "Provider mismatch", "CLM-EVAL-900007", True, "human_review", ["DOCUMENT_PROVIDER_MISMATCH"], "Provider identity differs between claim and document evidence."),
    ("fraud_repeat_2", "Repeat boundary: 2 claims", "CLM-EVAL-900009", False, "continue_claim_review", [], "Two same-insured/provider claims stay below the threshold."),
    ("fraud_repeat_3", "Repeat threshold: 3 claims", "CLM-EVAL-900010", True, "human_review", ["SAME_INSURED_PROVIDER_REPEAT_SUSPECTED"], "Three same-insured/provider claims reach the review threshold."),
    ("fraud_provider_49", "Provider boundary: 49 claims", "CLM-EVAL-900011", False, "continue_claim_review", [], "Provider volume remains immediately below the threshold."),
    ("fraud_provider_50", "Provider threshold: 50 claims", "CLM-EVAL-900012", True, "human_review", ["PROVIDER_PATTERN_ANOMALY_SUSPECTED"], "Provider volume reaches the anomaly threshold."),
    ("fraud_document_missing", "Missing document", "CLM-EVAL-900020", False, "human_review", ["DOCUMENT_UNAVAILABLE"], "A required document is unavailable and must fail closed without a fraud accusation."),
    ("fraud_document_corrupt", "Corrupted PDF", "CLM-EVAL-900021", False, "human_review", ["DOCUMENT_UNAVAILABLE"], "A corrupted PDF must route to human review without automatic denial."),
)


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

    def list_fraud_presets(self) -> dict[str, Any]:
        claims = self._load_eval_claims()
        presets = [self._fraud_preset(spec, claims) for spec in _FRAUD_PRESET_SPECS]
        return {
            "version": "1.0.0",
            "description": "Raw-evidence Fraud_Check v2 presets. Runtime claims never contain evaluation labels.",
            "seed_required": True,
            "scenarios": presets,
        }

    def get_fraud_preset(self, preset_id: str) -> dict[str, Any]:
        claims = self._load_eval_claims()
        for spec in _FRAUD_PRESET_SPECS:
            if spec[0] == preset_id:
                return self._fraud_preset(spec, claims)
        raise NotFound(f"Fraud demo preset not found: {preset_id}")

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

    def _load_eval_claims(self) -> dict[str, dict[str, Any]]:
        path = self.settings.claims_eval_path
        if not path.exists():
            raise ValidationFailed(f"Generated eval claims file not found: {path}")
        selected_ids = {spec[2] for spec in _FRAUD_PRESET_SPECS}
        claims: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                claim = json.loads(line)
                claim_id = claim.get("claim_id")
                if claim_id in selected_ids:
                    self.runtime.validator.validate_claim_input(claim)
                    claims[claim_id] = claim
        missing = sorted(selected_ids - set(claims))
        if missing:
            raise ValidationFailed("Required Fraud demo claims are missing.", missing)
        return claims

    @staticmethod
    def _fraud_preset(spec: tuple[Any, ...], claims: dict[str, dict[str, Any]]) -> dict[str, Any]:
        preset_id, name, claim_id, expected_fraud, routing, reason_codes, summary = spec
        return copy.deepcopy(
            {
                "id": preset_id,
                "name": name,
                "category": "fraud_check",
                "expected_decision": routing,
                "expected_fraud_suspected": expected_fraud,
                "expected_fraud_routing": routing,
                "expected_reason_codes": reason_codes,
                "summary": summary,
                "verification_points": [
                    f"Fraud routing: {routing}.",
                    f"Expected reason: {', '.join(reason_codes) if reason_codes else 'no fraud reason code'}.",
                    "The claim ID stays fixed so seeded history and document evidence remain linked.",
                ],
                "preserve_claim_id": True,
                "requires_fraud_context_seed": True,
                "claim": claims[claim_id],
            }
        )

    @staticmethod
    def _public_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
        return copy.deepcopy(
            {
                "id": scenario["id"],
                "name": scenario["name"],
                "category": scenario.get("category", "demo"),
                "expected_decision": scenario["expected_decision"],
                "expected_runtime_decision": scenario.get(
                    "expected_runtime_decision", scenario["expected_decision"]
                ),
                "expected_fraud_suspected": bool(scenario.get("expected_fraud_suspected", False)),
                "summary": scenario.get("summary", ""),
                "verification_points": list(scenario.get("verification_points", [])),
                "claim": scenario["claim"],
            }
        )
