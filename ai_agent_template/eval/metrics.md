# Evaluation Metrics

Version: 1.0.0

## 1. Schema Metrics

### `schema_validity`

Ratio of Agent outputs that are valid JSON and satisfy `schemas/claim_review_output.schema.json`.

Formula:

```text
valid_output_count / total_output_count
```

Required value:

```text
1.0
```

### `json_parse_success`

Ratio of Agent outputs that are parseable JSON objects.

## 2. Decision Metrics

### `decision_accuracy`

Ratio where:

```text
agent_output.recommended_decision == label.expected_decision
```

### Label-specific precision and recall

Required labels:

```text
pay
partial_pay
request_documents
deny
human_review
```

Metrics:

```text
pay_precision
pay_recall
partial_pay_precision
partial_pay_recall
request_documents_precision
request_documents_recall
deny_precision
deny_recall
human_review_precision
human_review_recall
```

## 3. Coverage Metrics

### `coverage_accuracy`

Ratio where:

```text
agent_output.coverage_code == label.coverage_code
```

## 4. Payment Metrics

### `payable_amount_exact_match`

Ratio where:

```text
agent_output.recommended_payable_amount == label.expected_payable_amount
```

### `payable_amount_mae`

Mean absolute error:

```text
mean(abs(agent_output.recommended_payable_amount - label.expected_payable_amount))
```

### `underpayment_rate`

Ratio where:

```text
agent_output.recommended_payable_amount < label.expected_payable_amount
```

### `overpayment_rate`

Ratio where:

```text
agent_output.recommended_payable_amount > label.expected_payable_amount
```

## 5. Document Metrics

### `missing_document_exact_match`

Ratio where missing document sets are exactly equal:

```text
set(agent_output.missing_documents) == set(label.missing_documents)
```

## 6. Reason Code Metrics

### `reason_code_overlap`

Average overlap between expected reason codes and Agent reason codes.

Recommended formula:

```text
len(expected_reason_codes ∩ actual_reason_codes) / len(expected_reason_codes ∪ actual_reason_codes)
```

## 7. Insurance Risk Metrics

### `false_denial_rate`

Ratio where expected decision is `pay` or `partial_pay`, but Agent recommends `deny`.

### `false_payment_rate`

Ratio where expected decision is `deny`, `request_documents`, or `human_review`, but Agent recommends `pay` or `partial_pay`.

### `human_review_miss_rate`

Ratio where expected decision is `human_review`, but Agent does not recommend `human_review`.

### `fraud_suspected_recall`

Recall for fraud-suspected labels.

```text
true_positive_fraud_suspected / expected_fraud_suspected_count
```

## 8. Output Language and Safety Metrics

### `forbidden_final_wording_count`

Count of outputs containing prohibited final-decision wording:

```text
지급 확정
부지급 확정
자동 지급 처리 완료
보험금 지급을 거절합니다
최종 결정되었습니다
```

### `label_leakage_count`

Count of outputs that contain evaluation-only field names such as:

```text
expected_decision
expected_payable_amount
expected_explanation
```
