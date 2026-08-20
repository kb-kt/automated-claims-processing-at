import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

from mvp.app.core.claim_service import ClaimService
from mvp.app.core.demo_scenario_service import DemoScenarioService
from mvp.app.core.errors import ValidationFailed
from mvp.app.core.review_service import ReviewService
from mvp.app.core.settings import Settings
from mvp.app.core.template_runtime import TemplateRuntime
from mvp.app.db.sqlite import SQLiteRepository
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import ValidationApiError
from test_support.fraud_check_server import FraudCheckTestServer, synthetic_like_fraud_response, unused_local_url


WORKSPACE = Path(__file__).resolve().parents[2]
MVP_ROOT = WORKSPACE / "mvp"


class ClaimReviewStage2Test(unittest.TestCase):
    def test_claim_service_validates_and_persists_claim(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            runtime = TemplateRuntime.build(Settings.load())
            result = ClaimService(repository=repo, runtime=runtime).submit_claim(claim)
            stored = repo.get_claim(claim["claim_id"])
            listed = ClaimService(repository=repo, runtime=runtime).list_claims(limit=10)["claims"]
        self.assertEqual(result["status"], "accepted")
        self.assertEqual(stored["claim_id"], claim["claim_id"])
        self.assertEqual(listed[0]["claim_id"], claim["claim_id"])

    def test_claim_service_rejects_invalid_payload(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        claim.pop("claim_id")
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            runtime = TemplateRuntime.build(Settings.load())
            service = ClaimService(repository=repo, runtime=runtime)
            with self.assertRaises(ValidationFailed):
                service.submit_claim(claim)

    def test_claim_service_rejects_product_policy_mismatch(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        claim = json.loads(json.dumps(claim))
        claim["product_id"] = "ABL-UNIV-LIFE-2501-RDR_SURGERY"
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            runtime = TemplateRuntime.build(Settings.load())
            with self.assertRaises(ValidationApiError):
                ClaimService(repository=repo, runtime=runtime).submit_claim(claim)

    def test_non_active_product_adjudication_fails_closed_to_human_review(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        claim = json.loads(json.dumps(claim))
        claim["claim_id"] = "MVP-MULTI-PRODUCT-REVIEW-001"
        claim["product_id"] = "ABL-UNIV-LIFE-2501-RDR_SURGERY"
        claim["policy_id"] = "POL-SYN-ABL-UNIV-LIFE-2501-RDR_SURGERY-0001"
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            runtime = TemplateRuntime.build(Settings.load())
            output = ReviewService(repository=repo, runtime=runtime).run_review(
                claim_payload=claim
            )["output"]

        self.assertEqual("human_review", output["recommended_decision"])
        self.assertTrue(output["requires_human_review"])
        self.assertIn("PRODUCT_ADJUDICATION_PROFILE_UNAVAILABLE", output["reason_codes"])

    def test_claim_service_backfills_legacy_demo_payload_fields(self) -> None:
        claim = _legacy_claim(_read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl"))
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            runtime = TemplateRuntime.build(Settings.load())
            result = ClaimService(repository=repo, runtime=runtime).submit_claim(claim)
            stored = repo.get_claim(result["claim_id"])

        self.assertEqual(result["status"], "accepted")
        self.assertIn("insured_profile", stored)
        self.assertIn("receipt_hash", stored["claim"])
        self.assertIn("provider_id", stored["claim"])
        self.assertIn("same_insured_provider_claims_30d", stored["claim_history"])
        self.assertIn("prior_receipt_hashes", stored["claim_history"])

    def test_review_service_backfills_legacy_direct_claim_payload_fields(self) -> None:
        claim = _legacy_claim(_read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl"))
        claim["claim_id"] = "LEGACY-DEMO-REVIEW-001"
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            runtime = TemplateRuntime.build(Settings.load())
            output = ReviewService(repository=repo, runtime=runtime).run_review(claim_payload=claim)["output"]

        self.assertEqual(output["claim_id"], "LEGACY-DEMO-REVIEW-001")
        self.assertIn(output["recommended_decision"], {"pay", "partial_pay", "request_documents", "deny", "human_review"})

    def test_review_service_runs_workflow_and_persists_logs_and_citations(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        with tempfile.TemporaryDirectory() as temp_dir:
            db_path = Path(temp_dir) / "mvp.sqlite3"
            repo = _repo(Path(temp_dir), db_path=db_path)
            runtime = TemplateRuntime.build(Settings.load())
            ClaimService(repository=repo, runtime=runtime).submit_claim(claim)

            service = ReviewService(repository=repo, runtime=runtime)
            result = service.run_review(claim_id=claim["claim_id"])
            output = result["output"]
            stored = service.get_review(claim["claim_id"])
            service.save_reviewer_action(
                claim["claim_id"],
                {
                    "action": "accept_recommendation",
                    "reviewer_id": "reviewer-001",
                    "reviewer_note": "accepted",
                },
            )
            queue = service.list_review_queue(limit=10)["queue"]
            actions = service.list_reviewer_actions(claim["claim_id"])["actions"]
            audit_logs = service.list_audit_logs(claim_id=claim["claim_id"])["audit_logs"]
            persisted_reports = service.list_specialist_agent_reports(claim["claim_id"])["reports"]
            extraction_rows = repo.list_document_extraction_results(claim["claim_id"])
            counts = _table_counts(
                db_path,
                [
                    "reviews",
                    "tool_call_logs",
                    "retrieval_logs",
                    "reviewer_actions",
                    "audit_logs",
                    "specialist_agent_reports",
                ],
            )

        self.assertEqual(result["review_status"], "completed")
        self.assertEqual(stored["claim_id"], claim["claim_id"])
        self.assertEqual(counts["reviews"], 1)
        self.assertEqual(counts["tool_call_logs"], 8)
        self.assertEqual(counts["retrieval_logs"], 1)
        self.assertEqual(counts["reviewer_actions"], 1)
        self.assertEqual(counts["specialist_agent_reports"], 4)
        self.assertGreaterEqual(counts["audit_logs"], 4)
        self.assertEqual(queue[0]["claim_id"], claim["claim_id"])
        self.assertIn("policy_id_masked", queue[0])
        self.assertNotIn("policy_id", queue[0])
        self.assertEqual(actions[0]["action"], "accept_recommendation")
        self.assertEqual(audit_logs[0]["event_type"], "reviewer_action_saved")
        completed_audit = next(item for item in audit_logs if item["event_type"] == "review_completed")
        provenance = completed_audit["metadata"]["decision_provenance"]
        self.assertEqual(provenance["provenance_version"], "1.0.0")
        self.assertEqual(len(provenance["workflow_sha256"]), 64)
        self.assertTrue(any("citation_id" in item for item in output["policy_basis"]))
        self.assertEqual(output["recommended_payable_amount"], output["calculation"]["payable_amount"])
        self.assertEqual(
            output["confidence_assessment"]["score_source"],
            "deterministic_rules_with_llm_assistance",
        )
        self.assertEqual(output["confidence_assessment"]["deterministic_confidence"], output["confidence"])
        self.assertEqual(output["explanation_confidence"]["source"], "llm_output_validation")
        self.assertEqual(output["explanation_confidence"]["calculation_alignment"], "pass")
        self.assertIn(output["explanation_confidence"]["faithfulness_to_tools"], {"high", "medium", "low"})
        self.assertEqual(
            [report["agent_name"] for report in output["specialist_reports"]],
            [
                "policy_coverage_analysis",
                "document_understanding",
                "medical_review_causality",
                "fraud_risk_analysis",
            ],
        )
        self.assertEqual(stored["specialist_reports"], output["specialist_reports"])
        self.assertEqual(persisted_reports, output["specialist_reports"])
        document_report = next(
            report for report in output["specialist_reports"] if report["agent_name"] == "document_understanding"
        )
        self.assertTrue(
            any(item.get("finding_type") == "document_extraction" for item in document_report["findings"])
        )
        self.assertTrue(extraction_rows)
        self.assertTrue(
            any(row["extraction_status"] in {"extracted", "partial"} for row in extraction_rows)
        )

    def test_review_service_uses_seeded_medical_registry_at_runtime(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        claim = json.loads(json.dumps(claim))
        claim.pop("medical_evidence", None)
        claim["claim_id"] = "MVP-RUNTIME-REGISTRY-001"
        claim["claim"]["diagnosis_code"] = "SYN-M54"
        claim["claim"]["treatment_code"] = "TRT-NONCOV-001"
        generated = WORKSPACE / "data_generator" / "generated"
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            repo.seed_medical_registry(
                medical_code_registry=_read_json(generated / "medical_code_registry.json"),
                edi_code_registry=_read_json(generated / "edi_code_registry.json"),
                diagnosis_treatment_rules=_read_json(generated / "diagnosis_treatment_rules.json"),
                insurer_medical_routing_rules=_read_json(generated / "insurer_medical_routing_rules.json"),
                source_files=["mvp-runtime-registry-smoke"],
            )
            runtime = TemplateRuntime.build(Settings.load())
            output = ReviewService(repository=repo, runtime=runtime).run_review(claim_payload=claim)["output"]

        medical_report = next(
            report for report in output["specialist_reports"] if report["agent_name"] == "medical_review_causality"
        )
        pair_finding = next(
            finding
            for finding in medical_report["findings"]
            if finding.get("finding_type") == "diagnosis_treatment_pair"
        )
        routing_finding = next(
            finding
            for finding in medical_report["findings"]
            if finding.get("finding_type") == "insurer_medical_routing_rule"
        )
        self.assertEqual(
            pair_finding["normalized_kcd_code"],
            "M54.5",
        )
        self.assertEqual(
            routing_finding["matched_rules"][0]["reason_code"],
            "DIAGNOSIS_TREATMENT_COMPATIBLE",
        )

    def test_review_service_calls_remote_fraud_check_integration(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        with tempfile.TemporaryDirectory() as temp_dir:
            with FraudCheckTestServer(synthetic_like_fraud_response) as server:
                with patch.dict(
                    "os.environ",
                    {
                        "FRAUD_CHECK_URL": server.url,
                        "CLAIM_MVP_PLUGIN_CONFIG": str(MVP_ROOT / "config" / "plugins.remote.yaml"),
                    },
                ):
                    repo = _repo(Path(temp_dir))
                    runtime = TemplateRuntime.build(Settings.load())
                    output = ReviewService(repository=repo, runtime=runtime).run_review(
                        claim_payload=claim,
                    )["output"]

                requests = list(server.requests)

        self.assertEqual(output["recommended_decision"], "partial_pay")
        self.assertEqual(requests[0]["path"], "/v1/fraud/check")
        self.assertIn("claim", requests[0]["payload"])
        self.assertIn("claim_history", requests[0]["payload"])
        self.assertIn("signals", requests[0]["payload"])
        self.assertIn("insured_profile", requests[0]["payload"])

    def test_review_service_calls_remote_fraud_check_v2_raw_evidence(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        with tempfile.TemporaryDirectory() as temp_dir:
            with FraudCheckTestServer(_v2_fraud_false_response) as server:
                with patch.dict(
                    "os.environ",
                    {
                        "FRAUD_CHECK_URL": server.url,
                        "CLAIM_MVP_PLUGIN_CONFIG": str(MVP_ROOT / "config" / "plugins.remote.v2.yaml"),
                    },
                ):
                    repo = _repo(Path(temp_dir))
                    runtime = TemplateRuntime.build(Settings.load())
                    output = ReviewService(repository=repo, runtime=runtime).run_review(
                        claim_payload=claim,
                    )["output"]
                requests = list(server.requests)

        self.assertEqual(output["recommended_decision"], "partial_pay")
        self.assertEqual(requests[0]["path"], "/v2/fraud/check")
        self.assertEqual(requests[0]["payload"]["schema_version"], "2.0.0")
        self.assertEqual(requests[0]["payload"]["source_system"], "automated_claims_processing_mvp")
        self.assertEqual(requests[0]["payload"]["analysis_mode"], "raw_evidence")
        self.assertEqual(requests[0]["payload"]["upstream_signals"], {})

    def test_review_service_v2_remote_failure_fail_closes_to_human_review(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                "os.environ",
                {
                    "FRAUD_CHECK_URL": unused_local_url(),
                    "FRAUD_CHECK_V2_TIMEOUT_MS": "100",
                    "CLAIM_MVP_PLUGIN_CONFIG": str(MVP_ROOT / "config" / "plugins.remote.v2.yaml"),
                },
            ):
                repo = _repo(Path(temp_dir))
                runtime = TemplateRuntime.build(Settings.load())
                output = ReviewService(repository=repo, runtime=runtime).run_review(
                    claim_payload=claim,
                )["output"]

        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertTrue(output["requires_human_review"])
        self.assertIn("TOOL_FAILURE", output["reason_codes"])

    def test_review_service_rejects_unknown_reviewer_action(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            runtime = TemplateRuntime.build(Settings.load())
            ClaimService(repository=repo, runtime=runtime).submit_claim(claim)
            service = ReviewService(repository=repo, runtime=runtime)
            with self.assertRaises(ValidationFailed):
                service.save_reviewer_action(claim["claim_id"], {"action": "approve"})

    def test_demo_preset_claims_match_expected_workflow_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            runtime = TemplateRuntime.build(Settings.load())
            service = ReviewService(repository=repo, runtime=runtime)
            scenarios = DemoScenarioService(
                settings=Settings.load(),
                runtime=runtime,
            ).list_scenarios()["scenarios"]
            outputs = {
                scenario["id"]: service.run_review(claim_payload=scenario["claim"])["output"]
                for scenario in scenarios
            }

        self.assertEqual(len(scenarios), 6)
        self.assertEqual(6, len({scenario["claim"]["product_id"] for scenario in scenarios}))
        self.assertEqual(6, len({scenario["claim"]["policy_id"] for scenario in scenarios}))
        for scenario in scenarios:
            output = outputs[scenario["id"]]
            self.assertEqual(
                output["recommended_decision"],
                scenario["expected_runtime_decision"],
                scenario["id"],
            )
            self.assertEqual(output["fraud_suspected"], scenario["expected_fraud_suspected"], scenario["id"])
            self.assertTrue(output.get("specialist_reports"), scenario["id"])
            if scenario["claim"]["product_id"] != "SYN-MED-001":
                self.assertIn("PRODUCT_ADJUDICATION_PROFILE_UNAVAILABLE", output["reason_codes"])
        request_documents_claim = next(
            scenario["claim"] for scenario in scenarios if scenario["id"] == "request_documents"
        )
        self.assertNotIn("diagnosis_note", request_documents_claim["documents"])
        self.assertTrue(outputs["human_review"]["requires_human_review"])
        self.assertTrue(outputs["fraud_signal"]["requires_human_review"])

    def test_fraud_demo_presets_use_fixed_runtime_claims_without_labels(self) -> None:
        runtime = TemplateRuntime.build(Settings.load())
        service = DemoScenarioService(settings=Settings.load(), runtime=runtime)
        presets = service.list_fraud_presets()["scenarios"]

        self.assertEqual(13, len(presets))
        self.assertEqual("CLM-EVAL-900002", service.get_fraud_preset("fraud_exact_duplicate")["claim"]["claim_id"])
        self.assertTrue(all(preset["preserve_claim_id"] for preset in presets))
        self.assertTrue(all(preset["category"] == "fraud_check" for preset in presets))
        for preset in presets:
            serialized_claim = str(preset["claim"])
            self.assertNotIn("fraud_reason_codes", serialized_claim)
            self.assertNotIn("expected_decision", serialized_claim)

    def test_ui_files_expose_customer_and_reviewer_surfaces(self) -> None:
        customer = (MVP_ROOT / "app" / "ui" / "customer_claim_screen.html").read_text(encoding="utf-8")
        reviewer = (MVP_ROOT / "app" / "ui" / "reviewer_assistant_screen.html").read_text(encoding="utf-8")
        demo = (MVP_ROOT / "app" / "ui" / "demo_scenario_builder.html").read_text(encoding="utf-8")
        self.assertIn('<html lang="ko">', customer)
        self.assertIn('<html lang="ko">', reviewer)
        self.assertIn('fetch("/claims"', customer)
        self.assertNotIn('data-preset="', customer)
        self.assertNotIn("expectedDecision", customer)
        self.assertIn('<option value="active">', customer)
        self.assertIn('<option value="outpatient">', customer)
        self.assertIn('<option value="covered">', customer)
        self.assertIn("insured_profile", customer)
        self.assertIn("receipt_hash", customer)
        self.assertIn("same_insured_provider_claims_30d", customer)
        self.assertIn('requestJson("/demo/scenarios"', demo)
        self.assertIn('requestJson("/demo/fraud-presets"', demo)
        self.assertIn('id="fraudPresetList"', demo)
        self.assertIn("preserve_claim_id", demo)
        self.assertIn("Demo Scenario Builder", demo)
        self.assertIn('data-mutation="duplicate_receipt"', demo)
        self.assertIn('requestJson("/reviews"', reviewer)
        self.assertIn('requestJson("/reviews/queue?limit=50&sla_hours=24"', reviewer)
        self.assertIn("audit-logs", reviewer)
        self.assertIn('id="claimSelect"', reviewer)
        self.assertIn("Submitted Claims", reviewer)
        self.assertIn('claimSelect").addEventListener("change"', reviewer)
        self.assertIn('requestJson("/claims?limit=50"', reviewer)
        self.assertIn("policyBasis", reviewer)
        self.assertIn("citation_id", reviewer)
        self.assertIn("Deterministic Confidence", reviewer)
        self.assertIn("evidenceClarity", reviewer)
        self.assertIn("judgmentDifficulty", reviewer)
        self.assertIn("uncertaintyExplanation", reviewer)
        self.assertIn("confidence_assessment", reviewer)
        self.assertIn("Explanation Confidence", reviewer)
        self.assertIn("explanationScore", reviewer)
        self.assertIn("faithfulnessToTools", reviewer)
        self.assertIn("citationAlignment", reviewer)
        self.assertIn("calculationAlignment", reviewer)
        self.assertIn("unsupportedClaims", reviewer)
        self.assertIn("explanation_confidence", reviewer)
        self.assertIn('id="reviewLoading"', reviewer)
        self.assertIn("class=\"spinner\"", reviewer)
        self.assertIn("function resetReviewPanels", reviewer)
        self.assertIn('resetReviewPanels("Not Run")', reviewer)
        self.assertIn("function setReviewLoading", reviewer)
        self.assertIn("setReviewLoading(true)", reviewer)
        self.assertIn('resetReviewPanels("Review Failed")', reviewer)
        self.assertIn("Agent Reports", reviewer)
        self.assertIn('id="specialistReports"', reviewer)
        self.assertIn("function renderSpecialistReports", reviewer)
        self.assertIn("function renderDocumentExtractionFinding", reviewer)
        self.assertIn("function loadPersistedSpecialistReports", reviewer)
        self.assertIn('specialist-reports', reviewer)
        self.assertIn("Field statuses", reviewer)
        self.assertIn("specialist_reports", reviewer)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_fastapi_routes_when_dependency_available(self) -> None:
        from mvp.app.main import create_app

        app = create_app(settings=Settings.load())
        route_paths = {route.path for route in app.routes}
        self.assertTrue(
            {
                "/claims",
                "/claims/{claim_id}",
                "/reviews",
                "/reviews/queue",
                "/reviews/{claim_id}",
                "/reviews/{claim_id}/actions",
                "/reviews/{claim_id}/audit-logs",
                "/demo/scenarios",
                "/demo/scenarios/{scenario_id}",
                "/demo/fraud-presets",
                "/demo/fraud-presets/{preset_id}",
                "/products",
                "/products/{product_id}",
                "/products/{product_id}/policies",
                "/ui/customer",
                "/ui/reviewer",
                "/ui/demo",
                "/internal/v1/fraud-context/claims/{claim_id}",
                "/internal/v1/claims/{claim_id}/documents",
                "/internal/v1/documents/{document_id}/content",
            }
            <= route_paths
        )


def _repo(temp_dir: Path, db_path: Path | None = None) -> SQLiteRepository:
    return SQLiteRepository(
        db_path=db_path or temp_dir / "mvp.sqlite3",
        schema_path=MVP_ROOT / "app" / "db" / "schema.sql",
        migrations_dir=MVP_ROOT / "app" / "db" / "migrations",
    )


def _table_counts(db_path: Path, table_names: list[str]) -> dict[str, int]:
    with closing(sqlite3.connect(db_path)) as connection:
        return {
            table_name: connection.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            for table_name in table_names
        }


def _read_first_jsonl(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.loads(next(line for line in file if line.strip()))


def _read_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _legacy_claim(claim: dict) -> dict:
    claim = json.loads(json.dumps(claim))
    claim.pop("insured_profile", None)
    claim["claim"].pop("receipt_hash", None)
    claim["claim"].pop("provider_id", None)
    claim["claim_history"].pop("same_insured_provider_claims_30d", None)
    claim["claim_history"].pop("same_provider_claims_30d", None)
    claim["claim_history"].pop("prior_receipt_hashes", None)
    return claim


def _v2_fraud_false_response(payload: dict, headers: dict) -> tuple[int, dict]:
    return (
        200,
        {
            "schema_version": "2.0.0",
            "request_id": payload["request_id"],
            "claim_id": payload["claim_id"],
            "status": "success",
            "fraud_suspected": False,
            "fraud_reason_codes": [],
            "risk_score": 5,
            "routing": "continue_claim_review",
            "requires_human_review": False,
            "engine_version": "test-fraud-check-2.0.0",
            "workflow_version": "test-workflow-2.0.0",
            "document_findings": [],
            "history_findings": [],
            "evidence": [],
            "analysis_warnings": [],
            "tool_failures": [],
        },
    )


if __name__ == "__main__":
    unittest.main()
