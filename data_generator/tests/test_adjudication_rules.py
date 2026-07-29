import json
import unittest
from pathlib import Path

from data_generator.src.adjudication_rules import adjudicate
from data_generator.src.product_loader import load_product


BASE_DIR = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


class AdjudicationRulesTest(unittest.TestCase):
    def test_sample_labels_match_hidden_rules(self) -> None:
        product = load_product(BASE_DIR / "samples" / "products.json")
        claims = _read_jsonl(BASE_DIR / "samples" / "claims_sample.jsonl")
        expected_labels = {
            label["claim_id"]: label
            for label in _read_jsonl(BASE_DIR / "samples" / "labels_sample.jsonl")
        }

        for claim in claims:
            with self.subTest(claim_id=claim["claim_id"]):
                actual = adjudicate(product, claim)
                expected = expected_labels[claim["claim_id"]]
                self.assertEqual(actual["expected_decision"], expected["expected_decision"])
                self.assertEqual(
                    actual["expected_payable_amount"],
                    expected["expected_payable_amount"],
                )
                self.assertEqual(actual["coverage_code"], expected["coverage_code"])
                self.assertEqual(actual["missing_documents"], expected["missing_documents"])
                self.assertEqual(
                    actual["requires_human_review"],
                    expected["requires_human_review"],
                )
                self.assertEqual(actual["fraud_suspected"], expected["fraud_suspected"])
                self.assertEqual(actual["calculation"], expected["calculation"])
                self.assertEqual(
                    set(actual["reason_codes"]),
                    set(expected["reason_codes"]),
                )


if __name__ == "__main__":
    unittest.main()
