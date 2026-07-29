import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from mvp.app.core.claim_service import ClaimService
from mvp.app.core.demo_scenario_service import DemoScenarioService
from mvp.app.core.errors import ValidationFailed
from mvp.app.core.review_service import ReviewService
from mvp.app.core.settings import Settings
from mvp.app.core.template_runtime import TemplateRuntime
from mvp.app.db.sqlite import SQLiteRepository


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
            counts = _table_counts(
                db_path,
                ["reviews", "tool_call_logs", "retrieval_logs", "reviewer_actions", "audit_logs"],
            )

        self.assertEqual(result["review_status"], "completed")
        self.assertEqual(stored["claim_id"], claim["claim_id"])
        self.assertEqual(counts["reviews"], 1)
        self.assertEqual(counts["tool_call_logs"], 8)
        self.assertEqual(counts["retrieval_logs"], 1)
        self.assertEqual(counts["reviewer_actions"], 1)
        self.assertGreaterEqual(counts["audit_logs"], 4)
        self.assertEqual(queue[0]["claim_id"], claim["claim_id"])
        self.assertIn("policy_id_masked", queue[0])
        self.assertNotIn("policy_id", queue[0])
        self.assertEqual(actions[0]["action"], "accept_recommendation")
        self.assertEqual(audit_logs[0]["event_type"], "reviewer_action_saved")
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
        for scenario in scenarios:
            output = outputs[scenario["id"]]
            self.assertEqual(output["recommended_decision"], scenario["expected_decision"], scenario["id"])
            self.assertEqual(output["fraud_suspected"], scenario["expected_fraud_suspected"], scenario["id"])
        self.assertTrue(outputs["request_documents"]["missing_documents"])
        self.assertTrue(outputs["human_review"]["requires_human_review"])
        self.assertTrue(outputs["fraud_signal"]["requires_human_review"])

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
                "/ui/customer",
                "/ui/reviewer",
                "/ui/demo",
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


def _legacy_claim(claim: dict) -> dict:
    claim = json.loads(json.dumps(claim))
    claim.pop("insured_profile", None)
    claim["claim"].pop("receipt_hash", None)
    claim["claim"].pop("provider_id", None)
    claim["claim_history"].pop("same_insured_provider_claims_30d", None)
    claim["claim_history"].pop("same_provider_claims_30d", None)
    claim["claim_history"].pop("prior_receipt_hashes", None)
    return claim


if __name__ == "__main__":
    unittest.main()
