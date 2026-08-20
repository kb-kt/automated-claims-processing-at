from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from ai_agent_template.developer_kit.plugins.synthetic import default_synthetic_plugins
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    ReleaseGate,
    ApiAccessControl,
    TemplateBundle,
    TemplateContractValidator,
    ToolRegistry,
    WorkflowRunner,
    assert_no_label_leakage,
    build_decision_provenance,
    redact_sensitive_data,
    validate_startup_configuration,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk.errors import (
    SafetyValidationError,
    StartupValidationError,
)


WORKSPACE = Path(__file__).resolve().parents[4]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"
STARTER_CONFIG = TEMPLATE_ROOT / "developer_kit" / "starter_kit" / "config"


class CompletionSafetyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = TemplateBundle.load(TEMPLATE_ROOT)
        cls.pay_claim = _claim_for_decision("pay")

    def test_template_contracts_are_cross_artifact_consistent(self) -> None:
        result = TemplateContractValidator(self.template).validate()
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["tool_contract_count"], 8)
        self.assertEqual(result["workflow_tool_count"], 8)

    def test_nested_label_leakage_is_rejected(self) -> None:
        payload = json.loads(json.dumps(self.pay_claim))
        payload["medical_evidence"]["prior_medical_evidence"]["expected_decision"] = "pay"
        with self.assertRaises(SafetyValidationError) as context:
            assert_no_label_leakage(
                payload,
                context="test claim",
                forbid_agent_output_fields=True,
            )
        self.assertTrue(any("expected_decision" in item for item in context.exception.findings))

    def test_every_core_tool_failure_routes_to_human_review(self) -> None:
        for tool_name in sorted(self.template.tool_contracts()):
            with self.subTest(tool=tool_name):
                registry = ToolRegistry(self.template)
                for plugin in default_synthetic_plugins():
                    registry.register(plugin)
                registry.register(_FailingPlugin(tool_name, self.template.tool_contracts()[tool_name]))
                output = WorkflowRunner(self.template, tool_registry=registry).run(
                    json.loads(json.dumps(self.pay_claim))
                )
                self.assertEqual(output["recommended_decision"], "human_review")
                self.assertTrue(output["requires_human_review"])
                self.assertIn("TOOL_FAILURE", output["reason_codes"])

    def test_document_extraction_failure_routes_to_human_review(self) -> None:
        registry = _default_registry(self.template)
        output = WorkflowRunner(
            self.template,
            tool_registry=registry,
            document_extractor=_FailingDocumentExtractor(),
        ).run(json.loads(json.dumps(self.pay_claim)))
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertTrue(output["requires_human_review"])
        self.assertIn("TOOL_FAILURE", output["reason_codes"])

    def test_fraud_tool_failure_is_not_reported_as_low_risk_success(self) -> None:
        contract = self.template.tool_contracts()["fraud_signal_checker"]
        registry = _default_registry(self.template)
        registry.register(_FailingPlugin("fraud_signal_checker", contract))
        output = WorkflowRunner(self.template, tool_registry=registry).run(
            json.loads(json.dumps(self.pay_claim))
        )
        report = next(
            item for item in output["specialist_reports"]
            if item["agent_name"] == "fraud_risk_analysis"
        )

        self.assertEqual("failed", report["status"])
        self.assertEqual("high", report["risk_level"])
        self.assertTrue(report["requires_human_review"])
        self.assertIn("TOOL_FAILURE", report["reason_codes"])
        self.assertEqual(
            "FRAUD_SIGNAL_CHECKER_ERROR",
            report["findings"][0]["error_code"],
        )

    def test_specialist_failure_routes_to_human_review(self) -> None:
        output = WorkflowRunner(
            self.template,
            tool_registry=_default_registry(self.template),
            specialist_agents=[_FailingSpecialist()],
        ).run(json.loads(json.dumps(self.pay_claim)))
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertTrue(output["requires_human_review"])
        self.assertEqual(output["specialist_reports"][0]["status"], "failed")

    def test_release_gate_reports_missing_or_failed_blocking_metrics(self) -> None:
        gate = ReleaseGate.from_file(TEMPLATE_ROOT / "eval" / "thresholds.yaml")
        result = gate.evaluate({"schema_validity": 1.0})
        self.assertFalse(result["passed"])
        self.assertTrue(
            any(item["metric"] == "decision_accuracy" for item in result["blocking_failures"])
        )

    def test_release_gate_passes_when_all_blocking_thresholds_are_met(self) -> None:
        gate = ReleaseGate.from_file(TEMPLATE_ROOT / "eval" / "thresholds.yaml")
        metrics = {}
        for threshold in gate.thresholds:
            if threshold.operator in {">=", ">", "=="}:
                metrics[threshold.metric] = threshold.target + (0.01 if threshold.operator == ">" else 0)
            else:
                metrics[threshold.metric] = threshold.target - (0.01 if threshold.operator == "<" else 0)
        self.assertTrue(gate.evaluate(metrics)["passed"])

    def test_valid_starter_configuration_passes_startup_validation(self) -> None:
        result = validate_startup_configuration(
            template_root=TEMPLATE_ROOT,
            plugin_config_path=STARTER_CONFIG / "plugins.yaml",
            specialist_config_path=STARTER_CONFIG / "specialist_plugins.synthetic_insurer.yaml",
            model_config_path=STARTER_CONFIG / "model_config.yaml",
            retrieval_enabled=True,
            retrieval_mode="keyword",
            retrieval_top_k=3,
            max_document_bytes=10_000_000,
            fail_closed=True,
        )
        self.assertEqual(result["status"], "ready")
        self.assertEqual(len(result["registered_tools"]), 8)

    def test_unsafe_startup_configuration_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "missing.yaml"
            with self.assertRaises(StartupValidationError) as context:
                validate_startup_configuration(
                    template_root=TEMPLATE_ROOT,
                    plugin_config_path=missing,
                    specialist_config_path=STARTER_CONFIG / "specialist_plugins.synthetic_insurer.yaml",
                    model_config_path=STARTER_CONFIG / "model_config.yaml",
                    retrieval_enabled=True,
                    retrieval_mode="unsupported",
                    retrieval_top_k=0,
                    max_document_bytes=0,
                    fail_closed=False,
                )
        joined = " ".join(context.exception.errors)
        self.assertIn("fail_closed", joined)
        self.assertIn("plugin config not found", joined)
        self.assertIn("retrieval.top_k", joined)

    def test_api_access_control_enforces_customer_reviewer_admin_roles(self) -> None:
        control = ApiAccessControl(
            enabled=True,
            customer_api_key="customer-secret",
            reviewer_api_key="reviewer-secret",
            admin_api_key="admin-secret",
        )
        self.assertEqual(control.authorize(method="POST", path="/claims", authorization=None).status_code, 401)
        self.assertTrue(
            control.authorize(
                method="POST", path="/claims", authorization="Bearer customer-secret"
            ).allowed
        )
        self.assertEqual(
            control.authorize(
                method="GET", path="/reviews/queue", authorization="Bearer customer-secret"
            ).status_code,
            403,
        )
        self.assertTrue(
            control.authorize(
                method="GET", path="/reviews/queue", authorization="Bearer reviewer-secret"
            ).allowed
        )
        self.assertTrue(
            control.authorize(
                method="POST", path="/evaluations/runs", authorization="Bearer admin-secret"
            ).allowed
        )

    def test_sensitive_audit_data_is_redacted_and_tokenized(self) -> None:
        redacted = redact_sensitive_data(
            {
                "authorization": "Bearer secret",
                "api_key": "secret",
                "insured_id": "INS-SYN-001",
                "full_name": "Synthetic Person",
            }
        )
        self.assertEqual(redacted["authorization"], "[REDACTED]")
        self.assertEqual(redacted["api_key"], "[REDACTED]")
        self.assertTrue(redacted["insured_id"].startswith("tok_"))
        self.assertEqual(redacted["full_name"], "[REDACTED]")

    def test_decision_provenance_is_stable_and_versioned(self) -> None:
        registry = _default_registry(self.template)
        provider = type("Provider", (), {"provider_name": "test", "model_id": "model", "version": "1"})()
        first = build_decision_provenance(
            self.template,
            model_provider=provider,
            tool_registry=registry,
            specialist_agents=[],
            policy_sources=self.template.policy_document_candidates(),
        )
        second = build_decision_provenance(
            self.template,
            model_provider=provider,
            tool_registry=registry,
            specialist_agents=[],
            policy_sources=self.template.policy_document_candidates(),
        )
        self.assertEqual(first, second)
        self.assertEqual(first["provenance_version"], "1.0.0")
        self.assertEqual(len(first["workflow_sha256"]), 64)
        self.assertEqual(len(first["bundle_sha256"]), 64)


