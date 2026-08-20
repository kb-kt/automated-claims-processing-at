from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[1]
SAMPLES_DIR = BASE_DIR / "samples"
GENERATED_DIR = BASE_DIR / "generated"
CATALOG_DIR = BASE_DIR / "catalog"

DEFAULT_CONFIG_PATH = SAMPLES_DIR / "generation_config.sample.json"
DEFAULT_PRODUCT_PATH = SAMPLES_DIR / "products.json"
DEFAULT_PRODUCT_CATALOG_PATH = CATALOG_DIR / "products" / "product_catalog.json"
DEFAULT_POLICY_DOC_PATH = SAMPLES_DIR / "policy_documents.md"
DEFAULT_EVALUATION_CASES_PATH = SAMPLES_DIR / "evaluation_cases_sample.jsonl"

ALLOWED_DECISIONS = {
    "pay",
    "partial_pay",
    "request_documents",
    "deny",
    "human_review",
}

AGENT_FORBIDDEN_KEYS = {
    "expected_decision",
    "expected_payable_amount",
    "expected_explanation",
    "reason_codes",
    "calculation",
    "requires_human_review",
    "fraud_suspected",
}

CLAIM_REQUIRED_FIELDS = {
    "claim_id",
    "policy_id",
    "product_id",
    "scenario_type",
    "insured_profile",
    "claimant",
    "policy",
    "claim",
    "documents",
    "claim_history",
    "signals",
}

LABEL_REQUIRED_FIELDS = {
    "claim_id",
    "expected_decision",
    "expected_payable_amount",
    "coverage_code",
    "missing_documents",
    "reason_codes",
    "requires_human_review",
    "fraud_suspected",
    "calculation",
    "expected_explanation",
}

DEFAULT_DECISION_DISTRIBUTION = {
    "pay": 0.35,
    "partial_pay": 0.25,
    "request_documents": 0.15,
    "deny": 0.12,
    "human_review": 0.10,
    "fraud_suspected_human_review": 0.03,
}

DEFAULT_CLAIM_TYPE_DISTRIBUTION = {
    "covered_outpatient": 0.35,
    "noncovered_outpatient": 0.20,
    "prescription": 0.15,
    "covered_inpatient": 0.10,
    "noncovered_inpatient": 0.08,
    "special_noncovered": 0.10,
    "edge_case": 0.02,
}
