from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .schema_validator import SchemaValidator
from .template_loader import TemplateBundle


@dataclass(frozen=True)
class PolicyChunk:
    chunk_id: str
    source: str
    section: str
    text: str
    summary: str = ""
    product_id: str = ""
    product_version: str = ""
    effective_date: str = ""
    coverage_code: str = ""
    clause_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {key: value for key, value in asdict(self).items() if value not in ("", {}, None)}


class KeywordPolicyRetriever:
    """Dependency-free policy retriever used to keep the template RAG-ready.

    This is not a production vector store. It implements the same retrieval
    request/result contract that a future vector or hybrid retriever should use.
    """

    name = "keyword_policy_retriever"
    version = "1.0.0"
    owner = "claim-review-template"
    retrieval_modes = ["keyword"]

    def __init__(
        self,
        chunks: list[PolicyChunk],
        *,
        validator: SchemaValidator | None = None,
    ):
        self.chunks = chunks
        self.validator = validator

    @classmethod
    def from_template(cls, template: TemplateBundle) -> "KeywordPolicyRetriever":
        product = _load_first_json(template.product_json_candidates())
        policy_path = _first_existing(template.policy_document_candidates())
        chunks: list[PolicyChunk] = []
        if policy_path:
            chunks.extend(_chunks_from_markdown(policy_path, product))
        if product:
            chunks.extend(_chunks_from_product(product))
        validator = SchemaValidator(template)
        for chunk in chunks:
            validator.validate_policy_chunk(chunk.to_dict())
        return cls(chunks, validator=validator)

    def retrieve(
        self,
        request: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if self.validator:
            self.validator.validate_retrieval_request(request)

        query = request["query"]
        top_k = int(request.get("top_k") or 3)
        filters = request.get("filters") or {}
        query_terms = _terms(query)
        candidates = [chunk for chunk in self.chunks if _matches_filters(chunk, filters)]

        scored = [
            (_score(query_terms, chunk), chunk)
            for chunk in candidates
        ]
        scored.sort(key=lambda item: item[0], reverse=True)
        if any(score > 0 for score, _chunk in scored):
            selected = [(score, chunk) for score, chunk in scored if score > 0][:top_k]
        else:
            selected = scored[:top_k]

        result = {
            "query": query,
            "matches": [
                _match_from_chunk(chunk, score)
                for score, chunk in selected
            ],
            "metadata": {
                "retriever": self.name,
                "retriever_version": self.version,
                "retrieval_mode": "keyword",
                "top_k": top_k,
                "candidate_count": len(candidates),
            },
        }
        if self.validator:
            self.validator.validate_retrieval_result(result)
        return result


def _load_first_json(paths: list[Path]) -> dict[str, Any]:
    path = _first_existing(paths)
    if not path:
        return {}
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def _first_existing(paths: list[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def _chunks_from_markdown(path: Path, product: dict[str, Any]) -> list[PolicyChunk]:
    text = path.read_text(encoding="utf-8")
    chunks: list[PolicyChunk] = []
    current_section = "document"
    current_lines: list[str] = []
    section_index = 0

    def flush() -> None:
        nonlocal section_index, current_lines
        body = "\n".join(line for line in current_lines if line.strip()).strip()
        if not body:
            current_lines = []
            return
        section_index += 1
        chunks.append(
            PolicyChunk(
                chunk_id=f"POLICY-DOC-{section_index:03d}",
                source=path.name,
                section=current_section,
                text=body,
                summary=_summarize(body),
                product_id=str(product.get("product_id", "")),
                product_version=str(product.get("version", "")),
                effective_date=str(product.get("effective_date", "")),
                clause_id=f"CLAUSE-{section_index:03d}",
                metadata={"chunk_source": "markdown"},
            )
        )
        current_lines = []

    for raw_line in text.splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("#"):
            flush()
            current_section = stripped.lstrip("#").strip() or "document"
        else:
            current_lines.append(raw_line)
    flush()
    return chunks


def _chunks_from_product(product: dict[str, Any]) -> list[PolicyChunk]:
    chunks: list[PolicyChunk] = []
    product_id = str(product.get("product_id", ""))
    product_version = str(product.get("version", ""))
    effective_date = str(product.get("effective_date", ""))
    for index, coverage in enumerate(product.get("coverages", []), start=1):
        coverage_code = str(coverage.get("coverage_code", ""))
        name = str(coverage.get("name", coverage_code))
        required_documents = ", ".join(coverage.get("required_documents", []))
        text = " ".join(
            [
                f"coverage_code={coverage_code}",
                f"name={name}",
                f"care_setting={coverage.get('care_setting', '')}",
                f"benefit_category={coverage.get('benefit_category', '')}",
                f"limit_per_claim={coverage.get('limit_per_claim', '')}",
                f"annual_limit={coverage.get('annual_limit', '')}",
                f"required_documents={required_documents}",
            ]
        )
        chunks.append(
            PolicyChunk(
                chunk_id=f"PRODUCT-COVERAGE-{index:03d}",
                source="products.json",
                section=name,
                text=text,
                summary=f"{name} coverage rule from structured product data.",
                product_id=product_id,
                product_version=product_version,
                effective_date=effective_date,
                coverage_code=coverage_code,
                clause_id=f"COVERAGE-{index:03d}",
                metadata={"chunk_source": "structured_product"},
            )
        )
    return chunks


def _match_from_chunk(chunk: PolicyChunk, score: float) -> dict[str, Any]:
    item = chunk.to_dict()
    match = {
        "chunk_id": item["chunk_id"],
        "source": item["source"],
        "section": item["section"],
        "summary": item.get("summary") or _summarize(item["text"]),
        "text": item["text"],
        "product_id": item.get("product_id", ""),
        "product_version": item.get("product_version", ""),
        "effective_date": item.get("effective_date", ""),
        "coverage_code": item.get("coverage_code", ""),
        "clause_id": item.get("clause_id", ""),
        "citation_id": f"{item['source']}#{item.get('clause_id') or item['chunk_id']}",
        "retrieval_score": round(max(0.0, min(score, 1.0)), 4),
        "retrieval_method": "keyword",
    }
    return {key: value for key, value in match.items() if value not in ("", None)}


def _matches_filters(chunk: PolicyChunk, filters: dict[str, Any]) -> bool:
    for key, expected in filters.items():
        if expected in ("", None):
            continue
        if str(getattr(chunk, key, "")) != str(expected):
            return False
    return True


def _score(query_terms: set[str], chunk: PolicyChunk) -> float:
    if not query_terms:
        return 0.0
    haystack = _terms(" ".join([chunk.section, chunk.text, chunk.summary, chunk.coverage_code]))
    overlap = query_terms & haystack
    return len(overlap) / max(len(query_terms), 1)


def _terms(text: str) -> set[str]:
    return {term for term in re.findall(r"\w+", text.lower()) if len(term) > 1}


def _summarize(text: str, limit: int = 180) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 3].rstrip() + "..."
