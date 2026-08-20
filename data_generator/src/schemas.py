from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


JsonDict = dict[str, Any]


@dataclass(frozen=True)
class GenerationConfig:
    seed: int
    product_id: str
    dev_count: int
    eval_count: int
    decision_distribution: dict[str, float]
    claim_type_distribution: dict[str, float]
    amount_ranges: dict[str, dict[str, int]]
    split_policy: dict[str, Any] = field(default_factory=dict)
    fraud_generation: dict[str, Any] = field(default_factory=dict)
    medical_generation: dict[str, Any] = field(default_factory=dict)
    locale: str = "ko-KR"
    currency: str = "KRW"


@dataclass(frozen=True)
class DeductibleRule:
    type: str
    fixed_amount: int | None = None
    rate: float = 0.0


@dataclass(frozen=True)
class Coverage:
    coverage_code: str
    name: str
    care_setting: str
    benefit_category: str
    required_documents: list[str]
    deductible: DeductibleRule
    limit_per_claim: int | None = None
    annual_limit: int | None = None
    annual_count_limit: int | None = None


@dataclass(frozen=True)
class Product:
    product_id: str
    product_name: str
    product_type: str
    currency: str
    raw: JsonDict
    coverages: dict[str, Coverage]


@dataclass(frozen=True)
class CalculationResult:
    claimed_amount: int
    eligible_amount: int
    limit_applied: bool
    deductible_amount: int
    payable_amount: int

    def to_dict(self) -> JsonDict:
        return {
            "claimed_amount": self.claimed_amount,
            "eligible_amount": self.eligible_amount,
            "limit_applied": self.limit_applied,
            "deductible_amount": self.deductible_amount,
            "payable_amount": self.payable_amount,
        }


@dataclass(frozen=True)
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_summary(self) -> JsonDict:
        return {
            "ok": self.ok,
            "error_count": len(self.errors),
            "warning_count": len(self.warnings),
            "errors": self.errors,
            "warnings": self.warnings,
        }
