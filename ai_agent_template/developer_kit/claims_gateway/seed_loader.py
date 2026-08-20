from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Protocol


class FraudSeedRepository(Protocol):
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
        ...


class FraudContextSeedLoader:
    def __init__(self, repository: FraudSeedRepository):
        self.repository = repository

    def load_generated(self, generated_dir: str | Path, *, split: str) -> dict[str, Any]:
        root = Path(generated_dir).resolve()
        normalized_split = split.lower()
        if normalized_split not in {"dev", "eval"}:
            raise ValueError("split must be dev or eval")
        seed_path = root / f"fraud_context_seed_{normalized_split}.jsonl"
        historical_path = root / "historical_claims.jsonl"
        metadata_path = root / f"document_metadata_{normalized_split}.jsonl"
        links_path = root / f"claim_document_links_{normalized_split}.jsonl"
        source_files = [seed_path, historical_path, metadata_path, links_path]
        for path in source_files:
            if not path.exists():
                raise FileNotFoundError(f"Required seed source is missing: {path}")
        return self.repository.seed_fraud_context(
            split=normalized_split,
            seed_rows=_read_jsonl(seed_path),
            historical_claims=[
                row for row in _read_jsonl(historical_path)
                if str(row.get("claim_id", "")).startswith(f"CLM-{normalized_split.upper()}-")
            ],
            document_metadata=_read_jsonl(metadata_path),
            claim_document_links=_read_jsonl(links_path),
            source_files=[str(path) for path in source_files],
        )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}") from exc
    return rows
