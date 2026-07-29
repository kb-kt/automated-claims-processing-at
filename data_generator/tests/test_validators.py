import copy
import json
import unittest
from pathlib import Path

from data_generator.src.validators import validate_dataset


BASE_DIR = Path(__file__).resolve().parents[1]


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


class ValidatorsTest(unittest.TestCase):
    def test_sample_dataset_is_valid(self) -> None:
        claims = _read_jsonl(BASE_DIR / "samples" / "claims_sample.jsonl")
        labels = _read_jsonl(BASE_DIR / "samples" / "labels_sample.jsonl")

        result = validate_dataset(claims, labels)

        self.assertTrue(result.ok, result.errors)

    def test_forbidden_answer_field_in_claim_fails(self) -> None:
        claims = _read_jsonl(BASE_DIR / "samples" / "claims_sample.jsonl")
        labels = _read_jsonl(BASE_DIR / "samples" / "labels_sample.jsonl")
        bad_claims = copy.deepcopy(claims)
        bad_claims[0]["expected_decision"] = "pay"

        result = validate_dataset(bad_claims, labels)

        self.assertFalse(result.ok)
        self.assertTrue(any("agent-forbidden" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
