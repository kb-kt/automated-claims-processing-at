import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from ai_agent_template.developer_kit.plugin_interface import ToolPluginConformance
from ai_agent_template.developer_kit.plugins.remote_fraud_signal_checker import (
    RemoteFraudSignalCheckerPlugin,
)
from ai_agent_template.developer_kit.plugins.synthetic import default_synthetic_plugins
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    SchemaValidator,
    TemplateBundle,
    ToolRegistry,
    WorkflowRunner,
)

from test_support.fraud_check_server import (
    FraudCheckTestServer,
    synthetic_like_fraud_response,
    unused_local_url,
)


WORKSPACE = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"
CLAIMS_EVAL = WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl"


class RemoteFraudPluginTest(unittest.TestCase):
    def setUp(self) -> None:
        self.template = TemplateBundle.load(TEMPLATE_ROOT)
        self.claim = _read_first_jsonl(CLAIMS_EVAL)
        self.payload = _fraud_payload(self.claim)

    def test_normal_fraud_false_response(self) -> None:
        with FraudCheckTestServer(lambda payload, headers: synthetic_like_fraud_response(payload, headers)) as server:
            plugin = RemoteFraudSignalCheckerPlugin(service_url=server.url)
            envelope = plugin.run(self.payload, {})

        self.assertEqual(envelope["status"], "success")
        self.assertFalse(envelope["result"]["fraud_suspected"])
        self.assertEqual(envelope["result"]["routing"], "continue_claim_review")
        self.assertEqual(envelope["metadata"]["contract_version"], "1.0.0")
        SchemaValidator(self.template).validate_tool_output("fraud_signal_checker", envelope["result"])

    def test_normal_fraud_true_response_forces_human_review_in_workflow(self) -> None:
        claim = copy.deepcopy(self.claim)
        claim["claim_id"] = "REMOTE-FRAUD-TRUE-001"
        claim["signals"]["suspected_duplicate_receipt"] = True
        claim["claim_history"]["prior_receipt_hashes"] = [claim["claim"]["receipt_hash"]]
        with FraudCheckTestServer(lambda payload, headers: synthetic_like_fraud_response(payload, headers)) as server:
            output = _run_workflow_with_remote_fraud(self.template, claim, service_url=server.url)

        self.assertTrue(output["fraud_suspected"])
        self.assertTrue(output["requires_human_review"])
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertIn("DUPLICATE_RECEIPT_SUSPECTED", output["reason_codes"])

    def test_timeout_returns_failed_retryable_envelope(self) -> None:
        with FraudCheckTestServer(
            lambda payload, headers: synthetic_like_fraud_response(payload, headers),
            delay_seconds=0.2,
        ) as server:
            plugin = RemoteFraudSignalCheckerPlugin(service_url=server.url, timeout_ms=50)
            envelope = plugin.run(self.payload, {})

        self.assertEqual(envelope["status"], "failed")
        self.assertEqual(envelope["error"]["error_code"], "REMOTE_TIMEOUT")
        self.assertTrue(envelope["error"]["retryable"])
        self.assertIsNone(envelope["result"])

    def test_connection_failure_returns_failed_retryable_envelope(self) -> None:
        plugin = RemoteFraudSignalCheckerPlugin(service_url="http://127.0.0.1:9", timeout_ms=100)
        with patch(
            "ai_agent_template.developer_kit.plugins.remote_fraud_signal_checker.urlopen",
            side_effect=URLError(ConnectionRefusedError("connection refused")),
        ):
            envelope = plugin.run(self.payload, {})

        self.assertEqual(envelope["status"], "failed")
        self.assertEqual(envelope["error"]["error_code"], "REMOTE_CONNECTION_ERROR")
        self.assertTrue(envelope["error"]["retryable"])

    def test_http_4xx_and_5xx_return_failed_envelopes(self) -> None:
        for status, retryable in [(400, False), (503, True)]:
            with self.subTest(status=status):
                with FraudCheckTestServer(lambda payload, headers, status=status: (status, {"error": "failed"})) as server:
                    plugin = RemoteFraudSignalCheckerPlugin(service_url=server.url)
                    envelope = plugin.run(self.payload, {})
                self.assertEqual(envelope["status"], "failed")
                self.assertEqual(envelope["error"]["error_code"], "REMOTE_HTTP_ERROR")
                self.assertEqual(envelope["error"]["retryable"], retryable)

    def test_invalid_json_returns_failed_envelope(self) -> None:
        with FraudCheckTestServer(lambda payload, headers: (200, "{not-json")) as server:
            plugin = RemoteFraudSignalCheckerPlugin(service_url=server.url)
            envelope = plugin.run(self.payload, {})

        self.assertEqual(envelope["status"], "failed")
        self.assertEqual(envelope["error"]["error_code"], "REMOTE_INVALID_JSON")
        self.assertFalse(envelope["error"]["retryable"])

    def test_missing_required_response_fields_returns_failed_envelope(self) -> None:
        with FraudCheckTestServer(
            lambda payload, headers: (200, {"fraud_suspected": False, "fraud_reason_codes": []})
        ) as server:
            plugin = RemoteFraudSignalCheckerPlugin(service_url=server.url)
            envelope = plugin.run(self.payload, {})

        self.assertEqual(envelope["status"], "failed")
        self.assertEqual(envelope["error"]["error_code"], "REMOTE_CONTRACT_ERROR")

    def test_authorization_header_is_optional_and_supported(self) -> None:
        with patch.dict(os.environ, {"FRAUD_CHECK_API_KEY": "test-token"}):
            with FraudCheckTestServer(lambda payload, headers: synthetic_like_fraud_response(payload, headers)) as server:
                plugin = RemoteFraudSignalCheckerPlugin(service_url=server.url)
                envelope = plugin.run(self.payload, {})
                auth_header = server.requests[0]["headers"].get("Authorization")

        self.assertEqual(envelope["status"], "success")
        self.assertEqual(auth_header, "Bearer test-token")

    def test_remote_plugin_conforms_to_tool_contract(self) -> None:
        with FraudCheckTestServer(lambda payload, headers: synthetic_like_fraud_response(payload, headers)) as server:
            plugin = RemoteFraudSignalCheckerPlugin(service_url=server.url)
            ToolPluginConformance(self.template).assert_conformant(
                plugin,
                sample_payload=self.payload,
            )

    def test_failed_remote_fraud_check_fail_closes_to_human_review(self) -> None:
        claim = copy.deepcopy(self.claim)
        claim["claim_id"] = "REMOTE-FRAUD-DOWN-001"
        output = _run_workflow_with_remote_fraud(
            self.template,
            claim,
            service_url=unused_local_url(),
            timeout_ms=100,
        )

        self.assertFalse(output["fraud_suspected"])
        self.assertTrue(output["requires_human_review"])
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertIn("TOOL_FAILURE", output["reason_codes"])


def _run_workflow_with_remote_fraud(
    template: TemplateBundle,
    claim: dict,
    *,
    service_url: str,
    timeout_ms: int = 3000,
) -> dict:
    registry = ToolRegistry(template)
    for plugin in default_synthetic_plugins():
        if plugin.name != "fraud_signal_checker":
            registry.register(plugin)
    registry.register(RemoteFraudSignalCheckerPlugin(service_url=service_url, timeout_ms=timeout_ms))
    registry.validate_registered_plugins()
    return WorkflowRunner(template, tool_registry=registry).run(claim)


def _fraud_payload(claim: dict) -> dict:
    return {
        "insured_profile": claim["insured_profile"],
        "claim": claim["claim"],
        "claim_history": claim["claim_history"],
        "signals": claim["signals"],
    }


def _read_first_jsonl(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.loads(next(line for line in file if line.strip()))


if __name__ == "__main__":
    unittest.main()
