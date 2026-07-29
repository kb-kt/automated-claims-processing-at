# API Specification Draft

Version: 1.0.0

Framework target: FastAPI

OpenAPI target: 3.1.0

JSON Schema target: Draft 2020-12

This draft defines the API surface expected for the future AI Agent MVP. It is not an implemented API yet.

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
| GET | `/claims/{claim_id}` | Retrieve claim status and payload |
| POST | `/reviews` | Run claim review workflow |
| GET | `/reviews/{claim_id}` | Retrieve latest review output |
| POST | `/reviews/{claim_id}/rerun` | Rerun review workflow |
| POST | `/reviews/{claim_id}/approve` | Reviewer approves recommendation |
| POST | `/reviews/{claim_id}/override` | Reviewer overrides recommendation |
| POST | `/reviews/{claim_id}/request-human-review` | Mark claim as human review |
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
  "status": "completed",
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

### 4.5 `ReviewerOverrideRequest`

```json
{
  "override_decision": "pay | partial_pay | request_documents | deny | human_review",
  "override_payable_amount": 0,
  "reviewer_note": "string"
}
```

## 5. Error Handling

Error response schema:

```text
schemas/api_error.schema.json
```

Standard error codes:

```text
VALIDATION_ERROR
SCHEMA_VERSION_UNSUPPORTED
POLICY_DOCUMENT_NOT_FOUND
COVERAGE_RESOLUTION_FAILED
LOW_CONFIDENCE_COVERAGE_MATCH
DOCUMENT_CHECK_FAILED
EXCLUSION_CHECK_FAILED
PAYABLE_CALCULATION_FAILED
RISK_CHECK_FAILED
MODEL_PROVIDER_ERROR
MODEL_OUTPUT_INVALID_JSON
DECISION_VALIDATION_FAILED
TOOL_TIMEOUT
INTERNAL_ERROR
```

## 6. FastAPI Implementation Notes

- Use Pydantic models that mirror `schemas/*.schema.json`.
- Expose OpenAPI 3.1 docs.
- Keep schema references stable.
- Read config from `config/app_config.yaml` and `config/model_config.yaml`.
- Read plugin mapping from `config/plugins.yaml` when plugin-based tools are enabled.
- If RAG-ready retrieval is enabled, `agent_output.policy_basis` may include optional citation metadata such as `clause_id`, `citation_id`, `retrieval_score`, and `retrieval_method`.
- Use SQLite path from `config/app_config.yaml`.
- Do not expose secret fields such as real model API keys in API responses.
- Persist claim input and Agent output only after schema validation succeeds.
- Never expose `labels_*.jsonl` through API endpoints.
