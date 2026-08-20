# Operations Template Guide

The executable operational baseline and incident procedures are maintained in `docs/OPERATIONS_RUNBOOK.md`.

Version: 1.0.0

This document describes how MVP developers should use the Template artifacts.

## 1. Runtime Configuration

Detailed configuration guidance is maintained in:

```text
docs/CONFIGURATION.md
```

Application config:

```text
config/app_config.yaml
```

Model config:

```text
config/model_config.yaml
```

Plugin config for Starter Kit and MVP runtime:

```text
developer_kit/starter_kit/config/plugins.yaml
mvp/config/plugins.yaml
```

SQLite path:

```text
runtime/agent_template.sqlite3
```

Docker is intentionally disabled for the current phase.

Secrets such as real model API keys must be injected through environment variables or a secret manager, not committed into config files.

## 2. Prompt Assembly

Recommended prompt order:

1. `prompts/system_prompt.md`
2. `prompts/human_review_policy_prompt.md`
3. `prompts/output_format_prompt.md`
4. `prompts/claim_review_prompt.md`
5. Claim input and tool results

## 3. Workflow Execution

Use:

```text
workflows/claim_review_workflow.yaml
```

The MVP workflow engine may be simple Python code, LangGraph, or another orchestration layer. It must preserve the step order and failure policies.

## 4. Persistence

If persistence is enabled:

1. Validate claim input.
2. Store claim input in `claim_reviews`.
3. Execute workflow.
4. Store tool calls in `tool_call_logs`.
5. Validate Agent output.
6. Store final output in `agent_outputs`.
7. Store reviewer action in `reviewer_actions`.

## 5. UI Usage

Customer UI uses:

```text
ui/customer_claim_screen.md
examples/customer_claim_input.example.json
```

Reviewer UI uses:

```text
ui/reviewer_assistant_screen.md
examples/reviewer_assistant_output.example.json
```
