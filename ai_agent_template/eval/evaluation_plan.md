# Evaluation Plan

Version: 1.0.0

## 1. Purpose

This plan defines how to evaluate AI Agent MVPs built from the Agent Template.

## 2. Evaluation Stages

### Stage A: Contract Validation

Goal: ensure Agent output is structurally valid.

Checks:

- JSON parse success
- output schema validity
- no extra fields
- required fields present
- decision enum valid
- reason codes registered
- no evaluation label leakage

### Stage B: Functional Accuracy

Goal: compare Agent output with Data Generator labels.

Checks:

- decision accuracy
- coverage accuracy
- payable amount exact match
- missing document exact match
- reason code overlap

### Stage C: Insurance Risk Gate

Goal: detect unsafe review behavior.

Checks:

- false denial rate
- false payment rate
- human review miss rate
- fraud suspected recall
- underpayment rate
- overpayment rate

### Stage D: Reviewer Usability

Goal: ensure outputs are useful for a human reviewer.

Checks:

- policy basis present
- reviewer summary present
- no final-decision wording
- reviewer notes actionable

## 3. Datasets

Development dataset:

```text
data_generator/generated/claims_dev.jsonl
data_generator/generated/labels_dev.jsonl
```

Evaluation dataset:

```text
data_generator/generated/claims_eval.jsonl
data_generator/generated/labels_eval.jsonl
```

Holdout dataset:

```text
data_generator/generated_holdout/claims_eval.jsonl
data_generator/generated_holdout/labels_eval.jsonl
```

Holdout data should use a different seed from development data.

## 4. Required Run Metadata

Each evaluation run must record:

- `run_id`
- dataset paths
- Agent version
- prompt version
- workflow version
- schema version
- model provider
- model ID
- tool contract versions
- thresholds version

## 5. Failure Analysis

Failure cases must be grouped by:

- schema failure
- decision mismatch
- coverage mismatch
- payable amount mismatch
- missing document mismatch
- human review miss
- false denial
- false payment
- fraud miss
- reason code mismatch
- language safety failure

## 6. Release Gate

An Agent MVP can move to the next validation phase only if:

- all hard thresholds pass
- no critical failure remains unexplained
- regression from previous approved run is reviewed
- model and prompt versions are recorded