class _FailingPlugin:
    def __init__(self, name: str, contract: dict) -> None:
        self.name = name
        self.contract_name = name
        self.contract_version = contract["version"]
        self.failure_policy = "human_review"

    def run(self, payload: dict, context: dict) -> dict:
        raise RuntimeError("forced conformance failure")


class _FailingDocumentExtractor:
    def extract_for_claim(self, claim_payload: dict) -> list[dict]:
        raise RuntimeError("forced document extraction failure")


class _FailingSpecialist:
    name = "forced_failure_specialist"
    version = "1.0.0"

    def run(self, payload: dict, context: dict) -> dict:
        raise RuntimeError("forced specialist failure")


def _default_registry(template: TemplateBundle) -> ToolRegistry:
    registry = ToolRegistry(template)
    for plugin in default_synthetic_plugins():
        registry.register(plugin)
    return registry


def _claim_for_decision(decision: str) -> dict:
    generated = WORKSPACE / "data_generator" / "generated"
    labels = {
        row["claim_id"]: row
        for row in _read_jsonl(generated / "labels_eval.jsonl")
    }
    return next(
        row
        for row in _read_jsonl(generated / "claims_eval.jsonl")
        if labels[row["claim_id"]]["expected_decision"] == decision
    )


def _read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


if __name__ == "__main__":
    unittest.main()
