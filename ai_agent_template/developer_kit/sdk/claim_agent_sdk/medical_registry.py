from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class MedicalRegistryBundle:
    medical_code_registry: list[dict[str, Any]]
    edi_code_registry: list[dict[str, Any]]
    diagnosis_treatment_rules: list[dict[str, Any]]
    insurer_medical_routing_rules: list[dict[str, Any]]

    @classmethod
    def from_generated_dir(cls, generated_dir: str | Path) -> "MedicalRegistryBundle":
        root = Path(generated_dir)
        return cls(
            medical_code_registry=_read_json(root / "medical_code_registry.json"),
            edi_code_registry=_read_json(root / "edi_code_registry.json"),
            diagnosis_treatment_rules=_read_json(root / "diagnosis_treatment_rules.json"),
            insurer_medical_routing_rules=_read_json_optional(root / "insurer_medical_routing_rules.json"),
        )

    def kcd_by_submitted_code(self, submitted_code: str) -> dict[str, Any] | None:
        return _find_by_code_or_source(self.medical_code_registry, submitted_code)

    def edi_by_submitted_code(self, submitted_code: str) -> dict[str, Any] | None:
        return _find_by_code_or_source(self.edi_code_registry, submitted_code)

    def diagnosis_treatment_rule(self, kcd_code: str, edi_code: str) -> dict[str, Any] | None:
        for row in self.diagnosis_treatment_rules:
            if row.get("kcd_code") == kcd_code and row.get("edi_code") == edi_code:
                return row
        return None

    def insurer_medical_routing_rule(self, rule_id: str) -> dict[str, Any] | None:
        for row in self.insurer_medical_routing_rules:
            if row.get("rule_id") == rule_id:
                return row
        return None


def _find_by_code_or_source(rows: list[dict[str, Any]], code: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("code") == code or row.get("source_synthetic_code") == code:
            return row
    return None


def _read_json(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _read_json_optional(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return _read_json(path)
