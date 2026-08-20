# Operations Runbook

Version: 1.0.0

## 1. Preflight

```powershell
python scripts\check_environment.py
python scripts\run_quality_gates.py
```

Confirm that labels are not configured as runtime inputs and that `CLAIM_AGENT_PLUGIN_CONFIG` / `CLAIM_MVP_PLUGIN_CONFIG` selects the intended synthetic, Fraud v1, or Fraud v2 profile.

## 2. Local Startup

Starter Kit:

```powershell
python -m uvicorn ai_agent_template.developer_kit.starter_kit.app.main:app --host 127.0.0.1 --port 8000
```

MVP:

```powershell
python -m uvicorn mvp.app.main:app --host 127.0.0.1 --port 8001
```

Check `/health` and `/ready` before accepting claims.

## 3. Public API Authentication

Authentication is disabled by default for local demos. Enable it only after setting role keys:

```powershell
$env:CLAIM_MVP_AUTH_ENABLED = "true"
$env:CLAIM_MVP_CUSTOMER_API_KEY = "<runtime-secret>"
$env:CLAIM_MVP_REVIEWER_API_KEY = "<runtime-secret>"
$env:CLAIM_MVP_ADMIN_API_KEY = "<runtime-secret>"
```

Starter Kit uses the equivalent `CLAIM_AGENT_*` names. Never place actual keys in YAML, source files, screenshots, command history examples, or audit metadata. Internal Fraud APIs continue to use `CLAIMS_INTERNAL_API_KEY` independently.

## 4. Database Migration and Seed

SQLite migrations run during repository initialization and are idempotent. Confirm applied revisions in `/ready`. Fraud and medical registry seed commands are documented in the Starter Kit README. Evaluation label files must never be seeded into runtime tables.

## 5. Backup

Stop the application or obtain an SQLite-consistent snapshot, then copy the explicitly configured DB file to a timestamped backup directory. Back up `CLAIM_AGENT_DOCUMENT_STORAGE_DIR` or `CLAIM_MVP_DOCUMENT_STORAGE_DIR` together with the DB because uploaded PDF bytes are not stored in SQLite. Generated synthetic documents remain a separate reproducible dataset. Record the application, schema, workflow, policy, plugin, and registry versions with the backup.

## 6. Restore

Stop the application, verify the selected backup belongs to the intended environment, preserve the current DB as a rollback copy, restore the DB and document tree together, then start the service and check `/ready`. Run a read-only claim/review lookup before processing new work.

## 7. Dependency Failure

- Core tool, medical registry, document extraction, or specialist failure: verify final routing is `human_review`.
- LLM narrative failure: deterministic recommendation remains, reviewer warning and advisory failure audit metadata must exist.
- Fraud_Check failure: do not switch to synthetic output in remote mode; retain fail-closed routing.
- VLM failure: retain extraction failure evidence and route decision-critical cases to reviewer confirmation.

## 8. Incident Evidence

Collect request ID, claim ID, audit event IDs, safe tool status/error code/duration, contract version, workflow hash, prompt hash, model ID, and policy fingerprints. Do not collect Authorization headers, API keys, raw document bytes, full OCR text, or direct insured identifiers in general logs.

## 9. Evaluation and Release

Run the complete quality gate. Release is blocked when any hard threshold or critical failure limit in `ai_agent_template/eval/thresholds.yaml` fails. Preserve the evaluation run ID, dataset version, output artifacts, and release-gate result.

## 10. Data Reset

Use only explicitly resolved runtime DB and report paths. Stop the service before replacing a DB. Never delete the workspace root or generated source datasets as part of a runtime reset. Re-run migrations and the required seed loaders after creating a new empty database.
