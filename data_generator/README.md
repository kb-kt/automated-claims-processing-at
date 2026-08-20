# Data Generator

`data_generator` creates synthetic indemnity-medical insurance claims for claim-review Agent development and Fraud_Check evaluation. It does not use real personal information, real hospital names, real resident registration numbers, real phone numbers, real addresses, or real insurance records.

## Generate Data

From the project root:

```powershell
python -m data_generator.src.cli generate --output data_generator\generated --dev-count 1000 --eval-count 200 --seed 20260616 --overwrite
```

Validate generated files:

```powershell
python -m data_generator.src.cli validate --input data_generator\generated
```

Run tests:

```powershell
python -m unittest discover -s data_generator\tests
```

## Outputs

Core claim-review files:

- `products.json`
- `products/product_catalog.json`
- `products/{product_id}.json`
- `policies.jsonl`
- `policy_documents.md`
- `claims_dev.jsonl`
- `claims_eval.jsonl`
- `labels_dev.jsonl`
- `labels_eval.jsonl`
- `evaluation_cases.jsonl`
- `generation_report.json`

`products.json` remains the legacy active-product file used by deterministic
plugins. The normalized `products/` catalog is the multi-product source for UI,
API, and relationship validation. `policies.jsonl` contains multiple synthetic
policies per product and the policies referenced by generated claims.

Import a legacy one-column products CSV once, then remove the CSV after review:

```powershell
python -m data_generator.src.cli import-products `
  --source data_generator\generated\products.csv `
  --policies-per-product 3
```

The command writes the durable source catalog to `data_generator/catalog/products`
and the runtime copy to `data_generator/generated/products`. Product IDs must be
unique and file-safe. Every policy must reference an existing product, and every
claim's `policy_id` must resolve to the same `product_id`; `validate` fails on any
unknown or mismatched relationship.

Fraud_Check development and evaluation files:

- `insureds.json`
- `providers.json`
- `historical_claims.jsonl`
- `document_metadata_dev.jsonl`
- `document_metadata_eval.jsonl`
- `claim_document_links_dev.jsonl`
- `claim_document_links_eval.jsonl`
- `fraud_labels_dev.jsonl`
- `fraud_labels_eval.jsonl`
- `fraud_context_seed_dev.jsonl`
- `fraud_context_seed_eval.jsonl`
- `documents/dev/{claim_id}/*.pdf`
- `documents/eval/{claim_id}/*.pdf`

Medical review, KCD/EDI mapping, policy coverage analysis, and document-understanding evaluation files:

- `medical_code_registry.json`
- `edi_code_registry.json`
- `diagnosis_treatment_rules.json`
- `medical_labels_dev.jsonl`
- `medical_labels_eval.jsonl`
- `code_mapping_labels_dev.jsonl`
- `code_mapping_labels_eval.jsonl`
- `policy_coverage_labels_dev.jsonl`
- `policy_coverage_labels_eval.jsonl`
- `medical_document_metadata_dev.jsonl`
- `medical_document_metadata_eval.jsonl`
- `document_extraction_labels_dev.jsonl`
- `document_extraction_labels_eval.jsonl`
- `medical_context_seed_dev.jsonl`
- `medical_context_seed_eval.jsonl`

Document paths in metadata are relative to `data_generator/generated`.
`document_extraction_labels_*.jsonl` is evaluation-only and must not be loaded into runtime claim payloads or exposed to the Agent.

## Fraud Scenarios

The generator guarantees at least one dev and one eval example for:

- normal clean claim
- exact duplicate receipt hash
- legacy duplicate receipt ID
- altered duplicate receipt
- forged amount
- forged treatment/issue date
- forged provider
- explicit fraudulent-document signal
- same insured and provider repeat count boundary: 2 and 3
- provider-volume boundary: 49 and 50
- complex fraud combinations
- hard negatives
- missing document
- corrupted PDF
- low-OCR scan-like PDF
- unreadable/protected document simulation

