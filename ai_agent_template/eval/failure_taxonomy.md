# Failure Taxonomy

Version: 1.0.0

## Critical Failures

### `invalid_json`

Agent output cannot be parsed as JSON.

### `schema_invalid`

Agent output does not satisfy `claim_review_output.schema.json`.

### `label_leakage`

Agent output contains evaluation-only fields or references to labels.

### `human_review_miss`

Expected decision is `human_review`, but Agent recommends another decision.

### `fraud_miss`

Expected fraud flag is true, but Agent does not set `fraud_suspected=true`.

### `false_denial`

Expected decision is `pay` or `partial_pay`, but Agent recommends `deny`.

## Non-Critical Failures

### `coverage_mismatch`

Coverage code does not match expected label.

### `amount_mismatch`

Recommended payable amount does not match expected payable amount.

### `missing_documents_mismatch`

Missing document set does not match expected label.

### `reason_code_mismatch`

Reason codes have insufficient overlap with expected labels.

### `policy_basis_weak`

Policy basis is present but too generic or not tied to the decision.

## Remediation Mapping

| Failure | Likely Fix |
|---|---|
| invalid_json | strengthen output format prompt or response format enforcement |
| schema_invalid | improve decision validator and retry normalization |
| human_review_miss | update risk checker or human review rules |
| fraud_miss | update fraud signal checker |
| false_denial | review priority ordering and exclusion checker |
| amount_mismatch | fix payable calculator or coverage resolver |
| coverage_mismatch | improve coverage resolver |
| missing_documents_mismatch | update document checker |
