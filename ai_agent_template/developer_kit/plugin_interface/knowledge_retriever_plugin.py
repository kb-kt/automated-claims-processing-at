from __future__ import annotations

from typing import Any, Protocol


class PolicyKnowledgePlugin(Protocol):
    name: str
    version: str
    owner: str
    retrieval_modes: list[str]

    def retrieve(
        self,
        request: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        ...


KnowledgeRetrieverPlugin = PolicyKnowledgePlugin
