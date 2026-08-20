from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import TemplateError


@dataclass(frozen=True)
class TemplateBundle:
    """Resolved paths and readers for an ai_agent_template directory."""

    root: Path

    @classmethod
    def load(cls, root: str | Path = "ai_agent_template") -> "TemplateBundle":
        root_path = Path(root).resolve()
        if not root_path.exists():
            raise TemplateError(f"TEMPLATE_ROOT_NOT_FOUND: {root_path}")
        if not (root_path / "schemas" / "claim_review_input.schema.json").exists():
            raise TemplateError(f"SCHEMA_FILE_NOT_FOUND under template root: {root_path}")
        return cls(root=root_path)

    def path(self, relative: str | Path) -> Path:
        path = self.root / relative
        return path.resolve()

    def require(self, relative: str | Path) -> Path:
        path = self.path(relative)
        if not path.exists():
            raise TemplateError(f"Template artifact not found: {relative}")
        return path

    def read_json(self, relative: str | Path) -> dict[str, Any]:
        path = self.require(relative)
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def read_text(self, relative: str | Path) -> str:
        return self.require(relative).read_text(encoding="utf-8")

    @property
    def input_schema(self) -> dict[str, Any]:
        return self.read_json("schemas/claim_review_input.schema.json")

    @property
    def output_schema(self) -> dict[str, Any]:
        return self.read_json("schemas/claim_review_output.schema.json")

    @property
    def policy_chunk_schema(self) -> dict[str, Any]:
        return self.read_json("schemas/policy_chunk.schema.json")

    @property
    def retrieval_request_schema(self) -> dict[str, Any]:
        return self.read_json("schemas/retrieval_request.schema.json")

    @property
    def retrieval_result_schema(self) -> dict[str, Any]:
        return self.read_json("schemas/retrieval_result.schema.json")

    @property
    def agent_report_schema(self) -> dict[str, Any]:
        return self.read_json("schemas/agent_report.schema.json")

    def tool_contracts(self) -> dict[str, dict[str, Any]]:
        contracts_dir = self.require("tools/contracts")
        contracts: dict[str, dict[str, Any]] = {}
        for path in sorted(contracts_dir.glob("*.contract.json")):
            with path.open("r", encoding="utf-8") as file:
                contract = json.load(file)
            contracts[contract["tool_name"]] = contract
        return contracts

    def product_json_candidates(self) -> list[Path]:
        workspace = self.root.parent
        return [
            workspace / "data_generator" / "generated" / "products.json",
            workspace / "data_generator" / "samples" / "products.json",
        ]

    def policy_document_candidates(self) -> list[Path]:
        workspace = self.root.parent
        return [
            workspace / "data_generator" / "generated" / "policy_documents.md",
            workspace / "data_generator" / "samples" / "policy_documents.md",
        ]
