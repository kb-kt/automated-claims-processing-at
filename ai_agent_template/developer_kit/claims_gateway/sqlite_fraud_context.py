from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def seed_fraud_context(
    connection: sqlite3.Connection,
    *,
    split: str,
    seed_rows: list[dict[str, Any]],
    historical_claims: list[dict[str, Any]],
    document_metadata: list[dict[str, Any]],
    claim_document_links: list[dict[str, Any]],
    source_files: list[str],
) -> dict[str, Any]:
    now = _now()
    normalized_split = split.lower()
    run_id = _run_id(normalized_split, source_files, seed_rows, historical_claims, document_metadata, claim_document_links)

    counts = {
        "insureds": 0,
        "providers": 0,
        "fraud_current_claims": 0,
        "historical_claims": 0,
        "document_metadata": 0,
        "claim_documents": 0,
    }
    for row in seed_rows:
        seed_type = row.get("seed_type")
        if seed_type == "insured":
            _upsert_insured(connection, normalized_split, row["insured"], now)
            counts["insureds"] += 1
        elif seed_type == "provider":
            _upsert_provider(connection, normalized_split, row["provider"], now)
            counts["providers"] += 1
        elif seed_type == "current_claim":
            _upsert_current_claim(connection, normalized_split, row["claim"], now)
            counts["fraud_current_claims"] += 1
    for historical in historical_claims:
        _upsert_historical_claim(connection, normalized_split, historical, now)
        counts["historical_claims"] += 1
    for metadata in document_metadata:
        _upsert_document_metadata(connection, normalized_split, metadata, now)
        counts["document_metadata"] += 1
    for link in claim_document_links:
        _upsert_claim_document(connection, normalized_split, link, now)
        counts["claim_documents"] += 1

    total_rows = sum(counts.values())
    connection.execute(
        """
        INSERT INTO fraud_context_seed_runs (run_id, split, source_files_json, row_count, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
          source_files_json=excluded.source_files_json,
          row_count=excluded.row_count
        """,
        (run_id, normalized_split, json.dumps(source_files, ensure_ascii=False), total_rows, now),
    )
    connection.commit()
    return {"run_id": run_id, "split": normalized_split, "row_count": total_rows, "counts": counts}


