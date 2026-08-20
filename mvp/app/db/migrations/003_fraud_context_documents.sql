-- Runtime fraud context and document-reference tables for v2 evidence integration.

CREATE TABLE IF NOT EXISTS insureds (
  insured_id TEXT NOT NULL,
  split TEXT NOT NULL CHECK (split IN ('dev', 'eval')),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (insured_id, split)
);

CREATE TABLE IF NOT EXISTS providers (
  provider_id TEXT NOT NULL,
  split TEXT NOT NULL CHECK (split IN ('dev', 'eval')),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (provider_id, split)
);

CREATE TABLE IF NOT EXISTS fraud_current_claims (
  claim_id TEXT PRIMARY KEY,
  split TEXT NOT NULL CHECK (split IN ('dev', 'eval')),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_claims (
  claim_id TEXT PRIMARY KEY,
  split TEXT NOT NULL CHECK (split IN ('dev', 'eval')),
  history_for_claim_id TEXT,
  insured_id TEXT NOT NULL,
  provider_id TEXT NOT NULL,
  receipt_id TEXT NOT NULL,
  receipt_hash TEXT NOT NULL,
  diagnosis_code TEXT NOT NULL,
  treatment_code TEXT NOT NULL,
  treatment_start_date TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_metadata (
  document_id TEXT PRIMARY KEY,
  split TEXT NOT NULL CHECK (split IN ('dev', 'eval')),
  claim_id TEXT NOT NULL,
  document_type TEXT NOT NULL,
  file_path TEXT NOT NULL,
  content_hash TEXT,
  text_fingerprint TEXT,
  perceptual_hash TEXT,
  mime_type TEXT NOT NULL,
  file_size INTEGER NOT NULL CHECK (file_size >= 0),
  page_count INTEGER NOT NULL CHECK (page_count >= 0),
  document_status TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_documents (
  claim_id TEXT NOT NULL,
  document_id TEXT NOT NULL,
  split TEXT NOT NULL CHECK (split IN ('dev', 'eval')),
  document_type TEXT NOT NULL,
  created_at TEXT NOT NULL,
  PRIMARY KEY (claim_id, document_id)
);

CREATE TABLE IF NOT EXISTS fraud_context_seed_runs (
  run_id TEXT PRIMARY KEY,
  split TEXT NOT NULL CHECK (split IN ('dev', 'eval')),
  source_files_json TEXT NOT NULL,
  row_count INTEGER NOT NULL CHECK (row_count >= 0),
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_historical_claims_history_for ON historical_claims(history_for_claim_id);
CREATE INDEX IF NOT EXISTS idx_historical_claims_provider_date ON historical_claims(provider_id, treatment_start_date);
CREATE INDEX IF NOT EXISTS idx_historical_claims_insured_provider_date ON historical_claims(insured_id, provider_id, treatment_start_date);
CREATE INDEX IF NOT EXISTS idx_document_metadata_claim_id ON document_metadata(claim_id);
CREATE INDEX IF NOT EXISTS idx_claim_documents_claim_id ON claim_documents(claim_id);
