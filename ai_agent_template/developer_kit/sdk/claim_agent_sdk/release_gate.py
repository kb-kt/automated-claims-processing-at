from __future__ import annotations

import operator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .errors import EvaluationError


_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "==": operator.eq,
    ">=": operator.ge,
    "<=": operator.le,
    ">": operator.gt,
    "<": operator.lt,
}


@dataclass(frozen=True)
class Threshold:
    category: str
    metric: str
    operator: str
    target: float


class ReleaseGate:
    """Evaluate metrics against the Template-owned release thresholds."""

    def __init__(self, thresholds: list[Threshold]):
        self.thresholds = thresholds

    @classmethod
    def from_file(cls, path: str | Path) -> "ReleaseGate":
        return cls(_parse_thresholds(Path(path)))

    def evaluate(self, metrics: dict[str, Any]) -> dict[str, Any]:
        checks: list[dict[str, Any]] = []
        for threshold in self.thresholds:
            actual = metrics.get(threshold.metric)
            passed = False
            if isinstance(actual, (int, float)) and threshold.operator in _OPERATORS:
                passed = _OPERATORS[threshold.operator](float(actual), threshold.target)
            checks.append(
                {
                    "category": threshold.category,
                    "metric": threshold.metric,
                    "operator": threshold.operator,
                    "target": threshold.target,
                    "actual": actual,
                    "passed": passed,
                    "blocking": threshold.category in {"hard_thresholds", "critical_failure_limits"},
                }
            )
        blocking_failures = [item for item in checks if item["blocking"] and not item["passed"]]
        return {
            "passed": not blocking_failures,
            "checks": checks,
            "blocking_failures": blocking_failures,
        }


def _parse_thresholds(path: Path) -> list[Threshold]:
    if not path.exists():
        raise EvaluationError(f"RELEASE_GATE_CONFIG_NOT_FOUND: {path}")
    thresholds: list[Threshold] = []
    category: str | None = None
    metric: str | None = None
    values: dict[str, str] = {}

    def flush() -> None:
        nonlocal metric, values
        if category and metric:
            if "operator" not in values or "target" not in values:
                raise EvaluationError(f"Invalid release threshold for metric: {metric}")
            op = values["operator"].strip('"\'')
            if op not in _OPERATORS:
                raise EvaluationError(f"Unsupported release threshold operator: {op}")
            thresholds.append(Threshold(category, metric, op, float(values["target"])))
        metric = None
        values = {}

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        stripped = raw_line.strip()
        if indent == 0 and stripped.endswith(":"):
            flush()
            category = stripped[:-1]
        elif indent == 2 and stripped.endswith(":") and category in {
            "hard_thresholds",
            "soft_thresholds",
            "critical_failure_limits",
        }:
            flush()
            metric = stripped[:-1]
        elif indent >= 4 and metric and ":" in stripped:
            key, value = stripped.split(":", 1)
            values[key.strip()] = value.strip()
    flush()
    if not thresholds:
        raise EvaluationError(f"Release threshold file contains no checks: {path}")
    return thresholds
