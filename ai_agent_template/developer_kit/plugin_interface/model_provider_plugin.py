from __future__ import annotations

from typing import Any, Protocol


class ModelProviderPlugin(Protocol):
    provider_name: str
    model_id: str
    version: str

    def generate_json(
        self,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        ...

