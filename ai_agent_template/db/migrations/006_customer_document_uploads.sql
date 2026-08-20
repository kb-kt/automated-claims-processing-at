-- Customer-uploaded PDF metadata. File bytes remain in the configured runtime document store.
CREATE TABLE IF NOT EXISTS uploaded_document_metadata (
  document_id TEXT PRIMARY KEY,
  claim_id TEXT NOT NULL,
  document_type TEXT NOT NULL,
  file_path TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  text_fingerprint TEXT NOT NULL DEFAULT '',
  perceptual_hash TEXT NOT NULL DEFAULT '',
  mime_type TEXT NOT NULL CHECK (mime_type = 'application/pdf'),
  file_size INTEGER NOT NULL CHECK (file_size > 0),
  page_count INTEGER NOT NULL CHECK (page_count > 0),
  document_status TEXT NOT NULL CHECK (document_status IN ('available', 'missing', 'corrupted', 'password_protected')),
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_uploaded_document_claim
  ON uploaded_document_metadata(claim_id, document_type, document_id);
