import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ai_agent_template.developer_kit.starter_kit.app.core.evaluation_service import EvaluationService
from ai_agent_template.developer_kit.starter_kit.app.core.review_service import ReviewService
from ai_agent_template.developer_kit.starter_kit.app.core.settings import Settings


WORKSPACE = Path(__file__).resolve().parents[4]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"


class StarterKitSmokeTest(unittest.TestCase):
    def test_starter_kit_imports_from_its_own_directory(self) -> None:
        starter_root = TEMPLATE_ROOT / "developer_kit" / "starter_kit"
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "from app.core.review_service import ReviewService; print('ok')",
            ],
            cwd=starter_root,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("ok", result.stdout)

    def test_review_service_persists_claim_and_review(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                template_root=TEMPLATE_ROOT,
                sqlite_path=Path(temp_dir) / "starter.sqlite3",
                reports_dir=Path(temp_dir) / "reports",
            )
            service = ReviewService(settings)
            receipt = service.submit_claim(claim)
            output = service.run_review(claim_id=receipt["claim_id"])
            stored = service.get_review(receipt["claim_id"])
        self.assertEqual(receipt["status"], "received")
        self.assertEqual(output["claim_id"], claim["claim_id"])
        self.assertEqual(stored["claim_id"], claim["claim_id"])

    def test_evaluation_service_runs_small_dataset(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                template_root=TEMPLATE_ROOT,
                sqlite_path=Path(temp_dir) / "starter.sqlite3",
                reports_dir=Path(temp_dir) / "reports",
            )
            result = EvaluationService(ReviewService(settings)).run_evaluation(
                claims_path=WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl",
                labels_path=WORKSPACE / "data_generator" / "generated" / "labels_eval.jsonl",
                max_rows=3,
            )
        self.assertEqual(result["dataset_size"], 3)
        self.assertEqual(result["metrics"]["schema_validity"], 1.0)

    def test_evaluation_service_matches_labels_by_claim_id(self) -> None:
        claims = _read_jsonl(
            WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl",
            indexes=[9, 17],
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            claims_path = Path(temp_dir) / "claims_subset.jsonl"
            _write_jsonl(claims_path, claims)
            settings = Settings(
                template_root=TEMPLATE_ROOT,
                sqlite_path=Path(temp_dir) / "starter.sqlite3",
                reports_dir=Path(temp_dir) / "reports",
            )
            result = EvaluationService(ReviewService(settings)).run_evaluation(
                claims_path=claims_path,
                labels_path=WORKSPACE / "data_generator" / "generated" / "labels_eval.jsonl",
            )
        self.assertEqual(result["dataset_size"], 2)
        self.assertEqual(result["metrics"]["schema_validity"], 1.0)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_fastapi_app_factory_when_dependency_available(self) -> None:
        from ai_agent_template.developer_kit.starter_kit.app.main import create_app

        app = create_app()
        self.assertEqual(app.title, "Claim Review Agent Starter Kit")


def _read_first_jsonl(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.loads(next(line for line in file if line.strip()))


def _read_jsonl(path: Path, indexes: list[int]) -> list[dict]:
    wanted = set(indexes)
    rows = []
    with path.open("r", encoding="utf-8") as file:
        for index, line in enumerate(file):
            if index in wanted and line.strip():
                rows.append(json.loads(line))
    return rows


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    unittest.main()
