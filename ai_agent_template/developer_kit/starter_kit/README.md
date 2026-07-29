# AI Agent Starter Kit

FastAPI-based starter project for building an MVP from `ai_agent_template`.

The starter kit uses:

- Claim Agent SDK
- Synthetic tool plugins
- RAG-ready keyword policy retriever
- SQLite local runtime storage
- Customer and reviewer prototype screens

## Local Run

```text
cd ai_agent_template/developer_kit/sdk
python -m pip install -e .

cd ../starter_kit
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

The Starter Kit bootstraps the repository root onto `sys.path`, so the command above works from the `starter_kit` directory.

Alternative run from the repository root:

```text
python -m uvicorn ai_agent_template.developer_kit.starter_kit.app.main:app --reload --port 8000
```

FastAPI is intentionally listed as a starter dependency, not a template dependency.

## RAG-ready Path

The Starter Kit injects `KeywordPolicyRetriever` into `WorkflowRunner` when policy chunks can be built from the template's data generator candidates. If retrieval is unavailable, `policy_search` falls back to the existing synthetic policy basis.

See:

```text
ai_agent_template/docs/RAG_READY.md
```

## Tests

```text
python -m unittest discover -s ai_agent_template/developer_kit/starter_kit/tests
```
