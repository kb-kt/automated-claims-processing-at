# Output Format Prompt

Version: 1.0.0

Return exactly one JSON object in the following shape. The object must satisfy `schemas/claim_review_output.schema.json`.

```json
{
  "claim_id": "string",
  "recommended_decision": "pay | partial_pay | request_documents | deny | human_review",
  "recommended_payable_amount": 0,
  "coverage_code": "string",
  "coverage_name": "string",
  "missing_documents": [],
  "reason_codes": [],
  "requires_human_review": false,
  "fraud_suspected": false,
  "confidence": 0.0,
  "calculation": {
    "claimed_amount": 0,
    "eligible_amount": 0,
    "limit_applied": false,
    "deductible_amount": 0,
    "payable_amount": 0
  },
  "policy_basis": [
    {
      "source": "policy_documents.md",
      "section": "string",
      "summary": "string",
      "citation_id": "optional string",
      "clause_id": "optional string",
      "retrieval_score": 0.0,
      "retrieval_method": "keyword | vector | hybrid | structured"
    }
  ],
  "review_summary": "string",
  "reviewer_notes": []
}
```

## Formatting Rules

- JSON only.
- No markdown.
- No comments.
- No trailing commas.
- No extra fields beyond `schemas/claim_review_output.schema.json`.
- No omitted required fields.
- Use KRW integer values for money.
- Use standardized codes from `standards/*.yaml`.
- Preserve optional `policy_basis` citation metadata when tool results provide it.
