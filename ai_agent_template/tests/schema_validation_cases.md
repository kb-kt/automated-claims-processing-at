# Schema Validation Cases

Version: 1.0.0

These cases guide MVP validation tests. They are not executable tests by themselves.

## Input Schema Cases

### Valid Claim Input

Use:

```text
examples/customer_claim_input.example.json
```

Expected:

```text
valid
```

### Reject Evaluation Label Leakage

Add this field to an otherwise valid claim input:

```json
{
  "expected_decision": "pay"
}
```

Expected:

```text
invalid
```

### Reject Negative Claimed Amount

Set:

```json
{
  "claim": {
    "claimed_amount": -1
  }
}
```

Expected:

```text
invalid
```

## Output Schema Cases

### Valid Reviewer Output

Use:

```text
examples/reviewer_assistant_output.example.json
```

Expected:

```text
valid
```

### Reject Human Review Invariant Violation

Set:

```json
{
  "requires_human_review": true,
  "recommended_decision": "pay"
}
```

Expected:

```text
invalid
```

### Reject Fraud Invariant Violation

Set:

```json
{
  "fraud_suspected": true,
  "requires_human_review": false
}
```

Expected:

```text
invalid
```
