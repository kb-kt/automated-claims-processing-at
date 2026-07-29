from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .migrations import MigrationRunner


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

    def save_agent_output(self, output: dict[str, Any]) -> None:
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
                    "1.0.0",
                    "1.0.0",
                    "mock",
                    "mock-reviewer",
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

    def save_tool_call_log(
        self,
        *,
        claim_id: str,
        tool_name: str,
        tool_version: str,
        request: dict[str, Any],
        response: dict[str, Any] | None,
        status: str,
        error_code: str | None = None,
        duration_ms: int | None = None,
    ) -> None:
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
                    json.dumps(request, ensure_ascii=False),
                    json.dumps(response, ensure_ascii=False) if response is not None else None,
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
        action_type: str,
        reviewer_note: str | None = None,
        override_decision: str | None = None,
    ) -> None:
        with closing(self._connect()) as connection:
            connection.execute(
                """
                INSERT INTO reviewer_actions (
                  claim_id, action_type, reviewer_note, override_decision, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    claim_id,
                    action_type,
                    reviewer_note,
                    override_decision,
                    _now(),
                ),
            )
            connection.commit()

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
