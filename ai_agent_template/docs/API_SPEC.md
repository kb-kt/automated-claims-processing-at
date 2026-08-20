# Claim Review API Specification

Version: 1.0.0  
Status: Baseline Contract  
OpenAPI: 3.1.0  
JSON Schema: Draft 2020-12

## Contract Authority

The machine-readable operation manifest is `schemas/api_surface.contract.json`. Claim input and Agent output are governed by `claim_review_input.schema.json` and `claim_review_output.schema.json`. This document replaces `API_SPEC_DRAFT.md` as the baseline contract; the draft remains historical reference only.

## Canonical Review DTO

`POST /reviews`, `POST /reviews/{claim_id}/rerun`, and successful review retrieval use the following compatibility envelope:

```json
{
  "claim_id": "string",
  "review_status": "completed | human_review_required | found",
  "status": "completed | human_review_required | found",
  "output": {},
  "agent_output": {},
  "errors": []
}
```

`output` is canonical. `agent_output` is an identical compatibility alias. The nested object must validate against `claim_review_output.schema.json`.

## Customer PDF Upload

Starter Kit and MVP expose the same raw-PDF upload contract after a claim has been accepted:

```text
POST /claims/{claim_id}/documents?document_type=medical_receipt
Content-Type: application/pdf
Body: PDF bytes
```

Successful uploads return `201` with `document_id`, `claim_id`, `document_type`, SHA-256 `content_hash`, MIME type, file size, page count, and availability status. The service accepts only registered document types and structurally valid PDFs within `CLAIMS_INTERNAL_MAX_DOCUMENT_BYTES`. It stores bytes under the configured runtime document root and stores only relative paths and integrity metadata in SQLite.

Uploading a `medical_receipt` synchronizes the persisted claim `receipt_hash` with the actual PDF SHA-256. Uploaded document types are added to the persisted claim `documents` list before review. Customer API keys may call this upload operation but may not read arbitrary claims.

## Product And Policy Catalog

Starter Kit and MVP expose the same read-only catalog operations:

```text
GET /products
GET /products/{product_id}
GET /products/{product_id}/policies
```

The source is `data_generator/generated/products/product_catalog.json`, product-specific
JSON files, and `policies.jsonl`. Customer, reviewer, and admin roles may read this
catalog. Claim submission validates that both IDs exist and that `policy_id` belongs
to the submitted `product_id`. UI fields remain editable through HTML datalist inputs,
but an unregistered or mismatched pair is rejected with `VALIDATION_ERROR` or
`NOT_FOUND` before persistence.

## Security

Local/demo mode keeps public API authentication disabled. Operational mode enables environment-key RBAC:

- customer: submit claims and attach PDFs to an accepted claim
- reviewer: read claims, run reviews, record reviewer actions, inspect standards/configuration
- admin: all public API operations including evaluation and demo administration

The internal fraud-context/document API keeps its separate `CLAIMS_INTERNAL_API_KEY` contract. API keys must only be supplied through environment variables and must never appear in OpenAPI examples, logs, SQLite rows, or audit metadata.

## Errors

Authentication failures return `401 AUTHENTICATION_REQUIRED`. Authenticated callers without the required role receive `403 ACCESS_FORBIDDEN`. All public and internal HTTP errors use the nested `error` envelope defined in `api/errors.md` and `schemas/api_error.schema.json`, including `details`, `retryable`, and a correlation `request_id`. Tool and workflow failure envelopes remain separate domain contracts; a safety-critical tool failure routes the review to `human_review` instead of being disguised as a successful low-risk report.

## Compatibility

The Starter Kit and MVP may expose additional endpoints, but every operation in `api_surface.contract.json` must remain present. Breaking field or operation changes require a new API contract version and a migration note.
