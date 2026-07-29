from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .migrations import MigrationRunner


class SQLiteRepository:
    def __init__(
        self,
        *,
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
                INSERT INTO claims (
                  claim_id, policy_id, product_id, payload_json, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(claim_id) DO UPDATE SET
                  payload_json=excluded.payload_json,
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
                "SELECT payload_json FROM claims WHERE claim_id = ?",
                (claim_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

    def list_claims(self, *, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 200))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT claim_id, policy_id, product_id, status, created_at, updated_at
                FROM claims
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
                  r.recommended_decision, r.requires_human_review,
                  r.fraud_suspected, r.confidence
                FROM claims c
                LEFT JOIN reviews r ON r.id = (
                  SELECT id
                  FROM reviews
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

    def save_review(
        self,
        output: dict[str, Any],
        *,
        model_provider: str,
        model_id: str,
        schema_version: str = "1.0.0",
        workflow_version: str = "1.0.0",
    ) -> None:
        now = _now()
        status = "human_review_required" if output["requires_human_review"] else "completed"
        with closing(self._connect()) as connection:
            connection.execute(
                "UPDATE claims SET status = ?, updated_at = ? WHERE claim_id = ?",
                (status, now, output["claim_id"]),
            )
            connection.execute(
                """
                INSERT INTO reviews (
                  claim_id, output_json, recommended_decision,
                  recommended_payable_amount, coverage_code, requires_human_review,
                  fraud_suspected, confidence, schema_version, workflow_version,
                  model_provider, model_id, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    output["claim_id"],
                    json.dumps(output, ensure_ascii=False),
                    output["recommended_decision"],
                    int(output["recommended_payable_amount"]),
                    output["coverage_code"],
                    int(output["requires_human_review"]),
                    int(output["fraud_suspected"]),
                    float(output["confidence"]),
                    schema_version,
                    workflow_version,
                    model_provider,
                    model_id,
                    now,
                ),
            )
            connection.commit()

    def get_latest_review(self, claim_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT output_json
                FROM reviews
                WHERE claim_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (claim_id,),
            ).fetchone()
        return json.loads(row[0]) if row else None

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
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO tool_call_logs (
                  claim_id, tool_name, tool_version, request_json, response_json,
                  metadata_json, status, error_code, duration_ms, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    tool_name,
                    tool_version,
                    json.dumps(request, ensure_ascii=False),
                    json.dumps(response, ensure_ascii=False) if response is not None else None,
                    json.dumps(metadata or {}, ensure_ascii=False),
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
        action: str,
        reviewer_id: str | None = None,
        reviewer_note: str | None = None,
        override_decision: str | None = None,
        override_payable_amount: int | None = None,
        action_payload: dict[str, Any] | None = None,
    ) -> None:
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
                    action,
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
                    json.dumps(result, ensure_ascii=False),
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
                  run_id, dataset_name, claims_path, labels_path,
                  output_path, metrics_json, passed, created_at
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
                    json.dumps(metadata or {}, ensure_ascii=False),
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
