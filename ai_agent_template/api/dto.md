# API DTO Draft

## `ClaimReviewRequest`

```json
{
  "claim": "claim_review_input",
  "policy_document_ref": "string",
  "options": {
    "model_provider": "string",
    "model_name": "string",
    "strict_schema": true,
    "force_human_review": false
  }
}
```

## `ClaimReviewResponse`

```json
{
  "request_id": "string",
  "claim_id": "string",
  "status": "completed | failed | human_review_required",
  "agent_output": "claim_review_output",
  "tool_trace": [
    {
      "tool_name": "string",
      "status": "success | failed | skipped",
      "duration_ms": "integer"
    }
  ],
  "errors": []
}
```

## FastAPI Mapping

- Use Pydantic models generated from JSON Schema or manually maintained Pydantic models.
- Keep field names identical to JSON Schema.
- Do not add response fields that are unavailable in `claim_review_output.schema.json`.
