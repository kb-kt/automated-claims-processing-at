from __future__ import annotations

from typing import Any

from .base import SyntheticToolPlugin
from .product_catalog import calculate_payable, find_coverage, load_product


class SyntheticPayableCalculatorPlugin(SyntheticToolPlugin):
    name = "payable_calculator"
    contract_name = "payable_calculator"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        product = load_product(context.get("product_path"))
        coverage = find_coverage(product, payload["coverage_code"])
        result = calculate_payable(coverage, int(payload["claimed_amount"]))
        return self.ok(result)

