# Project Implementation Status

Last reviewed: 2026-08-15

The AI Agent Template is the authoritative product. Data Generator is an independent compatible producer, and MVP is the reference implementation consuming Template contracts.

| Area | Status | Authority | Remaining external dependency |
|---|---|---|---|
| Synthetic claim, fraud, document, medical, KCD/EDI generation | Complete | Data Generator | Real de-identified insurer adapter |
| Draft 2020-12 input/output/report schemas | Complete | Template | Insurer schema approval |
| Tool, specialist plugin, workflow contracts | Complete | Template | Insurer-approved production plugins |
| Template/MVP contract parity gates | Complete | Template/Integration | None |
| Fail-closed and label-isolation gates | Complete | Template | Operational policy approval |
| Unified evaluation release gate | Complete | Template | Real holdout thresholds |
| Startup validation and CI quality gates | Complete | Template | CI repository activation |
| API-key RBAC baseline and audit redaction | Complete baseline | Template/MVP | Enterprise IdP/OIDC and organization roles |
| Decision provenance and artifact fingerprints | Complete baseline | Template/MVP | Registry/policy approval identifiers from insurer systems |
| API specification 1.0.0 and OpenAPI parity test | Complete | Template | External consumer review |
| SQLite repository and migrations | Complete for local/MVP | Template/MVP | PostgreSQL implementation for operation |
| Fraud_Check v1/v2 boundary | Complete | Template/MVP | Live Fraud_Check service validation |
| OCR/VLM provider boundary | Complete baseline | Template/MVP | Endpoint conformance and real extraction evaluation |
| RAG-ready policy retrieval | Complete baseline | Template/MVP | Real policy ingestion, vector/hybrid retrieval, reranker |

Items marked “Complete baseline” are structurally complete for the Template/MVP scope but are not production approval claims.
