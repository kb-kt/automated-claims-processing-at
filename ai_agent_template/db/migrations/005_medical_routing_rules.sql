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

CREATE INDEX IF NOT EXISTS idx_medical_routing_rules_status
  ON medical_routing_rules(approval_status);
