# Workflow Validation Cases

Version: 1.0.0

These cases define expected workflow behavior for MVP tests.

## Case 1: Fraud Signal Priority

Input:

```text
signals.suspected_duplicate_receipt = true
```

Expected:

```text
recommended_decision = human_review
requires_human_review = true
fraud_suspected = true
```

## Case 2: Missing Document Before Calculation

Input:

```text
missing required document and high claimed amount
```

Expected:

```text
recommended_decision = request_documents
missing_documents is not empty
```

## Case 3: Tool Failure Fallback

Input:

```text
payable_calculator fails
```

Expected:

```text
recommended_decision = human_review
reason_codes includes TOOL_FAILURE
```

## Case 4: Output Validator Failure

Input:

```text
model returns invalid JSON
```

Expected:

```text
retry once, then failed if still invalid
```

## Case 5: Final Wording Guard

Input:

```text
review_summary contains "지급 확정"
```

Expected:

```text
decision_validator rejects output
```
