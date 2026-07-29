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
            self.assertTrue(hasattr(repository, "save_tool_call_log"))

    def test_migration_runner_applies_initial_migration_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            repository = _repository(temp_dir)
            self.assertEqual(repository.applied_migrations(), ["001_initial"])
            repository.initialize()
            self.assertEqual(repository.applied_migrations(), ["001_initial"])

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
            counts = _table_counts(Path(temp_dir) / "repo.sqlite3")

        self.assertEqual(counts["claim_reviews"], 1)
        self.assertEqual(counts["agent_outputs"], 1)
        self.assertEqual(counts["tool_call_logs"], 1)
        self.assertEqual(counts["reviewer_actions"], 1)
        self.assertEqual(counts["evaluation_runs"], 1)


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
        "evaluation_runs",
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
