# Standardization Guide

Version: 1.0.0

This document explains how the Agent Template standard files should be used.

## 1. Registry Files

```text
standards/decision_codes.yaml
standards/reason_codes.yaml
standards/document_codes.yaml
standards/coverage_codes.yaml
standards/field_naming.md
```

These files are source-of-truth registries for Agent MVP implementation.

## 2. Decision Codes

Decision codes are lowercase snake case:

```text
pay
partial_pay
request_documents
deny
human_review
```

Never add a new decision code without updating:

- `standards/decision_codes.yaml`
- `schemas/claim_review_output.schema.json`
- evaluator decision mapping
- API documentation

## 3. Reason Codes

Reason codes are uppercase snake case. They must be listed in `standards/reason_codes.yaml`.

Agent output must not contain unregistered reason codes.

## 4. Coverage Codes

Coverage codes must remain compatible with Data Generator product definitions.

Initial coverage registry:

```text
COV_OUTPATIENT_COVERED
COV_OUTPATIENT_NONCOVERED
COV_PRESCRIPTION
COV_INPATIENT_COVERED
COV_INPATIENT_NONCOVERED
COV_SPECIAL_MANUAL_THERAPY
COV_SPECIAL_INJECTION
COV_SPECIAL_MRI_MRA
```

## 5. Document Codes

Document codes are lowercase snake case and must be stable across UI, Agent tools, and evaluator.

## 6. Versioning

Use semantic versioning for:

- schemas
- prompts
- workflows
- tool contracts
- model config
- standard registries

Changing field names, enum values, or output invariants requires a major version bump.
