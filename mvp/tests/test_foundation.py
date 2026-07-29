import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import SchemaValidator

from mvp.app.core.policy_knowledge_service import PolicyKnowledgeService
from mvp.app.core.errors import ValidationFailed
from mvp.app.core.settings import Settings
from mvp.app.core.template_runtime import TemplateRuntime
from mvp.app.api.errors import raise_http_error
from mvp.app.db.sqlite import SQLiteRepository


WORKSPACE = Path(__file__).resolve().parents[2]
MVP_ROOT = WORKSPACE / "mvp"


class MvpFoundationTest(unittest.TestCase):
    def test_settings_loads_default_config_and_paths(self) -> None:
        settings = Settings.load()
        self.assertEqual(settings.app_name, "insurance-claims-review-mvp")
        self.assertTrue(settings.template_root.exists())
        self.assertTrue(settings.plugin_config_path.exists())
        self.assertTrue(settings.model_config_path.exists())
        self.assertTrue(settings.demo_scenarios_path.exists())
        self.assertEqual(settings.retrieval_mode, "keyword")
        self.assertEqual(settings.retrieval_top_k, 3)

    def test_settings_environment_overrides_runtime_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            override = Path(temp_dir) / "override.sqlite3"
            with patch.dict("os.environ", {"CLAIM_MVP_SQLITE_PATH": str(override)}):
                settings = Settings.load()
        self.assertEqual(settings.sqlite_path, override.resolve())

    def test_template_runtime_loads_plugins_model_and_retriever(self) -> None:
        runtime = TemplateRuntime.build(Settings.load())
        readiness = runtime.readiness()
        self.assertEqual(
            readiness["registered_tools"],
            [
                "coverage_resolver",
                "decision_validator",
                "document_checker",
                "exclusion_checker",
                "fraud_signal_checker",
                "payable_calculator",
                "policy_search",
                "risk_checker",
            ],
        )
        self.assertEqual(readiness["model_provider"], "general_llm")
        self.assertEqual(readiness["model_id"], "gemma-4-26B-4aB-it")
        self.assertTrue(readiness["policy_knowledge"]["retriever_available"])

    def test_policy_knowledge_retrieval_result_matches_template_schema(self) -> None:
        runtime = TemplateRuntime.build(Settings.load())
        service = PolicyKnowledgeService(runtime.template, runtime.settings)
        result = service.retrieve(
            "outpatient noncovered deductible limit",
            product_id="SYN-MED-001",
        )
        self.assertIsNotNone(result)
        SchemaValidator(runtime.template).validate_retrieval_result(result)
        self.assertTrue(result["matches"])
        self.assertIn("citation_id", result["matches"][0])

    def test_api_error_conversion_emits_structured_log(self) -> None:
        error = ValidationFailed("invalid claim", ["claim_id is required"])
        with self.assertLogs("mvp.api.errors", level="WARNING") as logs:
            with self.assertRaises(Exception):
                raise_http_error(error)
        self.assertIn("MVP API error converted to HTTP response", logs.output[0])

    def test_sqlite_repository_migration_and_basic_persistence(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        with tempfile.TemporaryDirectory() as temp_dir:
            repo = _repo(Path(temp_dir))
            self.assertEqual(repo.applied_migrations(), ["001_initial", "002_audit_logs"])
            repo.initialize()
            self.assertEqual(repo.applied_migrations(), ["001_initial", "002_audit_logs"])
            repo.save_claim(claim)
            self.assertEqual(repo.get_claim(claim["claim_id"])["claim_id"], claim["claim_id"])
            claim_summaries = repo.list_claims(limit=10)
            self.assertEqual(claim_summaries[0]["claim_id"], claim["claim_id"])
            self.assertEqual(claim_summaries[0]["status"], "received")
            queue = repo.list_review_queue(limit=10, sla_hours=24)
            self.assertEqual(queue[0]["claim_id"], claim["claim_id"])
            self.assertIn("sla_status", queue[0])
            repo.save_retrieval_log(
                claim_id=claim["claim_id"],
                query="outpatient noncovered",
                result={"matches": [{"citation_id": "products.json#COVERAGE-002"}]},
            )
            repo.save_reviewer_action(
                claim_id=claim["claim_id"],
                action="accept_recommendation",
                reviewer_id="reviewer-001",
                reviewer_note="accepted",
            )
            actions = repo.list_reviewer_actions(claim["claim_id"])
            self.assertEqual(actions[0]["action"], "accept_recommendation")
            repo.save_audit_log(
                event_type="repository_smoke",
                claim_id=claim["claim_id"],
                entity_type="claim",
                entity_id=claim["claim_id"],
                metadata={"ok": True},
            )
            audit_logs = repo.list_audit_logs(claim_id=claim["claim_id"])
            self.assertEqual(audit_logs[0]["event_type"], "repository_smoke")
            self.assertTrue(audit_logs[0]["metadata"]["ok"])
            repo.save_evaluation_run(
                run_id="eval-repository-smoke",
                dataset_name="synthetic",
                claims_path="claims.jsonl",
                labels_path="labels.jsonl",
                output_path="outputs.jsonl",
                metrics={"schema_validity": 1.0},
                passed=True,
            )
            stored_eval = repo.get_evaluation_run("eval-repository-smoke")
            self.assertEqual(stored_eval["metrics"]["schema_validity"], 1.0)
            self.assertTrue(stored_eval["passed"])

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_fastapi_app_factory_when_dependency_available(self) -> None:
        from mvp.app.main import create_app

        app = create_app(settings=Settings.load())
        self.assertEqual(app.title, "Insurance Claims Review MVP")


def _repo(temp_dir: Path) -> SQLiteRepository:
    return SQLiteRepository(
        db_path=temp_dir / "mvp.sqlite3",
        schema_path=MVP_ROOT / "app" / "db" / "schema.sql",
        migrations_dir=MVP_ROOT / "app" / "db" / "migrations",
    )


def _read_first_jsonl(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.loads(next(line for line in file if line.strip()))


if __name__ == "__main__":
    unittest.main()
