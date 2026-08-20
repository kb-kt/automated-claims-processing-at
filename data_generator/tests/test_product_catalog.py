import copy
import json
import unittest
from pathlib import Path

from data_generator.src.product_catalog import (
    load_catalog_products,
    validate_product_policy_relationships,
    validate_products,
)


BASE_DIR = Path(__file__).resolve().parents[1]
GENERATED = BASE_DIR / "generated"


def _read_jsonl(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8") as file:
        return [json.loads(line) for line in file if line.strip()]


class ProductCatalogTest(unittest.TestCase):
    def test_normalized_catalog_and_all_claim_relationships_are_valid(self) -> None:
        products = load_catalog_products(GENERATED / "products" / "product_catalog.json")
        policies = _read_jsonl(GENERATED / "policies.jsonl")
        claims = _read_jsonl(GENERATED / "claims_dev.jsonl")
        claims += _read_jsonl(GENERATED / "claims_eval.jsonl")

        self.assertEqual(len(products), 13)
        self.assertTrue(validate_products(products).ok)
        relationship = validate_product_policy_relationships(products, policies, claims)
        self.assertTrue(relationship.ok, relationship.errors)
        counts = {
            product["product_id"]: sum(
                policy["product_id"] == product["product_id"] for policy in policies
            )
            for product in products
        }
        self.assertTrue(all(count >= 3 for count in counts.values()))

    def test_product_policy_mismatch_is_rejected(self) -> None:
        products = load_catalog_products(GENERATED / "products" / "product_catalog.json")
        policies = _read_jsonl(GENERATED / "policies.jsonl")
        claims = [_read_jsonl(GENERATED / "claims_dev.jsonl")[0]]
        bad_claim = copy.deepcopy(claims[0])
        bad_claim["product_id"] = next(
            product["product_id"]
            for product in products
            if product["product_id"] != bad_claim["product_id"]
        )

        result = validate_product_policy_relationships(products, policies, [bad_claim])

        self.assertFalse(result.ok)
        self.assertTrue(any("does not match policy" in error for error in result.errors))


if __name__ == "__main__":
    unittest.main()
