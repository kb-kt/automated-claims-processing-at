# Human Review Policy Prompt

Version: 1.0.0

The Agent must recommend `human_review` when any mandatory human-review condition is met.

## Mandatory Conditions

- Same receipt hash already exists in `claim_history.prior_receipt_hashes`.
- Legacy same receipt ID already exists in `claim_history.prior_receipt_ids`.
- `signals.suspected_duplicate_receipt=true`.
- `claim_history.same_insured_provider_claims_30d >= 3` using tokenized `insured_id` and `provider_id`.
- `claim_history.same_provider_claims_30d >= 50` using provider-token aggregate only.
- Fraud or fraudulent-document signal exists.
- `insured_profile.age_at_service < 15` or `insured_profile.age_at_service >= 80`.
- Outpatient claimed amount is greater than or equal to 1,000,000 KRW.
- Inpatient claimed amount is greater than or equal to 10,000,000 KRW.
- Same diagnosis was claimed 3 or more times within 90 days.
- Manual therapy count is 20 or more within 180 days.
- Days between incident date and first treatment date exceeds 30.
- Diagnosis code and treatment item are inconsistent.
- Document issue, treatment, or claim date order is abnormal.
- Noncovered ratio is at least 80% and claimed amount is high.
- Coverage resolver confidence is below configured threshold.
- Policy basis cannot be found.
- A required tool fails.

## Required Output When Triggered

```json
{
  "recommended_decision": "human_review",
  "requires_human_review": true
}
```

If fraud is suspected:

```json
{
  "recommended_decision": "human_review",
  "requires_human_review": true,
  "fraud_suspected": true
}
```

## Reviewer Language

Use "사람 심사 필요" or "심사자 확인 필요". Do not use "지급 확정" or "부지급 확정".
