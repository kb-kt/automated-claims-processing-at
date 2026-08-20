-- Medical code registry and specialist-agent report tables.

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
CREATE INDEX IF NOT EXISTS idx_specialist_agent_reports_claim ON specialist_agent_reports(claim_id);
CREATE INDEX IF NOT EXISTS idx_document_extraction_results_claim ON document_extraction_results(claim_id);