Fraud-suspected cases are labeled for `human_review`; they are not labeled for automatic denial.

## PDF Generation

PDF generation uses the Python standard library only. The generated PDFs are deterministic minimal PDFs containing structured fields such as:

- `document_id`
- `receipt_id`
- `insured_id`
- `provider_id`
- `provider_name`
- `issue_date`
- `treatment_start_date`
- `treatment_end_date`
- `diagnosis_code`
- `treatment_code`
- `claimed_amount`
- `document_type`

Every readable PDF contains `SYNTHETIC TEST DOCUMENT / 실제 사용 불가`. Metadata also marks each document as synthetic and stores content hash, normalized text fingerprint, perceptual-hash placeholder, MIME type, file size, page count, relative path, and document status.

## Label Isolation

Runtime files for Agent/Fraud_Check input:

- `claims_dev.jsonl`
- `claims_eval.jsonl`
- `historical_claims.jsonl`
- `document_metadata_dev.jsonl`
- `document_metadata_eval.jsonl`
- `fraud_context_seed_dev.jsonl`
- `fraud_context_seed_eval.jsonl`

Evaluation-only files:

- `labels_dev.jsonl`
- `labels_eval.jsonl`
- `fraud_labels_dev.jsonl`
- `fraud_labels_eval.jsonl`
- `medical_labels_dev.jsonl`
- `medical_labels_eval.jsonl`
- `code_mapping_labels_dev.jsonl`
- `code_mapping_labels_eval.jsonl`
- `policy_coverage_labels_dev.jsonl`
- `policy_coverage_labels_eval.jsonl`

Do not pass `fraud_labels_*`, `medical_labels_*`, `code_mapping_labels_*`, `policy_coverage_labels_*`, or `labels_*` to the Agent or Fraud_Check runtime. They are for evaluation harnesses only.

## Medical Review and KCD/EDI Evaluation

The generator creates synthetic KCD/EDI registries and evaluation labels for future specialist agents:

- Policy and Coverage Analysis Agent: `policy_coverage_labels_*.jsonl`
- KCD/EDI Code Mapping Agent: `code_mapping_labels_*.jsonl`
- Medical Review and Causality Agent: `medical_labels_*.jsonl`
- Document Understanding Agent: `medical_document_metadata_*.jsonl`

Runtime-safe seed files are `medical_context_seed_dev.jsonl` and `medical_context_seed_eval.jsonl`. These include submitted diagnosis/treatment codes, document references, and prior-history summaries, but they do not include expected KCD/EDI codes, expected medical decisions, or hidden reason codes.

The generated scenarios include:

- clear KCD mapping
- ambiguous KCD mapping requiring human review
- clear EDI mapping
- ambiguous EDI mapping requiring human review
- compatible diagnosis/treatment
- weakly related diagnosis/treatment
- unrelated diagnosis/treatment
- possible pre-existing condition review
- possible excessive-treatment review
- high-cost sufficient evidence
- high-cost insufficient evidence
- document-understanding failure requiring VLM/OCR review

## DB Seed Usage

Use `fraud_context_seed_dev.jsonl` or `fraud_context_seed_eval.jsonl` to seed a Fraud_Check context database. These files include individual historical claims, current claims, insured/provider synthetic records, document metadata, and claim-document links. They intentionally include source rows rather than only aggregate counters so a DB/API layer can recompute:

- `prior_receipt_ids`
- `prior_receipt_hashes`
- `same_insured_provider_claims_30d`
- `same_provider_claims_30d`
- `same_diagnosis_claims_90d`
- `manual_therapy_count_180d`

## Reproducibility

Use the same `seed` and config to recreate the same JSON rows, PDF bytes, document hashes, and fingerprints. The PDF metadata avoids runtime timestamps.

Example:

```powershell
python -m data_generator.src.cli generate --output data_generator\generated --dev-count 1000 --eval-count 200 --seed 20260616 --overwrite
```
