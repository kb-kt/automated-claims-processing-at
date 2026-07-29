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

Expected source artifacts:

```text
data_generator/generated/claims_dev.jsonl
data_generator/generated/claims_eval.jsonl
data_generator/generated/labels_dev.jsonl
data_generator/generated/labels_eval.jsonl
ai_agent_template/schemas/claim_review_input.schema.json
ai_agent_template/standards/*.yaml
```
