# Field Naming Standard

## General

- JSON field names use `snake_case`.
- Decision values use lowercase snake case.
- Reason codes use uppercase snake case.
- Coverage codes use uppercase snake case with `COV_` prefix.
- Document codes use lowercase snake case.
- Money values are KRW integer values.
- Dates use `YYYY-MM-DD`.
- Datetimes use ISO-8601 UTC strings.

## Reserved Prefixes

- `recommended_`: Agent recommendation fields.
- `expected_`: evaluation labels only. Never include these in Agent input.
- `COV_`: coverage codes.
- `HR_`: human review rule IDs.

## Field Separation

- Customer-facing payloads must not expose fraud result fields.
- Reviewer-facing payloads may expose fraud and risk reason codes.
- Evaluation labels are not available to Agent runtime.
