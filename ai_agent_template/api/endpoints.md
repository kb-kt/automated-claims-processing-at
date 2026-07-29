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
  "status": "completed",
  "agent_output": "claim_review_output",
  "tool_trace": [],
  "errors": []
}
```

### `GET /api/v1/reviews/{claim_id}`

Returns the latest Agent output for the claim.

### `POST /api/v1/reviews/{claim_id}/rerun`

Reruns the workflow with the current model and prompt configuration.

## Reviewer Actions

- `POST /api/v1/reviews/{claim_id}/approve`
- `POST /api/v1/reviews/{claim_id}/override`
- `POST /api/v1/reviews/{claim_id}/request-human-review`

## Config

- `GET /api/v1/configs/model`
- `PUT /api/v1/configs/model`
- `GET /api/v1/standards/reason-codes`

## Evaluation

- `POST /api/v1/evaluations/runs`
- `GET /api/v1/evaluations/runs/{run_id}`
