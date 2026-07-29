from __future__ import annotations

from typing import Any

from .base import SyntheticToolPlugin
from .product_catalog import load_product, resolve_coverage


class SyntheticCoverageResolverPlugin(SyntheticToolPlugin):
    name = "coverage_resolver"
    contract_name = "coverage_resolver"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        product = load_product(context.get("product_path"))
        coverage = resolve_coverage(product, payload["claim"])
        return self.ok(
            {
                "coverage_code": coverage["coverage_code"],
                "coverage_name": coverage["name"],
                "confidence": 0.98,
            }
        )

