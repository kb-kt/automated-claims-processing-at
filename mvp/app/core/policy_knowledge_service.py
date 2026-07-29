from __future__ import annotations

from typing import Any

from ai_agent_template.developer_kit.plugin_interface import (
    PolicyKnowledgePluginConformance,
)
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    KeywordPolicyRetriever,
    SchemaValidator,
    TemplateBundle,
)

from .settings import Settings


class PolicyKnowledgeService:
    def __init__(self, template: TemplateBundle, settings: Settings):
        self.template = template
        self.settings = settings
        self.validator = SchemaValidator(template)
        self._retriever: KeywordPolicyRetriever | None = None

    def load_retriever(self) -> KeywordPolicyRetriever | None:
        if not self.settings.retrieval_enabled:
            return None
        if self._retriever is None:
            retriever = KeywordPolicyRetriever.from_template(self.template)
            if not retriever.chunks:
                return None
            product_id = next((chunk.product_id for chunk in retriever.chunks if chunk.product_id), "")
            filters = {"product_id": product_id} if product_id else {}
            PolicyKnowledgePluginConformance(self.template).assert_conformant(
                retriever,
                sample_request={
                    "query": "outpatient covered deductible",
                    "top_k": min(max(self.settings.retrieval_top_k, 1), 20),
                    "retrieval_mode": self.settings.retrieval_mode,
                    "filters": filters,
                },
            )
            self._retriever = retriever
        return self._retriever

    def retrieve(
        self,
        query: str,
        *,
        product_id: str | None = None,
        coverage_code: str | None = None,
    ) -> dict[str, Any] | None:
        retriever = self.load_retriever()
        if retriever is None:
            return None
        filters: dict[str, str] = {}
        if product_id:
            filters["product_id"] = product_id
        if coverage_code:
            filters["coverage_code"] = coverage_code
        request = {
            "query": query,
            "top_k": self.settings.retrieval_top_k,
            "retrieval_mode": self.settings.retrieval_mode,
            "filters": filters,
        }
        result = retriever.retrieve(request)
        self.validator.validate_retrieval_result(result)
        return result

    def readiness(self) -> dict[str, Any]:
        retriever = self.load_retriever()
        return {
            "retrieval_enabled": self.settings.retrieval_enabled,
            "retrieval_mode": self.settings.retrieval_mode,
            "retrieval_top_k": self.settings.retrieval_top_k,
            "retriever_available": retriever is not None,
            "chunk_count": len(retriever.chunks) if retriever else 0,
        }
