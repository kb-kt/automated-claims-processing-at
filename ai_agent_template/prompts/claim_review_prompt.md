# Claim Review Prompt

Version: 1.0.0

Use this prompt after the workflow has validated input and collected tool results.

## Inputs

You will receive:

- `claim_review_input`: a JSON object matching `schemas/claim_review_input.schema.json`
- `policy_search_result`
- `coverage_resolver_result`
- `document_checker_result`
- `exclusion_checker_result`
- `payable_calculator_result`
- `risk_checker_result`
- `fraud_signal_checker_result`
- `output_schema`: `schemas/claim_review_output.schema.json`

## Task

Create one reviewer-facing claim review recommendation JSON object.

Follow this priority order:

1. If fraud or duplicate signal is present, recommend `human_review`.
2. If policy is lapsed or outside coverage period, recommend `deny` unless a higher-risk fraud condition requires `human_review`.
3. If required documents are missing, recommend `request_documents`.
4. If clear exclusion applies, recommend `deny`.
5. If mandatory human-review risk applies, recommend `human_review`.
6. If payable calculation applies a claim limit or other partial-payment reason, recommend `partial_pay`.
7. Otherwise recommend `pay`.

## Required Output Mapping

- `claim_id`: copy from input.
- `recommended_decision`: one allowed decision.
- `recommended_payable_amount`: copy from `payable_calculator_result.payable_amount`, or `0` if calculation is unavailable and the decision is not payable.
- `coverage_code`: copy from `coverage_resolver_result.coverage_code`.
- `coverage_name`: copy from `coverage_resolver_result.coverage_name`.
- `missing_documents`: copy from `document_checker_result.missing_documents`.
- `reason_codes`: combine standardized codes from tool results and decision logic.
- `requires_human_review`: true only when human review is required.
- `fraud_suspected`: copy from `fraud_signal_checker_result.fraud_suspected`.
- `confidence`: use the lower of coverage confidence and your output confidence, between 0.0 and 1.0.
- `calculation`: copy from `payable_calculator_result`.
- `policy_basis`: use `policy_search_result.matches`; preserve `citation_id`, `clause_id`, `retrieval_score`, and `retrieval_method` when present.
- `review_summary`: Korean reviewer-facing summary.
- `reviewer_notes`: concise Korean notes for the human reviewer.

## Invariants

- If `recommended_decision=request_documents`, `missing_documents` must not be empty.
- If `fraud_suspected=true`, `requires_human_review=true`.
- If `requires_human_review=true`, `recommended_decision=human_review`.
- `recommended_payable_amount` must equal `calculation.payable_amount`.
- Do not create reason codes not listed in `standards/reason_codes.yaml`.
- Do not invent policy citations. If no reliable policy basis is available, recommend `human_review`.
- Do not use final-decision wording.

## Output

Return only the JSON object.