def get_fraud_current_claim(connection: sqlite3.Connection, claim_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT payload_json FROM fraud_current_claims WHERE claim_id = ?",
        (claim_id,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def list_historical_claims_for_claim(connection: sqlite3.Connection, claim_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT payload_json
        FROM historical_claims
        WHERE history_for_claim_id = ?
        ORDER BY treatment_start_date ASC, claim_id ASC
        """,
        (claim_id,),
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


def list_document_metadata_for_claim(connection: sqlite3.Connection, claim_id: str) -> list[dict[str, Any]]:
    rows = connection.execute(
        """
        SELECT metadata_json
        FROM (
          SELECT document_type, document_id, metadata_json
          FROM document_metadata
          WHERE claim_id = ?
          UNION ALL
          SELECT document_type, document_id, metadata_json
          FROM uploaded_document_metadata
          WHERE claim_id = ?
        )
        ORDER BY document_type ASC, document_id ASC
        """,
        (claim_id, claim_id),
    ).fetchall()
    return [json.loads(row[0]) for row in rows]


def get_document_metadata(connection: sqlite3.Connection, document_id: str) -> dict[str, Any] | None:
    row = connection.execute(
        "SELECT metadata_json FROM document_metadata WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    if row:
        return json.loads(row[0])
    row = connection.execute(
        "SELECT metadata_json FROM uploaded_document_metadata WHERE document_id = ?",
        (document_id,),
    ).fetchone()
    return json.loads(row[0]) if row else None


def save_uploaded_document(
    connection: sqlite3.Connection,
    metadata: dict[str, Any],
    *,
    claim_table: str = "claim_reviews",
    claim_payload_column: str = "input_payload_json",
) -> None:
    now = _now()
    connection.execute(
        """
        INSERT INTO uploaded_document_metadata (
          document_id, claim_id, document_type, file_path, content_hash,
          text_fingerprint, perceptual_hash, mime_type, file_size, page_count,
          document_status, metadata_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            metadata["document_id"],
            metadata["claim_id"],
            metadata["document_type"],
            metadata["file_path"],
            metadata["content_hash"],
            metadata.get("text_fingerprint", ""),
            metadata.get("perceptual_hash", ""),
            metadata.get("mime_type", "application/pdf"),
            int(metadata["file_size"]),
            int(metadata["page_count"]),
            metadata.get("document_status", "available"),
            json.dumps(metadata, ensure_ascii=False),
            now,
            now,
        ),
    )
    if claim_table not in {"claim_reviews", "claims"} or claim_payload_column not in {
        "input_payload_json",
        "payload_json",
    }:
        raise ValueError("Unsupported claim persistence mapping")
    claim_row = connection.execute(
        f"SELECT {claim_payload_column} FROM {claim_table} WHERE claim_id = ?",
        (metadata["claim_id"],),
    ).fetchone()
    if claim_row:
        claim_payload = json.loads(claim_row[0])
        document_types = list(claim_payload.get("documents") or [])
        if metadata["document_type"] not in document_types:
            document_types.append(metadata["document_type"])
        claim_payload["documents"] = document_types
        if metadata["document_type"] == "medical_receipt":
            claim_payload.setdefault("claim", {})["receipt_hash"] = metadata["content_hash"]
        connection.execute(
            f"UPDATE {claim_table} SET {claim_payload_column} = ?, updated_at = ? WHERE claim_id = ?",
            (
                json.dumps(claim_payload, ensure_ascii=False),
                now,
                metadata["claim_id"],
            ),
        )
    connection.commit()


def _upsert_insured(connection: sqlite3.Connection, split: str, insured: dict[str, Any], now: str) -> None:
    connection.execute(
        """
        INSERT INTO insureds (insured_id, split, payload_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(insured_id, split) DO UPDATE SET
          payload_json=excluded.payload_json,
          updated_at=excluded.updated_at
        """,
        (insured["insured_id"], split, json.dumps(insured, ensure_ascii=False), now, now),
    )


def _upsert_provider(connection: sqlite3.Connection, split: str, provider: dict[str, Any], now: str) -> None:
    connection.execute(
        """
        INSERT INTO providers (provider_id, split, payload_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(provider_id, split) DO UPDATE SET
          payload_json=excluded.payload_json,
          updated_at=excluded.updated_at
        """,
        (provider["provider_id"], split, json.dumps(provider, ensure_ascii=False), now, now),
    )


def _upsert_current_claim(connection: sqlite3.Connection, split: str, claim: dict[str, Any], now: str) -> None:
    connection.execute(
        """
        INSERT INTO fraud_current_claims (claim_id, split, payload_json, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(claim_id) DO UPDATE SET
          split=excluded.split,
          payload_json=excluded.payload_json,
          updated_at=excluded.updated_at
        """,
        (claim["claim_id"], split, json.dumps(claim, ensure_ascii=False), now, now),
    )


def _upsert_historical_claim(connection: sqlite3.Connection, split: str, historical: dict[str, Any], now: str) -> None:
    claim = historical["claim"]
    connection.execute(
        """
        INSERT INTO historical_claims (
          claim_id, split, history_for_claim_id, insured_id, provider_id,
          receipt_id, receipt_hash, diagnosis_code, treatment_code,
          treatment_start_date, payload_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(claim_id) DO UPDATE SET
          split=excluded.split,
          history_for_claim_id=excluded.history_for_claim_id,
          insured_id=excluded.insured_id,
          provider_id=excluded.provider_id,
          receipt_id=excluded.receipt_id,
          receipt_hash=excluded.receipt_hash,
          diagnosis_code=excluded.diagnosis_code,
          treatment_code=excluded.treatment_code,
          treatment_start_date=excluded.treatment_start_date,
          payload_json=excluded.payload_json,
          updated_at=excluded.updated_at
        """,
        (
            historical["claim_id"],
            split,
            historical.get("history_for_claim_id"),
            historical["insured_profile"]["insured_id"],
            claim["provider_id"],
            claim["receipt_id"],
            claim["receipt_hash"],
            claim["diagnosis_code"],
            claim["treatment_code"],
            claim["treatment_start_date"],
            json.dumps(historical, ensure_ascii=False),
            now,
            now,
        ),
    )


def _upsert_document_metadata(connection: sqlite3.Connection, split: str, metadata: dict[str, Any], now: str) -> None:
    connection.execute(
        """
        INSERT INTO document_metadata (
          document_id, split, claim_id, document_type, file_path,
          content_hash, text_fingerprint, perceptual_hash, mime_type,
          file_size, page_count, document_status, metadata_json, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id) DO UPDATE SET
          split=excluded.split,
          claim_id=excluded.claim_id,
          document_type=excluded.document_type,
          file_path=excluded.file_path,
          content_hash=excluded.content_hash,
          text_fingerprint=excluded.text_fingerprint,
          perceptual_hash=excluded.perceptual_hash,
          mime_type=excluded.mime_type,
          file_size=excluded.file_size,
          page_count=excluded.page_count,
          document_status=excluded.document_status,
          metadata_json=excluded.metadata_json,
          updated_at=excluded.updated_at
        """,
        (
            metadata["document_id"],
            split,
            metadata["claim_id"],
            metadata["document_type"],
            metadata["file_path"],
            metadata.get("content_hash"),
            metadata.get("text_fingerprint"),
            metadata.get("perceptual_hash"),
            metadata.get("mime_type", "application/pdf"),
            int(metadata.get("file_size") or 0),
            int(metadata.get("page_count") or 0),
            metadata.get("document_status", "available"),
            json.dumps(metadata, ensure_ascii=False),
            now,
            now,
        ),
    )


def _upsert_claim_document(connection: sqlite3.Connection, split: str, link: dict[str, Any], now: str) -> None:
    connection.execute(
        """
        INSERT INTO claim_documents (claim_id, document_id, split, document_type, created_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(claim_id, document_id) DO UPDATE SET
          split=excluded.split,
          document_type=excluded.document_type
        """,
        (link["claim_id"], link["document_id"], split, link["document_type"], now),
    )


def _run_id(
    split: str,
    source_files: list[str],
    seed_rows: list[dict[str, Any]],
    historical_claims: list[dict[str, Any]],
    document_metadata: list[dict[str, Any]],
    claim_document_links: list[dict[str, Any]],
) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "split": split,
                "source_files": sorted(source_files),
                "counts": [
                    len(seed_rows),
                    len(historical_claims),
                    len(document_metadata),
                    len(claim_document_links),
                ],
            },
            ensure_ascii=False,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"fraud-context-{split}-{digest}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
