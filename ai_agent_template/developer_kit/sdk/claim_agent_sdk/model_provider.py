from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


class ModelProvider(Protocol):
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


class MockModelProvider:
    provider_name = "mock"
    model_id = "mock-reviewer"
    version = "1.0.0"

    def generate_json(
        self,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "review_summary": options.get(
                "fallback_summary",
                "Structured tool results were used to prepare a reviewer-facing recommendation.",
            )
        }


@dataclass(frozen=True)
class HostedLLMProvider:
    provider_name: str
    model_id: str
    base_url: str
    api_key: str
    temperature: float = 0
    response_format: str = "json_schema"
    timeout_ms: int = 30000
    version: str = "1.0.0"

    def generate_json(
        self,
        messages: list[dict[str, str]],
        output_schema: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        body = {
            "model": self.model_id,
            "messages": messages,
            "temperature": float(options.get("temperature", self.temperature)),
        }
        if self.response_format == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": options.get("schema_name", "claim_review_narrative"),
                    "strict": False,
                    "schema": output_schema,
                },
            }
        elif self.response_format:
            body["response_format"] = {"type": self.response_format}

        request = urllib.request.Request(
            _chat_completions_url(self.base_url),
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=float(options.get("timeout_ms", self.timeout_ms)) / 1000,
            ) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise RuntimeError(f"Hosted model request failed: {exc}") from exc

        message = (payload.get("choices") or [{}])[0].get("message", {})
        if isinstance(message.get("parsed"), dict):
            return message["parsed"]
        content = message.get("content")
        if isinstance(content, list):
            content = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict)
            )
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("Hosted model response did not include JSON content.")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise RuntimeError("Hosted model response content is not valid JSON.") from exc


def load_model_provider_from_config(config_path: str | Path, provider_name: str | None = None) -> ModelProvider:
    config = _parse_model_yaml(Path(config_path))
    active = provider_name or config.get("active_provider", "mock")
    providers = config.get("providers", {})
    active_config = providers.get(active, {})
    if active == "mock" or active_config.get("provider_type") == "mock":
        return MockModelProvider()
    return HostedLLMProvider(
        provider_name=active,
        model_id=active_config.get("model_id", active_config.get("model_name", active)),
        base_url=_resolve_env(active_config.get("base_url", "")),
        api_key=_resolve_env(active_config.get("api_key", "")),
        temperature=float(active_config.get("temperature", 0) or 0),
        response_format=active_config.get("response_format", "json_schema"),
        timeout_ms=int(active_config.get("timeout_ms", 30000) or 30000),
    )


def load_model_provider_config(config_path: str | Path, provider_name: str) -> dict[str, Any]:
    return dict(_parse_model_yaml(Path(config_path)).get("providers", {}).get(provider_name, {}))


def _parse_model_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"active_provider": "mock", "providers": {"mock": {"provider_type": "mock"}}}
    result: dict[str, Any] = {"providers": {}}
    current_provider: str | None = None
    in_providers = False
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        stripped = raw_line.strip()
        indent = len(raw_line) - len(raw_line.lstrip(" "))
        if indent == 0 and ":" in stripped:
            key, value = stripped.split(":", 1)
            if key == "providers":
                in_providers = True
            else:
                result[key] = _clean_yaml_value(value)
            continue
        if in_providers and indent == 2 and stripped.endswith(":"):
            current_provider = stripped[:-1]
            result["providers"][current_provider] = {}
            continue
        if current_provider and indent >= 4 and ":" in stripped:
            key, value = stripped.split(":", 1)
            result["providers"][current_provider][key.strip()] = _clean_yaml_value(value)
    return result


def _clean_yaml_value(value: str) -> str:
    value = value.strip()
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        value = value[1:-1]
    return _resolve_env(value)


def _resolve_env(value: str) -> str:
    value = str(value)
    if value.startswith("${") and value.endswith("}"):
        return os.environ.get(value[2:-1], "")
    return value


def _chat_completions_url(base_url: str) -> str:
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return f"{base}/chat/completions"
