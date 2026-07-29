from __future__ import annotations

from typing import Any

from .base import SyntheticToolPlugin
from .product_catalog import find_coverage, load_product


class SyntheticDocumentCheckerPlugin(SyntheticToolPlugin):
    name = "document_checker"
    contract_name = "document_checker"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        product = load_product(context.get("product_path"))
        coverage = find_coverage(product, payload["coverage_code"])
        submitted = list(payload.get("submitted_documents", []))
        submitted_set = set(submitted)
        missing = [doc for doc in coverage.get("required_documents", []) if doc not in submitted_set]
        return self.ok(
            {
                "missing_documents": missing,
                "submitted_documents": submitted,
                "documents_complete": not missing,
            }
        )

