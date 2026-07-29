from __future__ import annotations

from typing import Any


def mask_identifier(value: str | None, *, visible_tail: int = 4) -> str | None:
    if value in (None, ""):
        return value
    text = str(value)
    if len(text) <= visible_tail:
        return "*" * len(text)
    return f"{'*' * max(3, len(text) - visible_tail)}{text[-visible_tail:]}"


def mask_queue_item(item: dict[str, Any]) -> dict[str, Any]:
    masked = dict(item)
    masked["policy_id_masked"] = mask_identifier(item.get("policy_id"))
    masked.pop("policy_id", None)
    return masked
