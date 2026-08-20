# Integration Tests

This directory verifies compatibility between independently developed project areas.

Current scope:

```text
data_generator output ↔ ai_agent_template input schema
```

These tests intentionally avoid importing `data_generator` or `ai_agent_template` implementation modules. They read generated files and schema/standard files as external artifacts.

Run from repository root:

```powershell
python -m unittest discover -s integration_tests
```

The integration suite also verifies Template/MVP plugin profile parity, canonical review API envelope fields, and recursive label isolation across generated runtime artifacts. Run all project gates with:

```powershell
python scripts\run_quality_gates.py
```

`test_fraud_check_cross_workspace_e2e.py` starts the real Fraud_Check v2 service from the sibling workspace at `C:\Users\PC\AA\Fraud_Check` and connects it to the Claims evidence API and the MVP v2 plugin. The Fraud_Check virtual environment must exist at `.venv\Scripts\python.exe`; the test only reads and executes that workspace and does not modify it.

Run only the cross-workspace checks with:

```powershell
C:\Python314\python.exe -m unittest integration_tests.test_fraud_check_cross_workspace_e2e -v
```

The nine checks cover clean continuation, exact and altered duplicates, document mismatches, behavior thresholds, fail-closed routing, internal document API safety, label isolation, and log redaction.

Expected source artifacts:

```text
data_generator/generated/claims_dev.jsonl
data_generator/generated/claims_eval.jsonl
data_generator/generated/labels_dev.jsonl
data_generator/generated/labels_eval.jsonl
ai_agent_template/schemas/claim_review_input.schema.json
ai_agent_template/standards/*.yaml
```
