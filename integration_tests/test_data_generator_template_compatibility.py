import json
import re
import unittest
from datetime import date
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT_DIR / "data_generator" / "generated"
TEMPLATE_DIR = ROOT_DIR / "ai_agent_template"
INPUT_SCHEMA_PATH = TEMPLATE_DIR / "schemas" / "claim_review_input.schema.json"

FORBIDDEN_CLAIM_KEYS = {
    "expected_decision",
    "expected_payable_amount",
    "expected_explanation",
    "reason_codes",
    "calculation",
    "requires_human_review",
    "fraud_suspected",
}


class DataGeneratorTemplateCompatibilityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.input_schema = _read_json(INPUT_SCHEMA_PATH)
        cls.claim_files = [
            GENERATED_DIR / "claims_dev.jsonl",
            GENERATED_DIR / "claims_eval.jsonl",
        ]
        cls.label_files = [
            GENERATED_DIR / "labels_dev.jsonl",
            GENERATED_DIR / "labels_eval.jsonl",
        ]
        cls.decision_codes = _extract_yaml_codes(TEMPLATE_DIR / "standards" / "decision_codes.yaml")
        cls.coverage_codes = _extract_yaml_codes(TEMPLATE_DIR / "standards" / "coverage_codes.yaml")
        cls.document_codes = _extract_yaml_codes(TEMPLATE_DIR / "standards" / "document_codes.yaml")
        cls.reason_codes = _extract_yaml_codes(TEMPLATE_DIR / "standards" / "reason_codes.yaml")

    def test_required_files_exist(self) -> None:
        for path in [INPUT_SCHEMA_PATH, *self.claim_files, *self.label_files]:
            with self.subTest(path=str(path.relative_to(ROOT_DIR))):
                self.assertTrue(path.exists(), f"Missing required file: {path}")
                self.assertGreater(path.stat().st_size, 0, f"Empty required file: {path}")

    def test_claims_are_compatible_with_template_input_contract(self) -> None:
        for claim_file in self.claim_files:
            claims = _read_jsonl(claim_file)
            self.assertGreater(len(claims), 0)
            for row_number, claim in enumerate(claims, start=1):
                with self.subTest(file=claim_file.name, row=row_number):
                    self._assert_claim_matches_template_contract(claim)

    def test_claims_do_not_leak_label_fields(self) -> None:
        for claim_file in self.claim_files:
            for row_number, claim in enumerate(_read_jsonl(claim_file), start=1):
                with self.subTest(file=claim_file.name, row=row_number):
                    leaked = _find_forbidden_keys(claim, FORBIDDEN_CLAIM_KEYS)
                    self.assertEqual(leaked, set())

    def test_runtime_artifacts_do_not_leak_evaluation_fields(self) -> None:
        runtime_files = [
            "insureds.json",
            "providers.json",
            "historical_claims.jsonl",
            "claims_dev.jsonl",
            "claims_eval.jsonl",
            "document_metadata_dev.jsonl",
            "document_metadata_eval.jsonl",
            "claim_document_links_dev.jsonl",
            "claim_document_links_eval.jsonl",
            "fraud_context_seed_dev.jsonl",
            "fraud_context_seed_eval.jsonl",
        ]
        for file_name in runtime_files:
            path = GENERATED_DIR / file_name
            rows = _read_jsonl(path) if path.suffix == ".jsonl" else [_read_json(path)]
            for row_number, row in enumerate(rows, start=1):
                with self.subTest(file=file_name, row=row_number):
                    leaked = _find_forbidden_keys(row, FORBIDDEN_CLAIM_KEYS)
                    self.assertEqual(leaked, set())

    def test_claim_ids_match_labels_by_split(self) -> None:
        for claim_file, label_file in zip(self.claim_files, self.label_files):
            claims = _read_jsonl(claim_file)
            labels = _read_jsonl(label_file)
            claim_ids = {claim["claim_id"] for claim in claims}
            label_ids = {label["claim_id"] for label in labels}
            with self.subTest(claim_file=claim_file.name, label_file=label_file.name):
                self.assertEqual(claim_ids, label_ids)

    def test_labels_use_template_standard_codes(self) -> None:
        for label_file in self.label_files:
            for row_number, label in enumerate(_read_jsonl(label_file), start=1):
                with self.subTest(file=label_file.name, row=row_number):
                    self.assertIn(label["expected_decision"], self.decision_codes)
                    self.assertIn(label["coverage_code"], self.coverage_codes)
                    for document_code in label.get("missing_documents", []):
                        self.assertIn(document_code, self.document_codes)
                    for reason_code in label.get("reason_codes", []):
                        self.assertIn(reason_code, self.reason_codes)

    def test_generated_product_id_is_consistent(self) -> None:
        products = _read_json(GENERATED_DIR / "products.json")
        product_id = products["product_id"]
        for claim_file in self.claim_files:
            for row_number, claim in enumerate(_read_jsonl(claim_file), start=1):
                with self.subTest(file=claim_file.name, row=row_number):
                    self.assertEqual(claim["product_id"], product_id)

    def _assert_claim_matches_template_contract(self, claim: dict[str, Any]) -> None:
        for field in self.input_schema["required"]:
            self.assertIn(field, claim)

        self.assert_is_non_empty_string(claim["claim_id"])
        self.assert_is_non_empty_string(claim["policy_id"])
        self.assert_is_non_empty_string(claim["product_id"])
        self.assert_is_non_empty_string(claim["scenario_type"])

        claimant = claim["claimant"]
        for field in self.input_schema["properties"]["claimant"]["required"]:
            self.assertIn(field, claimant)
        self.assert_is_non_empty_string(claimant["synthetic_person_id"])
        self.assertIsInstance(claimant["age"], int)
        self.assertGreaterEqual(claimant["age"], 0)
        self.assertLessEqual(claimant["age"], 120)
        self.assertIn(claimant["gender"], {"F", "M"})

        policy = claim["policy"]
        self.assertIn(policy["status"], {"active", "lapsed", "terminated", "pending"})
        self.assert_is_iso_date(policy["coverage_start_date"])
        self.assert_is_iso_date(policy["coverage_end_date"])
        self.assertLessEqual(
            date.fromisoformat(policy["coverage_start_date"]),
            date.fromisoformat(policy["coverage_end_date"]),
        )

        claim_body = claim["claim"]
        for field in self.input_schema["properties"]["claim"]["required"]:
            self.assertIn(field, claim_body)
        self.assertIn(claim_body["care_setting"], {"outpatient", "inpatient", "pharmacy"})
        self.assertIn(
            claim_body["benefit_category"],
            {"covered", "noncovered", "special_noncovered"},
        )
        self.assert_is_non_empty_string(claim_body["treatment_code"])
        self.assert_is_non_empty_string(claim_body["diagnosis_code"])
        for date_field in [
            "incident_date",
            "treatment_start_date",
            "treatment_end_date",
            "claim_date",
        ]:
            self.assert_is_iso_date(claim_body[date_field])
        self.assertLessEqual(
            date.fromisoformat(claim_body["treatment_start_date"]),
            date.fromisoformat(claim_body["treatment_end_date"]),
        )
        self.assertIsInstance(claim_body["claimed_amount"], int)
        self.assertGreaterEqual(claim_body["claimed_amount"], 0)
        self.assert_is_non_empty_string(claim_body["receipt_id"])
        self.assertIn(
            claim_body["provider_type"],
            {"medical_institution", "pharmacy", "non_medical_provider"},
        )

        self.assertIsInstance(claim["documents"], list)
        self.assertEqual(len(claim["documents"]), len(set(claim["documents"])))
        for document_code in claim["documents"]:
            self.assertIn(document_code, self.document_codes)

        history = claim["claim_history"]
        self.assertIsInstance(history["same_diagnosis_claims_90d"], int)
        self.assertGreaterEqual(history["same_diagnosis_claims_90d"], 0)
        self.assertIsInstance(history["manual_therapy_count_180d"], int)
        self.assertGreaterEqual(history["manual_therapy_count_180d"], 0)
        self.assertIsInstance(history["prior_receipt_ids"], list)
        self.assertEqual(
            len(history["prior_receipt_ids"]),
            len(set(history["prior_receipt_ids"])),
        )

        signals = claim["signals"]
        for field in self.input_schema["properties"]["signals"]["required"]:
            self.assertIn(field, signals)
        for signal_name, signal_value in signals.items():
            self.assertIsInstance(signal_value, bool, signal_name)

    def assert_is_non_empty_string(self, value: Any) -> None:
        self.assertIsInstance(value, str)
        self.assertGreater(len(value), 0)

    def assert_is_iso_date(self, value: Any) -> None:
        self.assertIsInstance(value, str)
        try:
            date.fromisoformat(value)
        except ValueError as exc:
            raise AssertionError(f"Invalid ISO date: {value}") from exc


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    records = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if line.strip():
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise AssertionError(f"Invalid JSONL at {path}:{line_number}") from exc
    return records


def _extract_yaml_codes(path: Path) -> set[str]:
    text = path.read_text(encoding="utf-8")
    return set(re.findall(r"^\s+-\s+code:\s+([A-Za-z0-9_]+)\s*$", text, re.MULTILINE))


def _find_forbidden_keys(value: Any, forbidden: set[str]) -> set[str]:
    found = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in forbidden or key.startswith("expected_"):
                found.add(key)
            found.update(_find_forbidden_keys(nested, forbidden))
    elif isinstance(value, list):
        for item in value:
            found.update(_find_forbidden_keys(item, forbidden))
    return found


if __name__ == "__main__":
    unittest.main()
