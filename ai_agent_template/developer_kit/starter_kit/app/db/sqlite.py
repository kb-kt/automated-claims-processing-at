from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ai_agent_template.developer_kit.claims_gateway import sqlite_fraud_context
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import redact_sensitive_data

from .migrations import MigrationRunner


_ACTION_TYPE_MAP = {
    "approve_recommendation": "accept_recommendation",
    "override_decision": "modify_recommendation",
    "request_more_documents": "request_documents",
    "mark_human_review": "mark_human_review",
    "add_reviewer_note": "defer",
}


class SQLiteRepository:
    def __init__(
        self,
        db_path: str | Path,
        schema_path: str | Path,
        migrations_dir: str | Path | None = None,
    ):
        self.db_path = Path(db_path)
        self.schema_path = Path(schema_path)
        self.migrations_dir = Path(migrations_dir) if migrations_dir else self.schema_path.parent / "migrations"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        MigrationRunner(
            db_path=self.db_path,
            migrations_dir=self.migrations_dir,
            schema_path=self.schema_path,
        ).apply()

    def save_claim(self, claim_payload: dict[str, Any], status: str = "received") -> None:
        now = _now()
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO claim_reviews (
                  claim_id, policy_id, product_id, input_payload_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                  input_payload_json=excluded.input_payload_json,
                  status=excluded.status,
                  updated_at=excluded.updated_at
                """,
                (
                    claim_payload["claim_id"],
                    claim_payload["policy_id"],
                    claim_payload["product_id"],
                    json.dumps(claim_payload, ensure_ascii=False),
                    status,
                    now,
                    now,
                ),
            )
            connection.commit()

    def get_claim(self, claim_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT input_payload_json FROM claim_reviews WHERE claim_id = ?",
                (claim_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def get_fraud_current_claim(self, claim_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            return sqlite_fraud_context.get_fraud_current_claim(connection, claim_id)

    def list_historical_claims_for_claim(self, claim_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            return sqlite_fraud_context.list_historical_claims_for_claim(connection, claim_id)

    def list_document_metadata_for_claim(self, claim_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            return sqlite_fraud_context.list_document_metadata_for_claim(connection, claim_id)

    def get_document_metadata(self, document_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            return sqlite_fraud_context.get_document_metadata(connection, document_id)

    def save_uploaded_document(self, metadata: dict[str, Any]) -> None:
        with closing(self._connect()) as connection:
            sqlite_fraud_context.save_uploaded_document(connection, metadata)

    def seed_fraud_context(
        self,
        *,
        split: str,
        seed_rows: list[dict[str, Any]],
        historical_claims: list[dict[str, Any]],
        document_metadata: list[dict[str, Any]],
        claim_document_links: list[dict[str, Any]],
        source_files: list[str],
    ) -> dict[str, Any]:
        with closing(self._connect()) as connection:
            return sqlite_fraud_context.seed_fraud_context(
                connection,
                split=split,
                seed_rows=seed_rows,
                historical_claims=historical_claims,
                document_metadata=document_metadata,
                claim_document_links=claim_document_links,
                source_files=source_files,
            )

    def seed_medical_registry(
        self,
        *,
        medical_code_registry: list[dict[str, Any]],
        edi_code_registry: list[dict[str, Any]],
        diagnosis_treatment_rules: list[dict[str, Any]],
        source_files: list[str],
        insurer_medical_routing_rules: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        now = _now()
        row_count = 0
        with closing(self._connect()) as connection:
            for row in medical_code_registry:
                connection.execute(
                    """
                    INSERT INTO medical_code_registry (
                      code_system, code, source_synthetic_code, code_name,
                      parent_code, chapter, category, aliases_json, version,
                      valid_from, valid_to, synthetic, payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code_system, code, version) DO UPDATE SET
                      source_synthetic_code=excluded.source_synthetic_code,
                      code_name=excluded.code_name,
                      parent_code=excluded.parent_code,
                      chapter=excluded.chapter,
                      category=excluded.category,
                      aliases_json=excluded.aliases_json,
                      valid_from=excluded.valid_from,
                      valid_to=excluded.valid_to,
                      synthetic=excluded.synthetic,
                      payload_json=excluded.payload_json,
                      updated_at=excluded.updated_at
                    """,
                    (
                        row.get("code_system", "KCD"),
                        row["code"],
                        row.get("source_synthetic_code"),
                        row["code_name"],
                        row.get("parent_code"),
                        row.get("chapter"),
                        row.get("category"),
                        json.dumps(row.get("aliases", []), ensure_ascii=False),
                        row.get("version", "unknown"),
                        row.get("valid_from", "1900-01-01"),
                        row.get("valid_to"),
                        int(bool(row.get("synthetic", False))),
                        json.dumps(row, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                row_count += 1
            for row in edi_code_registry:
                connection.execute(
                    """
                    INSERT INTO procedure_code_registry (
                      code_system, code, source_synthetic_code, code_name,
                      procedure_group, benefit_category, aliases_json, version,
                      valid_from, valid_to, synthetic, payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(code_system, code, version) DO UPDATE SET
                      source_synthetic_code=excluded.source_synthetic_code,
                      code_name=excluded.code_name,
                      procedure_group=excluded.procedure_group,
                      benefit_category=excluded.benefit_category,
                      aliases_json=excluded.aliases_json,
                      valid_from=excluded.valid_from,
                      valid_to=excluded.valid_to,
                      synthetic=excluded.synthetic,
                      payload_json=excluded.payload_json,
                      updated_at=excluded.updated_at
                    """,
                    (
                        row.get("code_system", "EDI"),
                        row["code"],
                        row.get("source_synthetic_code"),
                        row["code_name"],
                        row.get("procedure_group"),
                        row.get("benefit_category"),
                        json.dumps(row.get("aliases", []), ensure_ascii=False),
                        row.get("version", "unknown"),
                        row.get("valid_from", "1900-01-01"),
                        row.get("valid_to"),
                        int(bool(row.get("synthetic", False))),
                        json.dumps(row, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                row_count += 1
            for row in diagnosis_treatment_rules:
                connection.execute(
                    """
                    INSERT INTO diagnosis_treatment_rules (
                      kcd_code, edi_code, relationship, medical_necessity_level,
                      required_documents_json, age_min, age_max, sex_constraint,
                      review_policy, reason_code, version, synthetic,
                      payload_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(kcd_code, edi_code, version) DO UPDATE SET
                      relationship=excluded.relationship,
                      medical_necessity_level=excluded.medical_necessity_level,
                      required_documents_json=excluded.required_documents_json,
                      age_min=excluded.age_min,
                      age_max=excluded.age_max,
                      sex_constraint=excluded.sex_constraint,
                      review_policy=excluded.review_policy,
                      reason_code=excluded.reason_code,
                      synthetic=excluded.synthetic,
                      payload_json=excluded.payload_json,
                      updated_at=excluded.updated_at
                    """,
                    (
                        row["kcd_code"],
                        row["edi_code"],
                        row["relationship"],
                        row["medical_necessity_level"],
                        json.dumps(row.get("required_documents", []), ensure_ascii=False),
                        row.get("age_min"),
                        row.get("age_max"),
                        row.get("sex_constraint", "any"),
                        row["review_policy"],
                        row["reason_code"],
                        row.get("version", "unknown"),
                        int(bool(row.get("synthetic", False))),
                        json.dumps(row, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                row_count += 1
            for row in insurer_medical_routing_rules or []:
                connection.execute(
                    """
                    INSERT INTO medical_routing_rules (
                      rule_id, rule_version, rule_name, description, routing,
                      reason_code, default_confidence, approval_status, owner,
                      effective_from, effective_to, synthetic, payload_json,
                      created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(rule_id, rule_version) DO UPDATE SET
                      rule_name=excluded.rule_name,
                      description=excluded.description,
                      routing=excluded.routing,
                      reason_code=excluded.reason_code,
                      default_confidence=excluded.default_confidence,
                      approval_status=excluded.approval_status,
                      owner=excluded.owner,
                      effective_from=excluded.effective_from,
                      effective_to=excluded.effective_to,
                      synthetic=excluded.synthetic,
                      payload_json=excluded.payload_json,
                      updated_at=excluded.updated_at
                    """,
                    (
                        row["rule_id"],
                        row.get("rule_version", row.get("version", "unknown")),
                        row.get("rule_name"),
                        row.get("description"),
                        row["routing"],
                        row["reason_code"],
                        float(row.get("default_confidence", row.get("confidence", 0))),
                        row.get("approval_status", "draft"),
                        row.get("owner"),
                        row.get("effective_from", "1900-01-01"),
                        row.get("effective_to"),
                        int(bool(row.get("synthetic", False))),
                        json.dumps(row, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
                row_count += 1
            run_id = _stable_seed_run_id(source_files)
            connection.execute(
                """
                INSERT INTO medical_registry_seed_runs (run_id, source_files_json, row_count, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                  source_files_json=excluded.source_files_json,
                  row_count=excluded.row_count
                """,
                (run_id, json.dumps(source_files, ensure_ascii=False), row_count, now),
            )
            connection.commit()
        return {"run_id": run_id, "row_count": row_count}

    def get_medical_code(self, code: str, *, code_system: str = "KCD") -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM medical_code_registry
                WHERE code_system = ? AND (code = ? OR source_synthetic_code = ?)
                ORDER BY valid_from DESC, version DESC
                LIMIT 1
                """,
                (code_system, code, code),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def get_procedure_code(self, code: str, *, code_system: str = "EDI") -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM procedure_code_registry
                WHERE code_system = ? AND (code = ? OR source_synthetic_code = ?)
                ORDER BY valid_from DESC, version DESC
                LIMIT 1
                """,
                (code_system, code, code),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def find_diagnosis_treatment_rule(self, kcd_code: str, edi_code: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM diagnosis_treatment_rules
                WHERE kcd_code = ? AND edi_code = ?
                ORDER BY version DESC
                LIMIT 1
                """,
                (kcd_code, edi_code),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def get_medical_routing_rule(self, rule_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT payload_json
                FROM medical_routing_rules
                WHERE rule_id = ?
                ORDER BY effective_from DESC, rule_version DESC
                LIMIT 1
                """,
                (rule_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def find_medical_routing_rule(
        self,
        *,
        reason_code: str,
        routing: str | None = None,
    ) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            if routing:
                row = connection.execute(
                    """
                    SELECT payload_json
                    FROM medical_routing_rules
                    WHERE reason_code = ? AND routing = ?
                      AND approval_status IN ('synthetic_insurer_approved', 'insurer_approved')
                    ORDER BY effective_from DESC, rule_version DESC
                    LIMIT 1
                    """,
                    (reason_code, routing),
                ).fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT payload_json
                    FROM medical_routing_rules
                    WHERE reason_code = ?
                      AND approval_status IN ('synthetic_insurer_approved', 'insurer_approved')
                    ORDER BY effective_from DESC, rule_version DESC
                    LIMIT 1
                    """,
                    (reason_code,),
                ).fetchone()
        return json.loads(row[0]) if row else None

    def list_claims(self, *, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT claim_id, policy_id, product_id, status, created_at, updated_at
                FROM claim_reviews
                ORDER BY updated_at DESC, claim_id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        return [
            {
                "claim_id": row[0],
                "policy_id": row[1],
                "product_id": row[2],
                "status": row[3],
                "created_at": row[4],
                "updated_at": row[5],
            }
            for row in rows
        ]

    def list_review_queue(self, *, limit: int = 50, sla_hours: int = 24) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        safe_sla_hours = max(1, min(int(sla_hours), 168))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                  c.claim_id, c.policy_id, c.product_id, c.status,
                  c.created_at, c.updated_at,
                  a.recommended_decision, a.requires_human_review,
                  a.fraud_suspected, a.confidence
                FROM claim_reviews c
                LEFT JOIN agent_outputs a ON a.id = (
                  SELECT id
                  FROM agent_outputs
                  WHERE claim_id = c.claim_id
                  ORDER BY id DESC
                  LIMIT 1
                )
                ORDER BY c.updated_at DESC, c.claim_id DESC
                LIMIT ?
                """,
                (safe_limit,),
            ).fetchall()
        queue = [_review_queue_item(row, safe_sla_hours) for row in rows]
        return sorted(queue, key=lambda item: item["priority_score"], reverse=True)

    def save_agent_output(
        self,
        output: dict[str, Any],
        *,
        model_provider: str = "unknown",
        model_name: str = "unknown",
        schema_version: str = "1.0.0",
        workflow_version: str = "1.0.0",
    ) -> None:
        now = _now()
        status = "human_review_required" if output["requires_human_review"] else "completed"
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE claim_reviews SET status = ?, updated_at = ? WHERE claim_id = ?",
                (status, now, output["claim_id"]),
            )
            connection.execute(
                """
                INSERT INTO agent_outputs (
                  claim_id, output_payload_json, recommended_decision,
                  recommended_payable_amount, coverage_code, requires_human_review,
                  fraud_suspected, confidence, prompt_version, workflow_version,
                  schema_version, model_provider, model_name, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    output["claim_id"],
                    json.dumps(output, ensure_ascii=False),
                    output["recommended_decision"],
                    output["recommended_payable_amount"],
                    output["coverage_code"],
                    int(output["requires_human_review"]),
                    int(output["fraud_suspected"]),
                    float(output["confidence"]),
                    "1.0.0",
                    workflow_version,
                    schema_version,
                    model_provider,
                    model_name,
                    now,
                ),
            )
            connection.commit()

    def get_latest_output(self, claim_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT output_payload_json
                FROM agent_outputs
                WHERE claim_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (claim_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def save_specialist_agent_reports(self, claim_id: str, reports: list[dict[str, Any]]) -> None:
        now = _now()
        with closing(self._connect()) as connection:
            connection.execute("DELETE FROM specialist_agent_reports WHERE claim_id = ?", (claim_id,))
            for report in reports:
                connection.execute(
                    """
                    INSERT INTO specialist_agent_reports (
                      claim_id, agent_name, agent_version, status,
                      report_json, requires_human_review, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        claim_id,
                        report.get("agent_name", "unknown"),
                        report.get("agent_version", report.get("report_version", "unknown")),
                        _report_status(report),
                        json.dumps(report, ensure_ascii=False),
                        int(bool(report.get("requires_human_review"))),
                        now,
                    ),
                )
            connection.commit()

    def list_specialist_agent_reports(self, claim_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT report_json
                FROM specialist_agent_reports
                WHERE claim_id = ?
                ORDER BY id ASC
                """,
                (claim_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_document_extraction_results(self, claim_id: str, results: list[dict[str, Any]]) -> None:
        if not results:
            return
        now = _now()
        with closing(self._connect()) as connection:
            for result in results:
                connection.execute(
                    """
                    INSERT INTO document_extraction_results (
                      document_id, claim_id, document_type, extraction_mode,
                      extraction_status, extraction_confidence_bucket,
                      result_json, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(document_id, extraction_mode) DO UPDATE SET
                      claim_id=excluded.claim_id,
                      document_type=excluded.document_type,
                      extraction_status=excluded.extraction_status,
                      extraction_confidence_bucket=excluded.extraction_confidence_bucket,
                      result_json=excluded.result_json,
                      updated_at=excluded.updated_at
                    """,
                    (
                        result.get("document_id", "unknown"),
                        claim_id,
                        result.get("document_type", "unknown"),
                        result.get("extraction_mode", "unknown"),
                        result.get("extraction_status", "unknown"),
                        result.get("extraction_confidence_bucket", "unknown"),
                        json.dumps(result, ensure_ascii=False),
                        now,
                        now,
                    ),
                )
            connection.commit()

    def list_document_extraction_results(self, claim_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT result_json
                FROM document_extraction_results
                WHERE claim_id = ?
                ORDER BY document_type, document_id, extraction_mode
                """,
                (claim_id,),
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def save_tool_call_log(
        self,
        *,
        claim_id: str,
        tool_name: str,
        tool_version: str,
        request: dict[str, Any],
        response: dict[str, Any] | None,
        status: str,
        metadata: dict[str, Any] | None = None,
        error_code: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
        response_payload = response
        if response_payload is not None and metadata:
            response_payload = dict(response_payload)
            response_payload.setdefault("metadata", {}).update(metadata)
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO tool_call_logs (
                  claim_id, tool_name, tool_version, request_json, response_json,
                  status, error_code, duration_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    tool_name,
                    tool_version,
                    json.dumps(redact_sensitive_data(request), ensure_ascii=False),
                    json.dumps(redact_sensitive_data(response_payload), ensure_ascii=False) if response_payload is not None else None,
                    status,
                    error_code,
                    duration_ms,
                    _now(),
                ),
            )
            connection.commit()

    def save_reviewer_action(
        self,
        *,
        claim_id: str,
        action: str | None = None,
        action_type: str | None = None,
        reviewer_id: str | None = None,
        reviewer_note: str | None = None,
        override_decision: str | None = None,
        override_payable_amount: int | None = None,
        action_payload: dict[str, Any] | None = None,
    ) -> None:
        normalized_action = action or _ACTION_TYPE_MAP.get(action_type or "", action_type)
        if not normalized_action:
            raise ValueError("action or action_type is required")
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO reviewer_actions (
                  claim_id, reviewer_id, action, override_decision,
                  override_payable_amount, reviewer_note, action_payload_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    reviewer_id,
                    normalized_action,
                    override_decision,
                    override_payable_amount,
                    reviewer_note,
                    json.dumps(action_payload or {}, ensure_ascii=False),
                    _now(),
                ),
            )
            connection.commit()

    def list_reviewer_actions(self, claim_id: str) -> list[dict[str, Any]]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT
                  id, claim_id, reviewer_id, action, override_decision,
                  override_payable_amount, reviewer_note, action_payload_json, created_at
                FROM reviewer_actions
                WHERE claim_id = ?
                ORDER BY id DESC
                """,
                (claim_id,),
            ).fetchall()
        return [
            {
                "id": row[0],
                "claim_id": row[1],
                "reviewer_id": row[2],
                "action": row[3],
                "override_decision": row[4],
                "override_payable_amount": row[5],
                "reviewer_note": row[6],
                "action_payload": _loads_json(row[7]),
                "created_at": row[8],
            }
            for row in rows
        ]

    def save_retrieval_log(
        self,
        *,
        query: str,
        result: dict[str, Any],
        claim_id: str | None = None,
    ) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO retrieval_logs (claim_id, query, result_json, citation_count, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    query,
                    json.dumps(redact_sensitive_data(result), ensure_ascii=False),
                    len(result.get("matches", [])),
                    _now(),
                ),
            )
            connection.commit()

    def save_evaluation_run(
        self,
        *,
        run_id: str,
        dataset_name: str,
        claims_path: str,
        labels_path: str,
        output_path: str,
        metrics: dict[str, Any],
        passed: bool,
    ) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO evaluation_runs (
                  run_id, dataset_name, claims_path, labels_path, output_path,
                  metrics_json, passed, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    dataset_name,
                    claims_path,
                    labels_path,
                    output_path,
                    json.dumps(metrics, ensure_ascii=False),
                    int(passed),
                    _now(),
                ),
            )
            connection.commit()

    def get_evaluation_run(self, run_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT
                  run_id, dataset_name, claims_path, labels_path,
                  output_path, metrics_json, passed, created_at
                FROM evaluation_runs
                WHERE run_id = ?
                """,
                (run_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "run_id": row[0],
            "dataset_name": row[1],
            "claims_path": row[2],
            "labels_path": row[3],
            "output_path": row[4],
            "metrics": json.loads(row[5]),
            "passed": bool(row[6]),
            "created_at": row[7],
        }

    def save_audit_log(
        self,
        *,
        event_type: str,
        entity_type: str,
        actor_id: str | None = None,
        claim_id: str | None = None,
        entity_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO audit_logs (
                  event_type, actor_id, claim_id, entity_type,
                  entity_id, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event_type,
                    actor_id,
                    claim_id,
                    entity_type,
                    entity_id,
                    json.dumps(redact_sensitive_data(metadata or {}), ensure_ascii=False),
                    _now(),
                ),
            )
            connection.commit()

    def list_audit_logs(self, *, claim_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 500))
        with closing(self._connect()) as connection:
            if claim_id:
                rows = connection.execute(
                    """
                    SELECT id, event_type, actor_id, claim_id, entity_type,
                           entity_id, metadata_json, created_at
                    FROM audit_logs
                    WHERE claim_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (claim_id, safe_limit),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT id, event_type, actor_id, claim_id, entity_type,
                           entity_id, metadata_json, created_at
                    FROM audit_logs
                    ORDER BY id DESC
                    LIMIT ?
                    """,
                    (safe_limit,),
                ).fetchall()
        return [
            {
                "id": row[0],
                "event_type": row[1],
                "actor_id": row[2],
                "claim_id": row[3],
                "entity_type": row[4],
                "entity_id": row[5],
                "metadata": _loads_json(row[6]),
                "created_at": row[7],
            }
            for row in rows
        ]

    def applied_migrations(self) -> list[str]:
        return MigrationRunner(
            db_path=self.db_path,
            migrations_dir=self.migrations_dir,
            schema_path=self.schema_path,
        ).applied_versions()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA foreign_keys = ON")
        return connection


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _loads_json(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    return json.loads(value)


def _report_status(report: dict[str, Any]) -> str:
    status = str(report.get("status", "success"))
    if status == "completed":
        return "success"
    if status in {"success", "failed", "skipped"}:
        return status
    return "failed"


def _stable_seed_run_id(source_files: list[str]) -> str:
    import hashlib

    digest = hashlib.sha256("|".join(sorted(source_files)).encode("utf-8")).hexdigest()[:16]
    return f"medical-registry-{digest}"


def _review_queue_item(row: tuple[Any, ...], sla_hours: int) -> dict[str, Any]:
    created_at = _parse_datetime(row[4])
    updated_at = _parse_datetime(row[5])
    now = datetime.now(timezone.utc)
    age_hours = max(0.0, (now - created_at).total_seconds() / 3600)
    due_at = created_at + timedelta(hours=sla_hours)
    status = row[3]
    requires_human_review = bool(row[7]) if row[7] is not None else False
    fraud_suspected = bool(row[8]) if row[8] is not None else False
    confidence = float(row[9]) if row[9] is not None else None
    active = status in {"received", "reviewing", "human_review_required"}
    if not active:
        sla_status = "closed"
    elif now > due_at:
        sla_status = "overdue"
    elif age_hours >= sla_hours * 0.8:
        sla_status = "due_soon"
    else:
        sla_status = "ok"

    priority_score = 25
    if status == "human_review_required" or requires_human_review:
        priority_score += 35
    if status in {"received", "reviewing"}:
        priority_score += 15
    if fraud_suspected:
        priority_score += 25
    if confidence is not None and confidence < 0.8:
        priority_score += 10
    if sla_status == "overdue":
        priority_score += 20
    elif sla_status == "due_soon":
        priority_score += 10
    if status in {"completed", "failed"}:
        priority_score -= 20

    return {
        "claim_id": row[0],
        "policy_id": row[1],
        "product_id": row[2],
        "status": status,
        "created_at": created_at.isoformat(),
        "updated_at": updated_at.isoformat(),
        "recommended_decision": row[6],
        "requires_human_review": requires_human_review,
        "fraud_suspected": fraud_suspected,
        "confidence": confidence,
        "age_hours": round(age_hours, 2),
        "sla_due_at": due_at.isoformat(),
        "sla_status": sla_status,
        "priority_score": max(0, min(priority_score, 100)),
    }


def _parse_datetime(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
