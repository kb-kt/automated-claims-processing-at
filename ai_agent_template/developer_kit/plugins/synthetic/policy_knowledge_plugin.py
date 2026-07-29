from __future__ import annotations

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    KeywordPolicyRetriever,
    TemplateBundle,
)


class SyntheticPolicyKnowledgePlugin(KeywordPolicyRetriever):
    name = "synthetic_policy_knowledge"
    version = "1.0.0"
    owner = "claim-review-template"
    retrieval_modes = ["keyword"]

    @classmethod
    def from_template(cls, template: TemplateBundle) -> "SyntheticPolicyKnowledgePlugin":
        retriever = KeywordPolicyRetriever.from_template(template)
        return cls(retriever.chunks, validator=retriever.validator)
