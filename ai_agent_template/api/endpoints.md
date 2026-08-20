# FastAPI Endpoint Draft

Framework: FastAPI

Base prefix: `/api/v1`

## Claims

### `POST /api/v1/claims`

Registers a claim review input payload.

Request body: `claim_review_input.schema.json`

Response:

```json
{
  "claim_id": "CLM-EVAL-EXAMPLE-0001",
  "status": "received"
}
```

### `GET /api/v1/claims/{claim_id}`

Returns the stored claim payload and processing status.

### `GET /api/v1/claims`

Returns recently submitted claims.

## Reviews

### `POST /api/v1/reviews`

Runs the claim review workflow and returns reviewer-facing Agent output.

Request body:

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

Response body:

```json
{
  "request_id": "REQ-000001",
  "claim_id": "CLM-EVAL-EXAMPLE-0001",
  "review_status": "completed",
  "status": "completed",
  "output": "claim_review_output",
  "agent_output": "claim_review_output",
  "tool_trace": [],
  "errors": []
}
```

`output` is the canonical response field. `agent_output` may be returned by Starter Kit and MVP implementations for backward compatibility with earlier template clients.

### `GET /api/v1/reviews/queue`

Returns reviewer worklist items with masked policy identifiers, SLA status, priority score, and latest recommendation metadata.

### `GET /api/v1/reviews/{claim_id}`

Returns the latest Agent output for the claim.

### `POST /api/v1/reviews/{claim_id}/rerun`

Reruns the workflow with the current model and prompt configuration.

## Reviewer Actions

### `POST /api/v1/reviews/{claim_id}/actions`

Stores a reviewer action.

```json
{
  "action": "accept_recommendation",
  "reviewer_id": "reviewer-001",
  "reviewer_note": "string",
  "override_decision": "pay",
  "override_payable_amount": 100000
}
```

Allowed `action` values:

- `accept_recommendation`
- `modify_recommendation`
- `request_documents`
- `defer`
- `mark_human_review`

### `GET /api/v1/reviews/{claim_id}/actions`

Returns reviewer action history.

### `GET /api/v1/reviews/{claim_id}/audit-logs`

Returns audit logs related to the claim.

## Config

- `GET /api/v1/configs/model`
- `PUT /api/v1/configs/model`
- `GET /api/v1/standards/reason-codes`

## Evaluation

- `POST /api/v1/evaluations/runs`
- `GET /api/v1/evaluations/runs/{run_id}`
