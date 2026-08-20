PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  applied_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_reviews (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT NOT NULL UNIQUE,
  policy_id TEXT NOT NULL,
  product_id TEXT NOT NULL,
  input_payload_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('received', 'reviewing', 'completed', 'failed', 'human_review_required')),
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_outputs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT NOT NULL,
  output_payload_json TEXT NOT NULL,
  recommended_decision TEXT NOT NULL CHECK (recommended_decision IN ('pay', 'partial_pay', 'request_documents', 'deny', 'human_review')),
  recommended_payable_amount INTEGER NOT NULL CHECK (recommended_payable_amount >= 0),
  coverage_code TEXT NOT NULL,
  requires_human_review INTEGER NOT NULL CHECK (requires_human_review IN (0, 1)),
  fraud_suspected INTEGER NOT NULL CHECK (fraud_suspected IN (0, 1)),
  confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
  prompt_version TEXT NOT NULL,
  workflow_version TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  model_provider TEXT NOT NULL,
  model_name TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (claim_id) REFERENCES claim_reviews(claim_id)
);

CREATE TABLE IF NOT EXISTS tool_call_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT NOT NULL,
  tool_name TEXT NOT NULL,
  tool_version TEXT NOT NULL,
  request_json TEXT NOT NULL,
  response_json TEXT,
  status TEXT NOT NULL CHECK (status IN ('success', 'failed', 'skipped')),
  error_code TEXT,
  duration_ms INTEGER,
  created_at TEXT NOT NULL,
  FOREIGN KEY (claim_id) REFERENCES claim_reviews(claim_id)
);

CREATE TABLE IF NOT EXISTS reviewer_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT NOT NULL,
  reviewer_id TEXT,
  action TEXT NOT NULL CHECK (action IN ('accept_recommendation', 'modify_recommendation', 'request_documents', 'defer', 'mark_human_review')),
  override_decision TEXT CHECK (override_decision IS NULL OR override_decision IN ('pay', 'partial_pay', 'request_documents', 'deny', 'human_review')),
  override_payable_amount INTEGER CHECK (override_payable_amount IS NULL OR override_payable_amount >= 0),
  reviewer_note TEXT,
  action_payload_json TEXT,
  created_at TEXT NOT NULL,
  FOREIGN KEY (claim_id) REFERENCES claim_reviews(claim_id)
);

CREATE TABLE IF NOT EXISTS retrieval_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT,
  query TEXT NOT NULL,
  result_json TEXT NOT NULL,
  citation_count INTEGER NOT NULL CHECK (citation_count >= 0),
  created_at TEXT NOT NULL,
  FOREIGN KEY (claim_id) REFERENCES claim_reviews(claim_id)
);

CREATE TABLE IF NOT EXISTS evaluation_runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL UNIQUE,
  dataset_name TEXT NOT NULL,
  claims_path TEXT NOT NULL,
  labels_path TEXT NOT NULL,
  output_path TEXT NOT NULL,
  metrics_json TEXT NOT NULL,
  passed INTEGER NOT NULL CHECK (passed IN (0, 1)),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS config_versions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  config_type TEXT NOT NULL,
  version TEXT NOT NULL,
  file_path TEXT NOT NULL,
  checksum TEXT NOT NULL,
  active INTEGER NOT NULL CHECK (active IN (0, 1)),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  actor_id TEXT,
  claim_id TEXT,
  entity_type TEXT NOT NULL,
  entity_id TEXT,
  metadata_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  FOREIGN KEY (claim_id) REFERENCES claim_reviews(claim_id)
);

