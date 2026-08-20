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
  "review_status": "completed | failed | human_review_required",
  "status": "completed | failed | human_review_required",
  "output": "claim_review_output",
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

`output` is the canonical field. `agent_output` is retained as a compatibility alias in Starter Kit and MVP responses.

## `ClaimReviewOutput` Confidence Fields

`claim_review_output` may include:

- `confidence`: deterministic tool/rule confidence used for reviewer triage.
- `confidence_assessment`: LLM-assisted explanation of evidence clarity, judgment difficulty, and uncertainty while preserving deterministic confidence.
- `explanation_confidence`: validation score for whether LLM-generated explanation text remains faithful to tool/rule output, policy citations, and calculation values.

LLM self-confidence must not replace `confidence`.

## `ReviewerActionRequest`

```json
{
  "action": "accept_recommendation | modify_recommendation | request_documents | defer | mark_human_review",
  "reviewer_id": "string",
  "reviewer_note": "string",
  "override_decision": "pay | partial_pay | request_documents | deny | human_review",
  "override_payable_amount": 0
}
```

## FastAPI Mapping

- Use Pydantic models generated from JSON Schema or manually maintained Pydantic models.
- Keep field names identical to JSON Schema.
- Top-level API envelope fields such as `review_status`, `output`, `agent_output`, and `errors` are API DTO fields. The nested review object must remain valid against `claim_review_output.schema.json`.
