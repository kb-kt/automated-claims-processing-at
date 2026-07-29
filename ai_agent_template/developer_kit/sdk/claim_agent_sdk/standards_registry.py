from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .template_loader import TemplateBundle


@dataclass(frozen=True)
class StandardCode:
    code: str
    attributes: dict[str, str]


class StandardsRegistry:
    def __init__(self, template: TemplateBundle):
        self.template = template
        self._registries: dict[str, list[StandardCode]] = {}

    def list_decision_codes(self) -> list[str]:
        return self._codes("decision_codes.yaml")

    def list_coverage_codes(self) -> list[str]:
        return self._codes("coverage_codes.yaml")

    def list_document_codes(self) -> list[str]:
        return self._codes("document_codes.yaml")

    def list_reason_codes(self) -> list[str]:
        return self._codes("reason_codes.yaml")

    def is_valid_decision(self, code: str) -> bool:
        return code in set(self.list_decision_codes())

    def is_valid_reason(self, code: str) -> bool:
        return code in set(self.list_reason_codes())

    def coverage_name(self, coverage_code: str) -> str:
        for item in self._load("coverage_codes.yaml"):
            if item.code == coverage_code:
                return item.attributes.get("label_ko", coverage_code)
        return coverage_code

    def _codes(self, file_name: str) -> list[str]:
        return [item.code for item in self._load(file_name)]

    def _load(self, file_name: str) -> list[StandardCode]:
        if file_name not in self._registries:
            path = self.template.require(Path("standards") / file_name)
            self._registries[file_name] = _parse_standard_codes(path)
        return self._registries[file_name]


def _parse_standard_codes(path: Path) -> list[StandardCode]:
    codes: list[StandardCode] = []
    current: dict[str, str] | None = None
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- code:"):
            if current:
                codes.append(StandardCode(code=current["code"], attributes=current))
            current = {"code": _clean_yaml_value(stripped.split(":", 1)[1])}
            continue
        if current and ":" in stripped and not stripped.startswith("-"):
            key, value = stripped.split(":", 1)
            current[key.strip()] = _clean_yaml_value(value)
    if current:
        codes.append(StandardCode(code=current["code"], attributes=current))
    return codes


def _clean_yaml_value(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value

