from __future__ import annotations

import json
import os
import socket
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_agent_template.developer_kit.plugin_interface.tool_plugin import failure, success


class RemoteFraudSignalCheckerPlugin:
    name = "fraud_signal_checker"
    version = "1.0.0"
    contract_name = "fraud_signal_checker"
    contract_version = "1.0.0"
    owner = "fraud-check"
    timeout_ms = 3000
    failure_policy = "human_review"

    def __init__(self, service_url: str | None = None, timeout_ms: int | None = None):
        self.service_url = (
            service_url
            or os.environ.get("FRAUD_CHECK_URL")
            or "http://127.0.0.1:8010"
        ).rstrip("/")
        self.timeout_ms = int(
            timeout_ms
            or os.environ.get("FRAUD_CHECK_V1_TIMEOUT_MS")
            or self.timeout_ms
        )

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        try:
            remote_result = self._post(payload)
        except HTTPError as exc:
            try:
                return self._failure(
                    "REMOTE_HTTP_ERROR",
                    f"Fraud_Check returned HTTP {exc.code}.",
                    started,
                    retryable=500 <= int(exc.code) <= 599,
                )
            finally:
                exc.close()
        except socket.timeout:
            return self._failure("REMOTE_TIMEOUT", "Fraud_Check request timed out.", started, retryable=True)
        except TimeoutError:
            return self._failure("REMOTE_TIMEOUT", "Fraud_Check request timed out.", started, retryable=True)
        except URLError as exc:
            if _is_timeout_reason(exc.reason):
                return self._failure("REMOTE_TIMEOUT", "Fraud_Check request timed out.", started, retryable=True)
            return self._failure(
                "REMOTE_CONNECTION_ERROR",
                "Fraud_Check connection failed.",
                started,
                retryable=True,
            )
        except json.JSONDecodeError:
            return self._failure("REMOTE_INVALID_JSON", "Fraud_Check returned invalid JSON.", started)
        except Exception as exc:
            return self._failure(
                "REMOTE_UNEXPECTED_ERROR",
                f"Fraud_Check request failed: {type(exc).__name__}.",
                started,
            )

        validation_error = _validate_remote_response(remote_result)
        if validation_error:
            return self._failure("REMOTE_CONTRACT_ERROR", validation_error, started)
        return self._success(remote_result, started)

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        api_key = os.environ.get("FRAUD_CHECK_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = Request(
            f"{self.service_url}/v1/fraud/check",
            data=json.dumps(_request_body(payload), ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_ms / 1000) as response:
            return json.loads(response.read().decode("utf-8"))

    def _success(self, result: dict[str, Any], started: float) -> dict[str, Any]:
        return success(
            self.name,
            {
                "fraud_suspected": bool(result["fraud_suspected"]),
                "fraud_reason_codes": list(result["fraud_reason_codes"]),
                "risk_score": int(result["risk_score"]),
                "routing": str(result["routing"]),
                "engine_version": str(result["engine_version"]),
            },
            plugin_version=self.version,
            contract_version=self.contract_version,
            duration_ms=_duration_ms(started),
            metadata={
                "engine_version": str(result["engine_version"]),
                "routing": str(result["routing"]),
            },
        )

    def _failure(
        self,
        error_code: str,
        message: str,
        started: float,
        *,
        retryable: bool = False,
    ) -> dict[str, Any]:
        return failure(
            self.name,
            error_code,
            message,
            plugin_version=self.version,
            contract_version=self.contract_version,
            retryable=retryable,
            duration_ms=_duration_ms(started),
            metadata={"failure_policy": self.failure_policy},
        )


def _request_body(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "claim": dict(payload.get("claim") or {}),
        "claim_history": dict(payload.get("claim_history") or {}),
        "signals": dict(payload.get("signals") or {}),
        "insured_profile": dict(payload.get("insured_profile") or {}),
    }


def _validate_remote_response(result: Any) -> str | None:
    if not isinstance(result, dict):
        return "Fraud_Check response must be a JSON object."
    required = {
        "fraud_suspected",
        "fraud_reason_codes",
        "risk_score",
        "routing",
        "engine_version",
    }
    missing = sorted(required - set(result))
    if missing:
        return f"Fraud_Check response is missing required fields: {', '.join(missing)}."
    if not isinstance(result["fraud_suspected"], bool):
        return "fraud_suspected must be boolean."
    if not isinstance(result["fraud_reason_codes"], list) or not all(
        isinstance(code, str) for code in result["fraud_reason_codes"]
    ):
        return "fraud_reason_codes must be an array of strings."
    if not isinstance(result["risk_score"], (int, float)) or not 0 <= float(result["risk_score"]) <= 100:
        return "risk_score must be a number between 0 and 100."
    if result["routing"] not in {"human_review", "continue_claim_review"}:
        return "routing must be human_review or continue_claim_review."
    if not isinstance(result["engine_version"], str) or not result["engine_version"].strip():
        return "engine_version must be a non-empty string."
    if result["fraud_suspected"] and result["routing"] != "human_review":
        return "fraud_suspected=true requires routing=human_review."
    return None


def _is_timeout_reason(reason: Any) -> bool:
    return isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower()


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
