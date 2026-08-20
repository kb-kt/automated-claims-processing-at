import unittest
from pathlib import Path

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    NotFoundApiError,
    ProductCatalogRegistry,
    ValidationApiError,
)


WORKSPACE = Path(__file__).resolve().parents[4]
GENERATED = WORKSPACE / "data_generator" / "generated"


class ProductCatalogRegistryTest(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = ProductCatalogRegistry.from_generated_dir(GENERATED)

    def test_catalog_lists_products_and_scoped_policies(self) -> None:
        products = self.registry.list_products()["products"]
        synthetic = next(item for item in products if item["product_id"] == "SYN-MED-001")
        policies = self.registry.list_policies("SYN-MED-001")["policies"]

        self.assertEqual(synthetic["product_name"], "Synthetic Medical Guard 4")
        self.assertGreaterEqual(len(policies), 3)
        self.assertTrue(all(item["product_id"] == "SYN-MED-001" for item in policies))

    def test_relationship_validation_rejects_unknown_and_mismatch(self) -> None:
        policy = self.registry.list_policies("SYN-MED-001")["policies"][0]
        self.registry.validate_relationship(
            product_id="SYN-MED-001",
            policy_id=policy["policy_id"],
        )
        other_product = next(
            item["product_id"]
            for item in self.registry.list_products()["products"]
            if item["product_id"] != "SYN-MED-001"
        )
        with self.assertRaises(ValidationApiError):
            self.registry.validate_relationship(
                product_id=other_product,
                policy_id=policy["policy_id"],
            )
        with self.assertRaises(NotFoundApiError):
            self.registry.validate_relationship(
                product_id="UNKNOWN-PRODUCT",
                policy_id=policy["policy_id"],
            )

    def test_only_legacy_active_product_has_automatic_adjudication_profile(self) -> None:
        self.assertTrue(self.registry.is_active_adjudication_product("SYN-MED-001"))
        self.assertFalse(
            self.registry.is_active_adjudication_product("ABL-UNIV-LIFE-2501-RDR_SURGERY")
        )


if __name__ == "__main__":
    unittest.main()
