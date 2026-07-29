# Claim Agent SDK

Python SDK for loading `ai_agent_template` artifacts, validating claim input and agent output, registering tool plugins, running the synthetic review workflow, and evaluating outputs.

The SDK treats `ai_agent_template` as the source of truth. It does not duplicate schema, standards, workflow, or tool contract definitions.

## RAG-ready retrieval

The SDK includes a dependency-free `KeywordPolicyRetriever` for validating the policy retrieval contract before a real vector store is introduced.

```python
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    KeywordPolicyRetriever,
    TemplateBundle,
)

template = TemplateBundle.load("ai_agent_template")
retriever = KeywordPolicyRetriever.from_template(template)
result = retriever.retrieve({"query": "outpatient noncovered deductible", "top_k": 3})
```

This retriever is for local validation only. Production RAG should implement the same request/result schemas described in `ai_agent_template/docs/RAG_READY.md`.
