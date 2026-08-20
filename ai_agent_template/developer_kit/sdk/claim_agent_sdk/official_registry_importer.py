from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


@dataclass(frozen=True)
class RegistrySourceMetadata:
    version: str
    effective_from: str
    source_file: str
    source_url: str = ""
    license_note: str = ""
    effective_to: str | None = None


def load_official_kcd_rows(path: str | Path, metadata: RegistrySourceMetadata) -> list[dict[str, Any]]:
    rows = []
    for raw in _read_rows(path):
        code = _first(raw, ["code", "kcd_code", "KCD", "분류번호", "질병코드"])
        if not code:
            continue
        code_name = _first(raw, ["code_name", "name", "korean_name", "한글명", "질병명", "상병명"]) or code
        rows.append(
            {
                "code_system": "KCD",
                "source_synthetic_code": None,
                "code": code,
                "code_name": code_name,
                "parent_code": str(code).split(".", 1)[0],
                "chapter": _first(raw, ["chapter", "장", "대분류"]),
                "category": _first(raw, ["category", "분류", "중분류"]),
                "valid_from": metadata.effective_from,
                "valid_to": metadata.effective_to,
                "version": metadata.version,
                "aliases": _aliases(raw),
                "source_file": metadata.source_file,
                "source_url": metadata.source_url,
                "license_note": metadata.license_note,
                "synthetic": False,
            }
        )
    return rows


def load_official_edi_rows(path: str | Path, metadata: RegistrySourceMetadata) -> list[dict[str, Any]]:
    rows = []
    for raw in _read_rows(path):
        code = _first(raw, ["code", "edi_code", "procedure_code", "수가코드", "행위코드", "분류코드"])
        if not code:
            continue
        code_name = _first(raw, ["code_name", "name", "procedure_name", "행위명", "한글명", "명칭"]) or code
        rows.append(
            {
                "code_system": "EDI",
                "source_synthetic_code": None,
                "code": code,
                "code_name": code_name,
                "procedure_group": _first(raw, ["procedure_group", "group", "분류유형", "분류"]),
                "benefit_category": _first(raw, ["benefit_category", "급여구분", "covered_type"]) or "unknown",
                "valid_from": metadata.effective_from,
                "valid_to": metadata.effective_to,
                "version": metadata.version,
                "aliases": _aliases(raw),
                "source_file": metadata.source_file,
                "source_url": metadata.source_url,
                "license_note": metadata.license_note,
                "synthetic": False,
            }
        )
    return rows


def load_insurer_medical_routing_rules(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    rows = data if isinstance(data, list) else data.get("rules", [])
    if not isinstance(rows, list):
        raise ValueError("Insurer medical routing rules must be a JSON array or an object with rules[].")
    normalized = []
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Each insurer medical routing rule must be an object.")
        required = [
            "rule_id",
            "rule_version",
            "routing",
            "reason_code",
            "default_confidence",
            "approval_status",
            "owner",
            "effective_from",
        ]
        missing = [field for field in required if row.get(field) in (None, "")]
        if missing:
            raise ValueError(f"Insurer medical routing rule missing required fields: {missing}")
        if row["routing"] not in {"continue_claim_review", "request_documents", "human_review"}:
            raise ValueError(f"Invalid routing: {row['routing']}")
        if row["approval_status"] not in {"synthetic_insurer_approved", "insurer_approved", "draft", "deprecated"}:
            raise ValueError(f"Invalid approval_status: {row['approval_status']}")
        normalized.append({**row, "synthetic": bool(row.get("synthetic", False))})
    return normalized


def write_registry_json(path: str | Path, rows: list[dict[str, Any]]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _read_rows(path: str | Path) -> list[dict[str, Any]]:
    source = Path(path)
    if source.suffix.lower() == ".json":
        data = json.loads(source.read_text(encoding="utf-8"))
        rows = data if isinstance(data, list) else data.get("rows", [])
        if not isinstance(rows, list):
            raise ValueError(f"JSON registry source must be a list or object with rows[]: {source}")
        return [row for row in rows if isinstance(row, dict)]
    encodings = ["utf-8-sig", "cp949", "euc-kr"]
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            with source.open("r", encoding=encoding, newline="") as file:
                return list(csv.DictReader(file))
        except UnicodeError as exc:
            last_error = exc
    raise ValueError(f"Could not read registry CSV with supported encodings: {source}") from last_error


def _first(row: dict[str, Any], names: Iterable[str]) -> str | None:
    normalized = {_clean_key(key): value for key, value in row.items()}
    for name in names:
        value = normalized.get(_clean_key(name))
        if value not in (None, ""):
            return str(value).strip()
    return None


def _aliases(row: dict[str, Any]) -> list[str]:
    values = []
    for key in ("aliases", "alias", "동의어", "영문명", "english_name"):
        value = _first(row, [key])
        if value:
            values.extend(part.strip() for part in value.replace("|", ",").split(",") if part.strip())
    return list(dict.fromkeys(values))


def _clean_key(value: Any) -> str:
    return str(value).strip().lower().replace(" ", "_")
