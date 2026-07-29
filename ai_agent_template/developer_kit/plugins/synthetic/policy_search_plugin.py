from __future__ import annotations

from typing import Any

from .base import SyntheticToolPlugin
from .product_catalog import load_product


class SyntheticPolicySearchPlugin(SyntheticToolPlugin):
    name = "policy_search"
    contract_name = "policy_search"

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        product = load_product(context.get("product_path"))
        product_id = payload.get("product_id")
        if product_id and product_id != product.get("product_id"):
            return self.fail("POLICY_DOCUMENT_NOT_FOUND", f"Unknown product_id: {product_id}")
        query = payload.get("query", "")
        retriever = context.get("policy_retriever")
        if retriever is not None and hasattr(retriever, "retrieve"):
            retrieval_options = dict(context.get("policy_retrieval_options") or {})
            retrieval_result = retriever.retrieve(
                {
                    "query": query,
                    "top_k": int(payload.get("top_k") or retrieval_options.get("top_k") or 3),
                    "retrieval_mode": payload.get(
                        "retrieval_mode",
                        retrieval_options.get("retrieval_mode", "keyword"),
                    ),
                    "filters": {
                        "product_id": product_id or product.get("product_id"),
                        **dict(payload.get("filters") or {}),
                    },
                },
                context,
            )
            matches = [_policy_match(match) for match in retrieval_result.get("matches", [])]
            if matches:
                return self.ok({"matches": matches})

        matches = [
            {
                "section": "coverage-summary",
                "summary": f"Synthetic product {product.get('product_name')} coverage basis for {query}.",
                "source": "policy_documents.md",
            },
            {
                "section": "deductible-and-limit",
                "summary": "Payable amount must use configured limit and deductible rules.",
                "source": "policy_documents.md",
            },
        ]
        return self.ok({"matches": matches})


def _policy_match(match: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "chunk_id",
        "source",
        "section",
        "summary",
        "text",
        "product_id",
        "product_version",
        "effective_date",
        "coverage_code",
        "clause_id",
        "citation_id",
        "retrieval_score",
        "retrieval_method",
    }
    return {
        key: value
        for key, value in match.items()
        if key in allowed and value not in ("", None)
    }
