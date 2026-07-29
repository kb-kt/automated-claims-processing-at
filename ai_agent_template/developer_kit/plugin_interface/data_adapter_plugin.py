from __future__ import annotations

from typing import Any, Protocol


class DataAdapterPlugin(Protocol):
    adapter_name: str
    version: str
    source_schema_name: str
    target_schema_name: str

    def to_claim_review_input(self, source_payload: dict[str, Any]) -> dict[str, Any]:
        ...

