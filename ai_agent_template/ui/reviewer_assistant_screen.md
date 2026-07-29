# Reviewer Assistant Screen Prototype

Audience: insurance claim reviewer.

Purpose: show Agent recommendation, evidence, calculation, and human-review signals.

## Layout

```text
┌─────────────────────────────────────────────────────────────────────┐
│ 심사 Assistant                                                      │
├───────────────┬─────────────────────────────────────────────────────┤
│ Claim Queue   │ Claim Detail                                        │
│ - 접수됨      │  claim_id / policy_id / product_id                  │
│ - 사람심사    │  claimant synthetic ID / age / gender               │
│ - 서류요청    │  dates / claimed_amount / receipt_id                │
│ - 부지급검토  │                                                     │
├───────────────┼─────────────────────────────────────────────────────┤
│ Agent Summary │ 권고 결정: partial_pay                              │
│               │ 지급예상금액: 140,000 KRW                           │
│               │ confidence: 0.94                                    │
│               │ human_review: false                                 │
├───────────────┼─────────────────────────────────────────────────────┤
│ Calculation   │ claimed: 681,994                                    │
│               │ eligible: 200,000                                   │
│               │ deductible: 60,000                                  │
│               │ payable: 140,000                                    │
├───────────────┼─────────────────────────────────────────────────────┤
│ Evidence      │ 약관 근거                                           │
│               │ - 2.2 비급여 통원 의료비                            │
│               │ Reason codes                                        │
│               │ - COVERED_INCIDENT                                  │
│               │ - PER_CLAIM_LIMIT_APPLIED                           │
│               │ - DEDUCTIBLE_APPLIED                                │
├───────────────┼─────────────────────────────────────────────────────┤
│ Actions       │ [권고 승인] [결정 수정] [추가서류 요청] [사람심사]   │
│ Reviewer Note │                                                     │
└───────────────┴─────────────────────────────────────────────────────┘
```

## Display Rules

- `human_review=true`이면 화면 상단에 심사자 확인 필요 배지를 표시한다.
- `fraud_suspected=true`이면 지급 권고 버튼을 비활성화하고 사람심사 액션을 강조한다.
- `request_documents`이면 누락서류 목록을 먼저 표시한다.
- `deny`는 "부지급 확정"이 아니라 "부지급 검토 권고"로 표시한다.

## Reviewer Actions

- `approve_recommendation`
- `override_decision`
- `request_more_documents`
- `mark_human_review`
- `add_reviewer_note`

## Privacy-Minimized Insured Display

Reviewer detail must display tokenized insured context only:

```text
insured_profile.insured_id / insured_profile.age_at_service / insured_profile.sex
```

Do not display direct name, resident registration number, phone, address, bank account, or raw hospital identity. Repeated-claim and duplicate-receipt context should be shown through reason codes and token/hash aggregates.
