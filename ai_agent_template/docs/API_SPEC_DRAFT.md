# API Specification Draft

> Historical draft. The authoritative 1.0.0 contract is `docs/API_SPEC.md` with machine-readable operations in `schemas/api_surface.contract.json`.

Version: 1.0.0

Framework target: FastAPI

OpenAPI target: 3.1.0

JSON Schema target: Draft 2020-12

This draft defines the API surface expected for Template-based applications. The Starter Kit implements the core subset directly, and the MVP extends the same shape.

## 1. Base

```text
Base path: /api/v1
Content-Type: application/json
```

## 2. Model Configuration

Default model provider is defined in:

```text
ai_agent_template/config/model_config.yaml
```

Current default:

```text
provider: general_llm
base_url: https://m2.geniemars.kt.co.kr:10601/v1
model_id: gemma-4-26B-4aB-it
api_key: dummy
```

The API implementation must not hard-code these values. It must read model configuration from the config file or an equivalent runtime configuration provider.

Detailed configuration rules, key meanings, environment variable overrides, and secret handling are defined in:

```text
ai_agent_template/docs/CONFIGURATION.md
```

## 3. Endpoint Summary

| Method | Path | Purpose |
|---|---|---|
| POST | `/claims` | Register or validate a claim payload |
| GET | `/claims` | List recently submitted claims |
| GET | `/claims/{claim_id}` | Retrieve claim status and payload |
| POST | `/reviews` | Run claim review workflow |
| GET | `/reviews/queue` | Retrieve reviewer worklist |
| GET | `/reviews/{claim_id}` | Retrieve latest review output |
| POST | `/reviews/{claim_id}/rerun` | Rerun review workflow |
| POST | `/reviews/{claim_id}/actions` | Store reviewer action |
| GET | `/reviews/{claim_id}/actions` | Retrieve reviewer action history |
| GET | `/reviews/{claim_id}/audit-logs` | Retrieve claim audit logs |
| GET | `/configs/model` | Retrieve active model config |
| PUT | `/configs/model` | Update active model provider |
| GET | `/standards/reason-codes` | Retrieve reason code registry |

## 4. DTOs

### 4.1 `ClaimCreateRequest`

Schema reference:

```text
schemas/claim_review_input.schema.json
```

### 4.2 `ClaimCreateResponse`

```json
{
  "claim_id": "CLM-EVAL-EXAMPLE-0001",
  "status": "received"
}
```

### 4.3 `ClaimReviewRequest`

```json
{
  "claim": "claim_review_input",
  "policy_document_ref": "data_generator/generated/policy_documents.md",
  "options": {
    "model_provider": "general_llm",
    "model_name": "gemma-4-26B-4aB-it",
    "strict_schema": true,
    "force_human_review": false
  }
}
```

### 4.4 `ClaimReviewResponse`

```json
{
  "request_id": "REQ-000001",
  "claim_id": "CLM-EVAL-EXAMPLE-0001",
  "review_status": "completed",
  "status": "completed",
  "output": "claim_review_output",
  "agent_output": "claim_review_output",
  "tool_trace": [
    {
      "tool_name": "coverage_resolver",
      "status": "success",
      "duration_ms": 12
    }
  ],
  "errors": []
}
```

`output` is the canonical review object. `agent_output` is retained as a compatibility alias for earlier clients.

### 4.5 `ClaimReviewOutput` Confidence Fields

`claim_review_output` separates decision confidence from explanation confidence:

- `confidence`: deterministic confidence from tool/rule workflow checks.
- `confidence_assessment.score_source`: fixed to `deterministic_rules_with_llm_assistance`.
- `confidence_assessment.deterministic_confidence`: must equal the deterministic `confidence`.
- `confidence_assessment.evidence_clarity`, `judgment_difficulty`, `uncertainty_level`, `uncertainty_explanation`, and `assessment_basis`: fields the LLM may help phrase or classify, without changing the deterministic decision.
- `explanation_confidence`: validation result measuring whether LLM-generated explanations stay faithful to tool outputs, calculation, and policy citation metadata.

LLM self-confidence must not be treated as a calibrated payment-decision probability.

### 4.6 `ReviewerActionRequest`

```json
{
  "action": "accept_recommendation | modify_recommendation | request_documents | defer | mark_human_review",
  "reviewer_id": "string",
  "override_decision": "pay | partial_pay | request_documents | deny | human_review",
  "override_payable_amount": 0,
  "reviewer_note": "string"
}
```

### 4.7 `ReviewQueueResponse`

```json
{
  "queue": [
    {
      "claim_id": "string",
      "policy_id_masked": "string",
      "product_id": "string",
      "status": "received | reviewing | completed | failed | human_review_required",
      "recommended_decision": "pay | partial_pay | request_documents | deny | human_review",
      "requires_human_review": false,
      "fraud_suspected": false,
      "confidence": 0.94,
      "sla_status": "ok | due_soon | overdue | closed",
      "priority_score": 50
    }
  ]
}
```

## 5. Error Handling

Error response schema:

```text
schemas/api_error.schema.json
```

Standard API error codes:

```text
VALIDATION_ERROR
SCHEMA_VERSION_UNSUPPORTED
NOT_FOUND
CONFLICT
AUTHENTICATION_REQUIRED
ACCESS_FORBIDDEN
INVALID_DOCUMENT_UPLOAD
DOCUMENT_TOO_LARGE
DEPENDENCY_ERROR
INTERNAL_ERROR
```

The response is the nested `error` envelope in the schema and always includes
`details`, `retryable`, and `request_id`. Domain-specific model/tool codes are kept
inside workflow tool failure envelopes and are not alternate HTTP response shapes.

## 6. FastAPI Implementation Notes

- Use Pydantic models that mirror `schemas/*.schema.json`.
- Expose OpenAPI 3.1 docs.
- Keep schema references stable.
- Read config from `config/app_config.yaml` and `config/model_config.yaml`.
- Read plugin mapping from `config/plugins.yaml` when plugin-based tools are enabled.
- If RAG-ready retrieval is enabled, `agent_output.policy_basis` may include optional citation metadata such as `clause_id`, `citation_id`, `retrieval_score`, and `retrieval_method`.
- Persist `policy_search` retrieval results in `retrieval_logs` when the runtime records tool calls.
- Persist reviewer actions and audit events through repository methods, not direct SQL in API handlers.
- Use SQLite path from `config/app_config.yaml`.
- Do not expose secret fields such as real model API keys in API responses.
- Persist claim input and Agent output only after schema validation succeeds.
- Never expose `labels_*.jsonl` through API endpoints.
