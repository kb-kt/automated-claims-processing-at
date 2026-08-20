import copy
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

from ai_agent_template.developer_kit.plugin_interface import ToolPluginConformance
from ai_agent_template.developer_kit.plugins.remote_fraud_signal_checker_v2 import (
    RemoteFraudSignalCheckerV2Plugin,
)
from ai_agent_template.developer_kit.plugins.synthetic import default_synthetic_plugins
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    SchemaValidator,
    TemplateBundle,
    ToolRegistry,
    WorkflowRunner,
)

from test_support.fraud_check_server import FraudCheckTestServer, unused_local_url


WORKSPACE = Path(__file__).resolve().parents[2]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"
CLAIMS_EVAL = WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl"


class RemoteFraudPluginV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.template = TemplateBundle.load(TEMPLATE_ROOT)
        self.claim = _read_first_jsonl(CLAIMS_EVAL)
        self.payload = _fraud_payload(self.claim)
        self.context = {"claim_payload": self.claim}

    def test_v2_normal_fraud_false_raw_evidence_request(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["signals"]["fraudulent_document"] = True
        with FraudCheckTestServer(lambda request, headers: _v2_response(request, fraud=False)) as server:
            plugin = RemoteFraudSignalCheckerV2Plugin(service_url=server.url)
            envelope = plugin.run(payload, self.context)

        request = server.requests[0]["payload"]
        self.assertEqual(server.requests[0]["path"], "/v2/fraud/check")
        self.assertEqual(request["schema_version"], "2.0.0")
        self.assertEqual(request["analysis_mode"], "raw_evidence")
        self.assertEqual(request["source_system"], "automated_claims_processing_template")
        self.assertEqual(request["upstream_signals"], {})
        self.assertIn("historical_document_fingerprints", request["inline_context"])
        self.assertEqual(envelope["status"], "success")
        self.assertFalse(envelope["result"]["fraud_suspected"])
        self.assertEqual(envelope["result"]["routing"], "continue_claim_review")
        SchemaValidator(self.template).validate_tool_output("fraud_signal_checker", envelope["result"])

    def test_v2_assisted_mode_sends_provenanced_upstream_signals(self) -> None:
        payload = copy.deepcopy(self.payload)
        payload["signals"]["fraudulent_document"] = True
        with FraudCheckTestServer(lambda request, headers: _v2_response(request, fraud=False)) as server:
            plugin = RemoteFraudSignalCheckerV2Plugin(
                service_url=server.url,
                analysis_mode="upstream_signal_assisted",
            )
            envelope = plugin.run(payload, self.context)

        signals = server.requests[0]["payload"]["upstream_signals"]
        self.assertEqual(envelope["status"], "success")
        self.assertTrue(signals["fraudulent_document"]["value"])
        self.assertEqual(signals["fraudulent_document"]["source"], "automated_claims_processing")

    def test_v2_fraud_true_forces_human_review_in_workflow(self) -> None:
        claim = copy.deepcopy(self.claim)
        claim["claim_id"] = "REMOTE-FRAUD-V2-TRUE-001"
        with FraudCheckTestServer(lambda request, headers: _v2_response(request, fraud=True)) as server:
            output = _run_workflow_with_remote_fraud_v2(self.template, claim, service_url=server.url)

        self.assertTrue(output["fraud_suspected"])
        self.assertTrue(output["requires_human_review"])
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertIn("FRAUD_SIGNAL", output["reason_codes"])

    def test_v2_human_review_routing_without_fraud_still_fail_closes_workflow(self) -> None:
        claim = copy.deepcopy(self.claim)
        claim["claim_id"] = "REMOTE-FRAUD-V2-ROUTING-001"
        with FraudCheckTestServer(
            lambda request, headers: _v2_response(
                request,
                fraud=False,
                routing="human_review",
                requires_human_review=True,
                reason_codes=["FRAUD_CHECK_REVIEW_REQUIRED"],
            )
        ) as server:
            output = _run_workflow_with_remote_fraud_v2(self.template, claim, service_url=server.url)

        self.assertFalse(output["fraud_suspected"])
        self.assertTrue(output["requires_human_review"])
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertIn("HUMAN_REVIEW_REQUIRED", output["reason_codes"])

    def test_v2_request_id_or_claim_id_mismatch_returns_failed_envelope(self) -> None:
        for field in ["request_id", "claim_id"]:
            with self.subTest(field=field):
                with FraudCheckTestServer(
                    lambda request, headers, field=field: _v2_response(request, overrides={field: "WRONG"})
                ) as server:
                    plugin = RemoteFraudSignalCheckerV2Plugin(service_url=server.url)
                    envelope = plugin.run(self.payload, self.context)
                self.assertEqual(envelope["status"], "failed")
                self.assertEqual(envelope["error"]["error_code"], "REMOTE_CONTRACT_ERROR")

    def test_v2_safety_invariant_violation_returns_failed_envelope(self) -> None:
        with FraudCheckTestServer(
            lambda request, headers: _v2_response(
                request,
                fraud=True,
                routing="continue_claim_review",
                requires_human_review=False,
            )
        ) as server:
            plugin = RemoteFraudSignalCheckerV2Plugin(service_url=server.url)
            envelope = plugin.run(self.payload, self.context)

        self.assertEqual(envelope["status"], "failed")
        self.assertEqual(envelope["error"]["error_code"], "REMOTE_CONTRACT_ERROR")

    def test_v2_claims_internal_api_failure_returns_failed_envelope(self) -> None:
        plugin = RemoteFraudSignalCheckerV2Plugin(
            service_url="http://127.0.0.1:8010",
            claims_internal_base_url=unused_local_url(),
            timeout_ms=100,
        )
        envelope = plugin.run(self.payload, self.context)

        self.assertEqual(envelope["status"], "failed")
        self.assertEqual(envelope["error"]["error_code"], "CLAIMS_INTERNAL_UNAVAILABLE")
        self.assertTrue(envelope["error"]["retryable"])

    def test_v2_timeout_invalid_json_and_http_errors_return_failed_envelopes(self) -> None:
        with FraudCheckTestServer(lambda request, headers: _v2_response(request), delay_seconds=0.2) as server:
            timeout_envelope = RemoteFraudSignalCheckerV2Plugin(
                service_url=server.url,
                timeout_ms=50,
            ).run(self.payload, self.context)
        self.assertEqual(timeout_envelope["error"]["error_code"], "REMOTE_TIMEOUT")

        with FraudCheckTestServer(lambda request, headers: (200, "{not-json")) as server:
            invalid_json = RemoteFraudSignalCheckerV2Plugin(service_url=server.url).run(self.payload, self.context)
        self.assertEqual(invalid_json["error"]["error_code"], "REMOTE_INVALID_JSON")

        with FraudCheckTestServer(lambda request, headers: (503, {"error": "down"})) as server:
            http_error = RemoteFraudSignalCheckerV2Plugin(service_url=server.url).run(self.payload, self.context)
        self.assertEqual(http_error["error"]["error_code"], "REMOTE_HTTP_ERROR")
        self.assertTrue(http_error["error"]["retryable"])

    def test_v2_auth_header_and_conformance(self) -> None:
        with patch.dict(os.environ, {"FRAUD_CHECK_API_KEY": "fraud-token"}):
            with FraudCheckTestServer(lambda request, headers: _v2_response(request)) as server:
                plugin = RemoteFraudSignalCheckerV2Plugin(service_url=server.url)
                ToolPluginConformance(self.template).assert_conformant(
                    plugin,
                    sample_payload=self.payload,
                    context=self.context,
                )
                auth_header = server.requests[0]["headers"].get("Authorization")

        self.assertEqual(auth_header, "Bearer fraud-token")

    def test_v2_connection_failure_fail_closes_to_human_review(self) -> None:
        claim = copy.deepcopy(self.claim)
        claim["claim_id"] = "REMOTE-FRAUD-V2-DOWN-001"
        output = _run_workflow_with_remote_fraud_v2(
            self.template,
            claim,
            service_url=unused_local_url(),
            timeout_ms=100,
        )

        self.assertFalse(output["fraud_suspected"])
        self.assertTrue(output["requires_human_review"])
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertIn("TOOL_FAILURE", output["reason_codes"])


def _run_workflow_with_remote_fraud_v2(
    template: TemplateBundle,
    claim: dict,
    *,
    service_url: str,
    timeout_ms: int = 15000,
) -> dict:
    registry = ToolRegistry(template)
    for plugin in default_synthetic_plugins():
        if plugin.name != "fraud_signal_checker":
            registry.register(plugin)
    registry.register(RemoteFraudSignalCheckerV2Plugin(service_url=service_url, timeout_ms=timeout_ms))
    registry.validate_registered_plugins()
    return WorkflowRunner(template, tool_registry=registry).run(claim)


def _v2_response(
    request: dict,
    *,
    fraud: bool = False,
    routing: str | None = None,
    requires_human_review: bool | None = None,
    reason_codes: list[str] | None = None,
    overrides: dict | None = None,
) -> tuple[int, dict]:
    body = {
        "schema_version": "2.0.0",
        "request_id": request.get("request_id"),
        "claim_id": request.get("claim_id"),
        "status": "success",
        "fraud_suspected": fraud,
        "fraud_reason_codes": reason_codes if reason_codes is not None else (["FRAUD_SIGNAL"] if fraud else []),
        "risk_score": 87 if fraud else 5,
        "routing": routing or ("human_review" if fraud else "continue_claim_review"),
        "requires_human_review": requires_human_review if requires_human_review is not None else fraud,
        "engine_version": "fraud-check-test-2.0.0",
        "workflow_version": "fraud-workflow-test-2.0.0",
        "document_findings": [],
        "history_findings": [],
        "evidence": [],
        "analysis_warnings": [],
        "tool_failures": [],
    }
    if overrides:
        body.update(overrides)
    return 200, body


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
