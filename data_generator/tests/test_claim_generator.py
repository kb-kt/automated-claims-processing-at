import unittest
from pathlib import Path

from data_generator.src.adjudication_rules import adjudicate
from data_generator.src.config import load_config
from data_generator.src.constants import AGENT_FORBIDDEN_KEYS
from data_generator.src.claim_generator import ClaimGenerator
from data_generator.src.product_loader import load_product
from data_generator.src.validators import validate_dataset


BASE_DIR = Path(__file__).resolve().parents[1]


class ClaimGeneratorTest(unittest.TestCase):
    def test_generate_claims_and_labels(self) -> None:
        config = load_config(
            BASE_DIR / "samples" / "generation_config.sample.json",
            dev_count=50,
            eval_count=10,
        )
        product = load_product(BASE_DIR / "samples" / "products.json")
        generator = ClaimGenerator(config, product)
        claims = generator.generate("dev", config.dev_count)
        labels = [adjudicate(product, claim) for claim in claims]

        self.assertEqual(len(claims), 50)
        self.assertEqual(len(labels), 50)
        decisions = {label["expected_decision"] for label in labels}
        self.assertTrue({"pay", "partial_pay", "request_documents", "deny", "human_review"} <= decisions)
        first_claim = claims[0]
        self.assertIn("insured_profile", first_claim)
        self.assertEqual(
            first_claim["insured_profile"]["age_at_service"],
            first_claim["claimant"]["age"],
        )
        self.assertEqual(first_claim["claim"]["receipt_hash"], f"RH-SYN-DEV-000001")
        self.assertIn("provider_id", first_claim["claim"])
        self.assertIn("same_insured_provider_claims_30d", first_claim["claim_history"])
        self.assertIn("prior_receipt_hashes", first_claim["claim_history"])
        validation = validate_dataset(claims, labels)
        self.assertTrue(validation.ok, validation.errors)

    def test_claims_do_not_contain_answer_fields(self) -> None:
        config = load_config(
            BASE_DIR / "samples" / "generation_config.sample.json",
            dev_count=20,
            eval_count=0,
        )
        product = load_product(BASE_DIR / "samples" / "products.json")
        claims = ClaimGenerator(config, product).generate("dev", config.dev_count)

        for claim in claims:
            serialized_keys = set(_walk_keys(claim))
            self.assertTrue(serialized_keys.isdisjoint(AGENT_FORBIDDEN_KEYS))


def _walk_keys(value):
    if isinstance(value, dict):
        for key, nested in value.items():
            yield key
            yield from _walk_keys(nested)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


if __name__ == "__main__":
    unittest.main()