CREATE INDEX IF NOT EXISTS idx_agent_outputs_claim_id ON agent_outputs(claim_id);
CREATE INDEX IF NOT EXISTS idx_tool_call_logs_claim_id ON tool_call_logs(claim_id);
CREATE INDEX IF NOT EXISTS idx_reviewer_actions_claim_id ON reviewer_actions(claim_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_logs_claim_id ON retrieval_logs(claim_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_claim_id ON audit_logs(claim_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type);

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

CREATE TABLE IF NOT EXISTS medical_code_registry (
  code_system TEXT NOT NULL,
  code TEXT NOT NULL,
  source_synthetic_code TEXT,
  code_name TEXT NOT NULL,
  parent_code TEXT,
  chapter TEXT,
  category TEXT,
  aliases_json TEXT NOT NULL,
  version TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (code_system, code, version)
);

CREATE TABLE IF NOT EXISTS procedure_code_registry (
  code_system TEXT NOT NULL,
  code TEXT NOT NULL,
  source_synthetic_code TEXT,
  code_name TEXT NOT NULL,
  procedure_group TEXT,
  benefit_category TEXT,
  aliases_json TEXT NOT NULL,
  version TEXT NOT NULL,
  valid_from TEXT NOT NULL,
  valid_to TEXT,
  synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (code_system, code, version)
);

CREATE TABLE IF NOT EXISTS diagnosis_treatment_rules (
  kcd_code TEXT NOT NULL,
  edi_code TEXT NOT NULL,
  relationship TEXT NOT NULL CHECK (relationship IN ('compatible', 'weakly_related', 'not_related', 'unknown')),
  medical_necessity_level TEXT NOT NULL CHECK (medical_necessity_level IN ('supported', 'partially_supported', 'unsupported', 'insufficient_evidence')),
  required_documents_json TEXT NOT NULL,
  age_min INTEGER,
  age_max INTEGER,
  sex_constraint TEXT NOT NULL,
  review_policy TEXT NOT NULL CHECK (review_policy IN ('continue_claim_review', 'request_documents', 'human_review')),
  reason_code TEXT NOT NULL,
  version TEXT NOT NULL,
  synthetic INTEGER NOT NULL CHECK (synthetic IN (0, 1)),
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (kcd_code, edi_code, version)
);

CREATE TABLE IF NOT EXISTS medical_routing_rules (
  rule_id TEXT NOT NULL,
  rule_version TEXT NOT NULL,
  rule_name TEXT,
  description TEXT,
  routing TEXT NOT NULL,
  reason_code TEXT NOT NULL,
  default_confidence REAL NOT NULL,
  approval_status TEXT NOT NULL,
  owner TEXT,
  effective_from TEXT,
  effective_to TEXT,
  synthetic INTEGER NOT NULL DEFAULT 0,
  payload_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (rule_id, rule_version)
);

CREATE TABLE IF NOT EXISTS specialist_agent_reports (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT NOT NULL,
  agent_name TEXT NOT NULL,
  agent_version TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('success', 'failed', 'skipped')),
  report_json TEXT NOT NULL,
  requires_human_review INTEGER NOT NULL CHECK (requires_human_review IN (0, 1)),
  created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS document_extraction_results (
  document_id TEXT NOT NULL,
  claim_id TEXT NOT NULL,
  document_type TEXT NOT NULL,
  extraction_mode TEXT NOT NULL,
  extraction_status TEXT NOT NULL,
  extraction_confidence_bucket TEXT NOT NULL,
  result_json TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  PRIMARY KEY (document_id, extraction_mode)
);

CREATE TABLE IF NOT EXISTS medical_registry_seed_runs (
  run_id TEXT PRIMARY KEY,
  source_files_json TEXT NOT NULL,
  row_count INTEGER NOT NULL CHECK (row_count >= 0),
  created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_medical_code_registry_source ON medical_code_registry(source_synthetic_code);
CREATE INDEX IF NOT EXISTS idx_procedure_code_registry_source ON procedure_code_registry(source_synthetic_code);
CREATE INDEX IF NOT EXISTS idx_diagnosis_treatment_rules_kcd ON diagnosis_treatment_rules(kcd_code);
CREATE INDEX IF NOT EXISTS idx_diagnosis_treatment_rules_edi ON diagnosis_treatment_rules(edi_code);
CREATE INDEX IF NOT EXISTS idx_medical_routing_rules_status ON medical_routing_rules(approval_status);
CREATE INDEX IF NOT EXISTS idx_specialist_agent_reports_claim ON specialist_agent_reports(claim_id);
CREATE INDEX IF NOT EXISTS idx_document_extraction_results_claim ON document_extraction_results(claim_id);

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
