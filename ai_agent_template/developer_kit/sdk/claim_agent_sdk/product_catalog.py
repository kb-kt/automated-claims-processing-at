from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .api_errors import NotFoundApiError, ValidationApiError


class ProductCatalogRegistry:
    """Read-only product/policy registry shared by the Starter Kit and MVP."""

    def __init__(
        self,
        *,
        catalog_path: Path,
        policies_path: Path,
        active_product_path: Path | None = None,
    ):
        self.catalog_path = catalog_path
        self.policies_path = policies_path
        self.active_product_path = active_product_path

    @classmethod
    def from_generated_dir(cls, generated_dir: Path) -> "ProductCatalogRegistry":
        return cls(
            catalog_path=generated_dir / "products" / "product_catalog.json",
            policies_path=generated_dir / "policies.jsonl",
            active_product_path=generated_dir / "products.json",
        )

    @property
    def available(self) -> bool:
        return self.catalog_path.exists() and self.policies_path.exists()

    def list_products(self) -> dict[str, Any]:
        catalog = self._catalog()
        return {
            "schema_version": catalog.get("schema_version", "1.0.0"),
            "usage": catalog.get("usage", "synthetic_development_and_evaluation_only"),
            "products": list(catalog.get("products", [])),
        }

    def get_product(self, product_id: str) -> dict[str, Any]:
        entry = self._product_entry(product_id)
        relative_path = str(entry.get("file_path", ""))
        product_path = (self.catalog_path.parent / relative_path).resolve()
        try:
            product_path.relative_to(self.catalog_path.parent.resolve())
        except ValueError as exc:
            raise ValidationApiError("Product catalog contains an unsafe file path.") from exc
        if not product_path.is_file():
            raise NotFoundApiError(f"Product file not found: {product_id}")
        return json.loads(product_path.read_text(encoding="utf-8"))

    def list_policies(self, product_id: str | None = None) -> dict[str, Any]:
        if product_id is not None:
            self._product_entry(product_id)
        policies = [
            policy
            for policy in self._policies()
            if product_id is None or policy.get("product_id") == product_id
        ]
        return {"product_id": product_id, "policies": policies}

    def validate_relationship(self, *, product_id: str, policy_id: str) -> None:
        if not self.available:
            return
        self._product_entry(product_id)
        policy = next(
            (item for item in self._policies() if item.get("policy_id") == policy_id),
            None,
        )
        if policy is None:
            raise ValidationApiError(
                "Policy ID is not registered in the product catalog.",
                [f"policy_id: {policy_id}"],
            )
        if policy.get("product_id") != product_id:
            raise ValidationApiError(
                "Policy ID does not belong to the selected product.",
                [
                    f"policy_id: {policy_id}",
                    f"selected product_id: {product_id}",
                    f"registered product_id: {policy.get('product_id')}",
                ],
            )

    def is_active_adjudication_product(self, product_id: str) -> bool:
        if self.active_product_path is None or not self.active_product_path.exists():
            return False
        active_product = json.loads(self.active_product_path.read_text(encoding="utf-8"))
        return active_product.get("product_id") == product_id

    def _catalog(self) -> dict[str, Any]:
        if not self.catalog_path.exists():
            raise NotFoundApiError("Product catalog is not available.")
        data = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        if not isinstance(data.get("products"), list):
            raise ValidationApiError("Product catalog is invalid.")
        return data

    def _product_entry(self, product_id: str) -> dict[str, Any]:
        entry = next(
            (item for item in self._catalog()["products"] if item.get("product_id") == product_id),
            None,
        )
        if entry is None:
            raise NotFoundApiError(f"Product not found: {product_id}")
        return entry

    def _policies(self) -> list[dict[str, Any]]:
        if not self.policies_path.exists():
            raise NotFoundApiError("Policy catalog is not available.")
        with self.policies_path.open("r", encoding="utf-8") as file:
            return [json.loads(line) for line in file if line.strip()]
