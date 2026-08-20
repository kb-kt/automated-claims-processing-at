import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
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
                specialist_config_path=(
                    TEMPLATE_ROOT
                    / "developer_kit"
                    / "starter_kit"
                    / "config"
                    / "specialist_plugins.synthetic_insurer.yaml"
                ),
            )
            service = ReviewService(settings)
            receipt = service.submit_claim(claim)
            output = service.run_review(claim_id=receipt["claim_id"])
            stored = service.get_review(receipt["claim_id"])
            queue = service.list_review_queue(limit=10)
            action = service.save_reviewer_action(
                receipt["claim_id"],
                {
                    "action": "accept_recommendation",
                    "reviewer_id": "smoke-reviewer",
                    "reviewer_note": "accepted in smoke test",
                },
            )
            actions = service.list_reviewer_actions(receipt["claim_id"])
            audit_logs = service.list_audit_logs(claim_id=receipt["claim_id"])
        self.assertEqual(receipt["status"], "received")
        self.assertEqual(output["claim_id"], claim["claim_id"])
        self.assertIn("confidence_assessment", output)
        self.assertIn("explanation_confidence", output)
        self.assertEqual(stored["claim_id"], claim["claim_id"])
        self.assertEqual(queue["queue"][0]["claim_id"], claim["claim_id"])
        self.assertEqual(action["status"], "stored")
        self.assertEqual(actions["actions"][0]["action"], "accept_recommendation")
        self.assertTrue(any(item["event_type"] == "review_completed" for item in audit_logs["audit_logs"]))
        completed_audit = next(
            item for item in audit_logs["audit_logs"] if item["event_type"] == "review_completed"
        )
        provenance = completed_audit["metadata"]["decision_provenance"]
        self.assertEqual(provenance["provenance_version"], "1.0.0")
        self.assertEqual(len(provenance["workflow_sha256"]), 64)
        self.assertEqual(len(provenance["bundle_sha256"]), 64)
        self.assertEqual(len(provenance["tool_plugins"]), 8)
        self.assertNotEqual(provenance["tool_plugins"][0]["name"], "[REDACTED]")

    def test_review_service_uses_seeded_medical_registry_at_runtime(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        claim = json.loads(json.dumps(claim))
        claim.pop("medical_evidence", None)
        claim["claim_id"] = "STARTER-RUNTIME-REGISTRY-001"
        claim["claim"]["diagnosis_code"] = "SYN-M54"
        claim["claim"]["treatment_code"] = "TRT-NONCOV-001"
        generated = WORKSPACE / "data_generator" / "generated"
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                template_root=TEMPLATE_ROOT,
                sqlite_path=Path(temp_dir) / "starter.sqlite3",
                reports_dir=Path(temp_dir) / "reports",
                specialist_config_path=(
                    TEMPLATE_ROOT
                    / "developer_kit"
                    / "starter_kit"
                    / "config"
                    / "specialist_plugins.synthetic_insurer.yaml"
                ),
            )
            service = ReviewService(settings)
            service.repository.seed_medical_registry(
                medical_code_registry=_read_json(generated / "medical_code_registry.json"),
                edi_code_registry=_read_json(generated / "edi_code_registry.json"),
                diagnosis_treatment_rules=_read_json(generated / "diagnosis_treatment_rules.json"),
                insurer_medical_routing_rules=_read_json(generated / "insurer_medical_routing_rules.json"),
                source_files=["runtime-registry-smoke"],
            )
            output = service.run_review(claim_payload=claim)

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

    def test_medical_registry_failure_routes_to_human_review(self) -> None:
        claim = _read_first_jsonl(WORKSPACE / "data_generator" / "generated" / "claims_eval.jsonl")
        claim = json.loads(json.dumps(claim))
        claim["claim_id"] = "STARTER-REGISTRY-FAIL-CLOSED-001"
        with tempfile.TemporaryDirectory() as temp_dir:
            settings = Settings(
                template_root=TEMPLATE_ROOT,
                sqlite_path=Path(temp_dir) / "starter.sqlite3",
                reports_dir=Path(temp_dir) / "reports",
                specialist_config_path=(
                    TEMPLATE_ROOT
                    / "developer_kit"
                    / "starter_kit"
                    / "config"
                    / "specialist_plugins.synthetic_insurer.yaml"
                ),
            )
            service = ReviewService(settings)
            with patch(
                "ai_agent_template.developer_kit.starter_kit.app.core.review_service."
                "RuntimeMedicalRegistryService.enrich_claim_payload",
                side_effect=RuntimeError("registry unavailable"),
            ):
                output = service.run_review(claim_payload=claim)
        self.assertEqual(output["recommended_decision"], "human_review")
        self.assertTrue(output["requires_human_review"])
        self.assertIn("TOOL_FAILURE", output["reason_codes"])

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

    def test_reviewer_ui_contains_operational_controls(self) -> None:
        html = (
            TEMPLATE_ROOT
            / "developer_kit"
            / "starter_kit"
            / "app"
            / "ui"
            / "reviewer_assistant_screen.html"
        ).read_text(encoding="utf-8")
        self.assertIn('lang="ko"', html)
        self.assertIn("resetReviewPanels", html)
        self.assertIn("reviewLoading", html)
        self.assertIn("/reviews/queue", html)
        self.assertIn("Deterministic Confidence", html)
        self.assertIn("Explanation Confidence", html)

    def test_customer_ui_uses_product_catalog_and_policy_suggestions(self) -> None:
        html = (
            TEMPLATE_ROOT
            / "developer_kit"
            / "starter_kit"
            / "app"
            / "ui"
            / "customer_claim_screen.html"
        ).read_text(encoding="utf-8")
        self.assertIn('list="productOptions"', html)
        self.assertIn('id="productName"', html)
        self.assertIn("/products/${encodeURIComponent(productId)}/policies", html)

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_fastapi_app_factory_when_dependency_available(self) -> None:
        from ai_agent_template.developer_kit.starter_kit.app.main import create_app

        app = create_app()
        self.assertEqual(app.title, "Claim Review Agent Starter Kit")
        paths = {route.path for route in app.routes}
        self.assertIn("/claims", paths)
        self.assertIn("/reviews/queue", paths)
        self.assertIn("/reviews/{claim_id}/actions", paths)
        self.assertIn("/reviews/{claim_id}/audit-logs", paths)
        self.assertIn("/products", paths)
        self.assertIn("/products/{product_id}/policies", paths)


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


def _read_json(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


if __name__ == "__main__":
    unittest.main()
