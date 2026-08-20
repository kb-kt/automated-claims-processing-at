# Completeness Gates

## Purpose

This document defines the immediately enforceable P0 completion gates shared by the AI Agent Template and MVP. The Template owns the contracts and safety policy. MVP consumes the same SDK validators and threshold file.

## P0 Gates

1. `TemplateContractValidator` validates every Draft 2020-12 schema, workflow-to-tool mapping, prompt reference, core tool contract, and specialist contract.
2. Every decision-critical tool contract uses `failure_policy=human_review`. The workflow routes every core tool failure to `human_review`.
3. `LabelLeakageGuard` rejects nested `expected_*`, ground-truth, gold-label, and answer-label fields before claim persistence, workflow execution, prompt construction, or tool execution.
4. `ReleaseGate` evaluates the Template-owned `eval/thresholds.yaml`. Hard thresholds and critical failure limits block release; soft thresholds remain visible but non-blocking.
5. `scripts/run_quality_gates.py` runs Data Generator, Template, MVP, and integration suites in that order. `.github/workflows/quality-gates.yml` applies the same sequence in CI.
6. `validate_startup_configuration` checks Template contracts, plugin completeness, specialist configuration, active model configuration, retrieval values, document size limits, and `fail_closed=true` before the FastAPI app becomes ready.

## Failure Criticality

| Component | Failure behavior |
|---|---|
| Policy, coverage, fraud, document, exclusion, calculation, risk, decision validation tools | Force `human_review` |
| Medical registry enrichment | Continue collecting available evidence, then force `human_review` |
| Specialist Agent | Emit a failed specialist report and force `human_review` |
| Document extraction required by a specialist | Failed/low-confidence evidence is surfaced to the specialist and must route to reviewer confirmation |
| LLM narrative assistance | Continue with locked deterministic output, add a reviewer warning, and audit the model failure as advisory |

The LLM narrative layer is advisory and cannot change decision, calculation, fraud, policy basis, or human-review fields. Its failure therefore cannot create an unsafe automatic decision. If a future workflow promotes a model to a decision-critical role, its failure policy must be changed to `human_review` before activation.

## Label Isolation

Runtime claims, document metadata, DB seed rows, prompts, tool requests, tool responses, and public runtime APIs must not contain evaluation answers. Runtime document metadata uses the observed `readable` field; `expected_readable` is not permitted. Label files remain evaluation-harness inputs only.

Demo scenario expectations are confined to the separately mounted demo configuration and `/ui/demo` verification surface. They must not be saved as claim payloads or passed to tools/models.

## Commands

```powershell
python scripts\run_quality_gates.py
```

Individual suites:

```powershell
python -m unittest discover -s data_generator\tests
python -m unittest discover -s ai_agent_template
python -m unittest discover -s mvp\tests
python -m unittest discover -s integration_tests
```

The release gate configuration is maintained only at `ai_agent_template/eval/thresholds.yaml`. MVP must not maintain a separate threshold implementation.
