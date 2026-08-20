import copy
import importlib.util
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import StandardsRegistry

from mvp.app.core.evaluation_service import EvaluationService
from mvp.app.core.errors import ValidationFailed
from mvp.app.core.review_service import ReviewService
from mvp.app.core.settings import Settings
from mvp.app.core.template_runtime import TemplateRuntime
from mvp.app.db.sqlite import SQLiteRepository
from test_support.fraud_check_server import unused_local_url


WORKSPACE = Path(__file__).resolve().parents[2]
MVP_ROOT = WORKSPACE / "mvp"
CLAIMS_EVAL = WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl"
LABELS_EVAL = WORKSPACE / "data_generator" / "generated" / "labels_eval.jsonl"


class EvaluationSafetyStage3Test(unittest.TestCase):
    def test_evaluation_service_runs_dataset_and_persists_sanitized_result(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            repo = _repo(Path(temp_dir), settings.sqlite_path)
            runtime = TemplateRuntime.build(settings)
            result = EvaluationService(
                repository=repo,
                runtime=runtime,
                settings=settings,
            ).run_evaluation({"max_rows": 3, "dataset_name": "unit-stage3"})
            stored = repo.get_evaluation_run(result["run_id"])
            output_rows = _read_jsonl(Path(result["outputs_path"]))

        self.assertEqual(result["dataset_size"], 3)
        self.assertEqual(result["metrics"]["schema_validity"], 1.0)
        self.assertTrue(result["labels_path_redacted"])
        self.assertIn("decision_accuracy", result["metrics"])
        self.assertIn("false_payment_rate", result["metrics"])
        self.assertIn("document_field_label_accuracy", result["metrics"])
        self.assertIn("kcd_mapping_accuracy", result["metrics"])
        self.assertIn("edi_mapping_accuracy", result["metrics"])
        self.assertIn("medical_causality_routing_accuracy", result["metrics"])
        self.assertIn("citation_requirement_pass_rate", result["metrics"])
        self.assertEqual(stored["run_id"], result["run_id"])
        self.assertNotIn("labels_path", result)
        self.assertTrue(output_rows)
        for row in output_rows:
            self.assertNotIn("expected_decision", row)
            self.assertNotIn("expected_payable_amount", row)

    def test_evaluation_service_rejects_claim_rows_with_label_leakage(self) -> None:
        claim = _read_first_jsonl(CLAIMS_EVAL)
        claim["expected_decision"] = "pay"
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir) / "claims_with_label.jsonl"
            _write_jsonl(temp_path, [claim])
            settings = _settings(Path(temp_dir))
            repo = _repo(Path(temp_dir), settings.sqlite_path)
            runtime = TemplateRuntime.build(settings)
            service = EvaluationService(repository=repo, runtime=runtime, settings=settings)
            with self.assertRaises(ValidationFailed) as context:
                service.run_evaluation(
                    {
                        "claims_path": str(temp_path),
                        "labels_path": str(LABELS_EVAL),
                        "max_rows": 1,
                    }
                )

        self.assertIn("expected_decision", " ".join(context.exception.details))

    def test_human_review_fallback_for_fraud_signal(self) -> None:
        claim = copy.deepcopy(_read_first_jsonl(CLAIMS_EVAL))
        claim["claim_id"] = "MVP-FRAUD-FALLBACK-001"
        claim["signals"]["suspected_duplicate_receipt"] = True
        claim["claim_history"]["prior_receipt_hashes"] = [claim["claim"]["receipt_hash"]]
        claim["claim_history"]["prior_receipt_ids"] = [claim["claim"]["receipt_id"]]
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            repo = _repo(Path(temp_dir), settings.sqlite_path)
            runtime = TemplateRuntime.build(settings)
            output = ReviewService(repository=repo, runtime=runtime).run_review(
                claim_payload=claim,
            )["output"]

        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertTrue(output["requires_human_review"])
        self.assertTrue(output["fraud_suspected"])
        self.assertIn("DUPLICATE_RECEIPT_SUSPECTED", output["reason_codes"])

    def test_remote_fraud_check_down_fail_closes_to_human_review(self) -> None:
        claim = copy.deepcopy(_read_first_jsonl(CLAIMS_EVAL))
        claim["claim_id"] = "MVP-FRAUD-CHECK-DOWN-001"
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch.dict(
                "os.environ",
                {
                    "FRAUD_CHECK_URL": unused_local_url(),
                    "CLAIM_MVP_PLUGIN_CONFIG": str(MVP_ROOT / "config" / "plugins.remote.yaml"),
                },
            ):
                settings = _settings(Path(temp_dir))
                repo = _repo(Path(temp_dir), settings.sqlite_path)
                runtime = TemplateRuntime.build(settings)
                output = ReviewService(repository=repo, runtime=runtime).run_review(
                    claim_payload=claim,
                )["output"]

        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertTrue(output["requires_human_review"])
        self.assertFalse(output["fraud_suspected"])
        self.assertIn("TOOL_FAILURE", output["reason_codes"])

    def test_medical_registry_failure_fail_closes_to_human_review(self) -> None:
        claim = copy.deepcopy(_read_first_jsonl(CLAIMS_EVAL))
        claim["claim_id"] = "MVP-REGISTRY-FAIL-CLOSED-001"
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            repo = _repo(Path(temp_dir), settings.sqlite_path)
            runtime = TemplateRuntime.build(settings)
            with patch(
                "mvp.app.core.review_service.RuntimeMedicalRegistryService.enrich_claim_payload",
                side_effect=RuntimeError("registry unavailable"),
            ):
                output = ReviewService(repository=repo, runtime=runtime).run_review(
                    claim_payload=claim,
                )["output"]
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertTrue(output["requires_human_review"])
        self.assertIn("TOOL_FAILURE", output["reason_codes"])

    def test_retrieval_fallback_without_keyword_retriever_still_returns_policy_basis(self) -> None:
        claim = copy.deepcopy(_read_first_jsonl(CLAIMS_EVAL))
        claim["claim_id"] = "MVP-RETRIEVAL-FALLBACK-001"
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir), retrieval_enabled=False)
            repo = _repo(Path(temp_dir), settings.sqlite_path)
            runtime = TemplateRuntime.build(settings)
            result = ReviewService(repository=repo, runtime=runtime).run_review(claim_payload=claim)
            output = result["output"]
            counts = _table_counts(settings.sqlite_path, ["tool_call_logs", "retrieval_logs"])

        self.assertEqual(runtime.policy_knowledge.readiness()["retriever_available"], False)
        self.assertTrue(output["policy_basis"])
        self.assertFalse(any("citation_id" in item for item in output["policy_basis"]))
        self.assertEqual(counts["tool_call_logs"], 8)
        self.assertEqual(counts["retrieval_logs"], 1)

    def test_standards_registry_exposes_required_code_sets(self) -> None:
        runtime = TemplateRuntime.build(Settings.load())
        registry = StandardsRegistry(runtime.template)
        self.assertIn("human_review", registry.list_decision_codes())
        self.assertIn("COV_OUTPATIENT_COVERED", registry.list_coverage_codes())
        self.assertTrue(registry.list_document_codes())
        self.assertIn("HUMAN_REVIEW_REQUIRED", registry.list_reason_codes())

    def test_ui_files_expose_stage3_api_surfaces(self) -> None:
        customer = (MVP_ROOT / "app" / "ui" / "customer_claim_screen.html").read_text(encoding="utf-8")
        reviewer = (MVP_ROOT / "app" / "ui" / "reviewer_assistant_screen.html").read_text(encoding="utf-8")
        self.assertIn('fetch("/claims"', customer)
        self.assertIn('requestJson("/reviews"', reviewer)
        self.assertIn('requestJson("/evaluations/runs"', reviewer)
        self.assertIn('requestJson("/reviews/queue?limit=50&sla_hours=24"', reviewer)
        self.assertIn('requestJson("/standards"', reviewer)
        self.assertIn('requestJson("/configs/model"', reviewer)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_fastapi_stage3_routes_when_dependency_available(self) -> None:
        from mvp.app.main import create_app

        with tempfile.TemporaryDirectory() as temp_dir:
            settings = _settings(Path(temp_dir))
            app = create_app(settings=settings)
        route_paths = {route.path for route in app.routes}
        self.assertTrue(
            {
                "/evaluations/runs",
                "/evaluations/runs/{run_id}",
                "/reviews/queue",
                "/reviews/{claim_id}/actions",
                "/reviews/{claim_id}/audit-logs",
                "/standards",
                "/standards/decision-codes",
                "/standards/coverage-codes",
                "/standards/document-codes",
                "/standards/reason-codes",
                "/configs",
                "/configs/model",
                "/configs/runtime",
            }
            <= route_paths
        )


def _settings(temp_dir: Path, *, retrieval_enabled: bool = True) -> Settings:
    return replace(
        Settings.load(),
        sqlite_path=temp_dir / "mvp.sqlite3",
        reports_dir=temp_dir / "reports",
        retrieval_enabled=retrieval_enabled,
    )


def _repo(temp_dir: Path, db_path: Path) -> SQLiteRepository:
    return SQLiteRepository(
        db_path=db_path,
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


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    unittest.main()
