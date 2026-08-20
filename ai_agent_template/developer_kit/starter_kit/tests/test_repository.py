import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from ai_agent_template.developer_kit.starter_kit.app.db.repository import ClaimReviewRepository
from ai_agent_template.developer_kit.starter_kit.app.db.sqlite import SQLiteRepository


WORKSPACE = Path(__file__).resolve().parents[4]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"


class SQLiteRepositoryTest(unittest.TestCase):
    def test_repository_satisfies_protocol_shape(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _repository(temp_dir)
            self.assertIsInstance(repository, SQLiteRepository)
            self.assertTrue(hasattr(repository, "save_claim"))
            self.assertTrue(hasattr(repository, "list_review_queue"))
            self.assertTrue(hasattr(repository, "save_tool_call_log"))
            self.assertTrue(hasattr(repository, "save_audit_log"))

    def test_migration_runner_applies_migrations_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _repository(temp_dir)
            self.assertEqual(
                repository.applied_migrations(),
                [
                    "001_initial",
                    "002_operational_parity",
                    "003_fraud_context_documents",
                    "004_medical_registry_specialist_agents",
                    "005_medical_routing_rules",
                    "006_customer_document_uploads",
                ],
            )
            repository.initialize()
            self.assertEqual(
                repository.applied_migrations(),
                [
                    "001_initial",
                    "002_operational_parity",
                    "003_fraud_context_documents",
                    "004_medical_registry_specialist_agents",
                    "005_medical_routing_rules",
                    "006_customer_document_uploads",
                ],
            )

    def test_foreign_key_rejects_agent_output_without_claim(self) -> None:
        output = _read_json(TEMPLATE_ROOT / "examples" / "reviewer_assistant_output.example.json")
        output["claim_id"] = "NON_EXISTENT_CLAIM"
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _repository(temp_dir)
            with self.assertRaises(sqlite3.IntegrityError):
                repository.save_agent_output(output)

    def test_repository_persists_claim_output_logs_actions_and_eval(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        output = _read_json(TEMPLATE_ROOT / "examples" / "reviewer_assistant_output.example.json")
        output["claim_id"] = claim["claim_id"]
        with tempfile.TemporaryDirectory() as temp_dir:
            repository: ClaimReviewRepository = _repository(temp_dir)
            repository.save_claim(claim)
            repository.save_agent_output(output)
            repository.save_specialist_agent_reports(claim["claim_id"], output.get("specialist_reports", []))
            repository.save_tool_call_log(
                claim_id=claim["claim_id"],
                tool_name="policy_search",
                tool_version="1.0.0",
                request={"query": "coverage"},
                response={"matches": []},
                status="success",
                duration_ms=1,
            )
            repository.save_reviewer_action(
                claim_id=claim["claim_id"],
                action_type="add_reviewer_note",
                reviewer_note="repository boundary smoke test",
            )
            repository.save_retrieval_log(
                claim_id=claim["claim_id"],
                query="outpatient noncovered",
                result={"matches": [{"citation_id": "SYN-MED-001-2.2-A"}]},
            )
            repository.save_audit_log(
                event_type="repository_test",
                claim_id=claim["claim_id"],
                entity_type="claim",
                entity_id=claim["claim_id"],
                metadata={"ok": True},
            )
            repository.save_evaluation_run(
                run_id="eval-repository-test",
                dataset_name="synthetic",
                claims_path="claims.jsonl",
                labels_path="labels.jsonl",
                output_path="outputs.jsonl",
                metrics={"schema_validity": 1.0},
                passed=True,
            )

            self.assertEqual(repository.get_claim(claim["claim_id"])["claim_id"], claim["claim_id"])
            self.assertEqual(repository.get_latest_output(claim["claim_id"])["claim_id"], claim["claim_id"])
            self.assertEqual(
                repository.list_specialist_agent_reports(claim["claim_id"]),
                output.get("specialist_reports", []),
            )
            self.assertEqual(repository.list_reviewer_actions(claim["claim_id"])[0]["action"], "defer")
            self.assertEqual(repository.list_review_queue(limit=10)[0]["claim_id"], claim["claim_id"])
            self.assertEqual(repository.get_evaluation_run("eval-repository-test")["passed"], True)
            self.assertEqual(repository.list_audit_logs(claim_id=claim["claim_id"])[0]["event_type"], "repository_test")
            counts = _table_counts(Path(temp_dir) / "repo.sqlite3")

        self.assertEqual(counts["claim_reviews"], 1)
        self.assertEqual(counts["agent_outputs"], 1)
        self.assertEqual(counts["specialist_agent_reports"], len(output.get("specialist_reports", [])))
        self.assertEqual(counts["tool_call_logs"], 1)
        self.assertEqual(counts["reviewer_actions"], 1)
        self.assertEqual(counts["retrieval_logs"], 1)
        self.assertEqual(counts["audit_logs"], 1)
        self.assertEqual(counts["evaluation_runs"], 1)

    def test_tool_and_audit_logs_redact_secrets_and_direct_identifiers(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _repository(temp_dir)
            claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
            claim = json.loads(json.dumps(claim))
            claim["claim_id"] = "CLAIM-LOG-001"
            repository.save_claim(claim)
            repository.save_tool_call_log(
                claim_id="CLAIM-LOG-001",
                tool_name="fraud_signal_checker",
                tool_version="1.0.0",
                request={"insured_id": "INS-SYN-SECRET", "authorization": "Bearer secret"},
                response={"api_key": "secret", "fraud_suspected": False},
                status="success",
            )
            repository.save_audit_log(
                event_type="security_test",
                entity_type="claim",
                metadata={"insured_id": "INS-SYN-SECRET", "api_key": "secret"},
            )
            with closing(sqlite3.connect(Path(temp_dir) / "repo.sqlite3")) as connection:
                request_json, response_json = connection.execute(
                    "SELECT request_json, response_json FROM tool_call_logs LIMIT 1"
                ).fetchone()
                metadata_json = connection.execute(
                    "SELECT metadata_json FROM audit_logs LIMIT 1"
                ).fetchone()[0]
        serialized = request_json + response_json + metadata_json
        self.assertNotIn("INS-SYN-SECRET", serialized)
        self.assertNotIn("Bearer secret", serialized)
        self.assertNotIn('"api_key": "secret"', serialized)
        self.assertIn("tok_", serialized)

    def test_medical_registry_seed_is_idempotent_and_queryable(self) -> None:
        generated = WORKSPACE / "data_generator" / "generated"
        medical_codes = _read_json(generated / "medical_code_registry.json")
        edi_codes = _read_json(generated / "edi_code_registry.json")
        rules = _read_json(generated / "diagnosis_treatment_rules.json")
        routing_rules = _read_json(generated / "insurer_medical_routing_rules.json")
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _repository(temp_dir)
            first = repository.seed_medical_registry(
                medical_code_registry=medical_codes,
                edi_code_registry=edi_codes,
                diagnosis_treatment_rules=rules,
                insurer_medical_routing_rules=routing_rules,
                source_files=[
                    "medical_code_registry.json",
                    "edi_code_registry.json",
                    "diagnosis_treatment_rules.json",
                    "insurer_medical_routing_rules.json",
                ],
            )
            second = repository.seed_medical_registry(
                medical_code_registry=medical_codes,
                edi_code_registry=edi_codes,
                diagnosis_treatment_rules=rules,
                insurer_medical_routing_rules=routing_rules,
                source_files=[
                    "medical_code_registry.json",
                    "edi_code_registry.json",
                    "diagnosis_treatment_rules.json",
                    "insurer_medical_routing_rules.json",
                ],
            )
            self.assertEqual(first["row_count"], second["row_count"])
            self.assertEqual(repository.get_medical_code("SYN-M54")["code"], "M54.5")
            self.assertEqual(repository.get_procedure_code("TRT-NONCOV-001")["code"], "EDI-MM010")
            self.assertEqual(
                repository.find_diagnosis_treatment_rule("M54.5", "EDI-MM010")["relationship"],
                "compatible",
            )
            self.assertEqual(
                repository.get_medical_routing_rule("SYN-MED-ROUTE-AMBIGUOUS-CODE")["routing"],
                "human_review",
            )
            self.assertEqual(
                repository.find_medical_routing_rule(
                    reason_code="DIAGNOSIS_TREATMENT_COMPATIBLE",
                    routing="continue_claim_review",
                )["rule_id"],
                "SYN-MED-ROUTE-CONTINUE",
            )
            counts = _table_counts(Path(temp_dir) / "repo.sqlite3")
        self.assertEqual(counts["medical_code_registry"], len(medical_codes))
        self.assertEqual(counts["procedure_code_registry"], len(edi_codes))
        self.assertEqual(counts["diagnosis_treatment_rules"], len(rules))
        self.assertEqual(counts["medical_routing_rules"], len(routing_rules))


def _repository(temp_dir: str) -> SQLiteRepository:
    return SQLiteRepository(
        db_path=Path(temp_dir) / "repo.sqlite3",
        schema_path=TEMPLATE_ROOT / "db" / "schema.sql",
        migrations_dir=TEMPLATE_ROOT / "db" / "migrations",
    )


def _table_counts(db_path: Path) -> dict[str, int]:
    tables = [
        "claim_reviews",
        "agent_outputs",
        "tool_call_logs",
        "reviewer_actions",
        "retrieval_logs",
            "audit_logs",
            "evaluation_runs",
            "specialist_agent_reports",
            "fraud_current_claims",
            "historical_claims",
            "document_metadata",
            "claim_documents",
            "medical_code_registry",
            "procedure_code_registry",
            "diagnosis_treatment_rules",
            "medical_routing_rules",
        ]
    with closing(sqlite3.connect(db_path)) as connection:
        return {
            table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table in tables
        }


def _read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_first_jsonl(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.loads(next(line for line in file if line.strip()))


if __name__ == "__main__":
    unittest.main()
