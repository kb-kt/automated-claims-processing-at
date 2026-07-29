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
  action_type TEXT NOT NULL CHECK (action_type IN ('approve_recommendation', 'override_decision', 'request_more_documents', 'mark_human_review', 'add_reviewer_note')),
  reviewer_note TEXT,
  override_decision TEXT,
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

CREATE INDEX IF NOT EXISTS idx_agent_outputs_claim_id ON agent_outputs(claim_id);
CREATE INDEX IF NOT EXISTS idx_tool_call_logs_claim_id ON tool_call_logs(claim_id);
CREATE INDEX IF NOT EXISTS idx_reviewer_actions_claim_id ON reviewer_actions(claim_id);
