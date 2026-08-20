-- Bring the template local runtime closer to the MVP operational boundary.

PRAGMA foreign_keys = OFF;

CREATE TABLE IF NOT EXISTS reviewer_actions_new (
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

INSERT INTO reviewer_actions_new (
  id, claim_id, reviewer_id, action, override_decision,
  override_payable_amount, reviewer_note, action_payload_json, created_at
)
SELECT
  id,
  claim_id,
  NULL,
  CASE action_type
    WHEN 'approve_recommendation' THEN 'accept_recommendation'
    WHEN 'override_decision' THEN 'modify_recommendation'
    WHEN 'request_more_documents' THEN 'request_documents'
    WHEN 'mark_human_review' THEN 'mark_human_review'
    ELSE 'defer'
  END,
  override_decision,
  NULL,
  reviewer_note,
  '{}',
  created_at
FROM reviewer_actions;

DROP TABLE reviewer_actions;
ALTER TABLE reviewer_actions_new RENAME TO reviewer_actions;

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS retrieval_logs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  claim_id TEXT,
  query TEXT NOT NULL,
  result_json TEXT NOT NULL,
  citation_count INTEGER NOT NULL CHECK (citation_count >= 0),
  created_at TEXT NOT NULL,
  FOREIGN KEY (claim_id) REFERENCES claim_reviews(claim_id)
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

CREATE INDEX IF NOT EXISTS idx_reviewer_actions_claim_id ON reviewer_actions(claim_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_logs_claim_id ON retrieval_logs(claim_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_claim_id ON audit_logs(claim_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_event_type ON audit_logs(event_type);
