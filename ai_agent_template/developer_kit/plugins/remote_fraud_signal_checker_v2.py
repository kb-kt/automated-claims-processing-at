from __future__ import annotations

import json
import os
import socket
import time
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from ai_agent_template.developer_kit.plugin_interface.tool_plugin import failure, success


_RAW_EVIDENCE_BLOCKED_SIGNALS = {
    "suspected_duplicate_receipt",
    "fraudulent_document",
    "document_claim_mismatch",
    "abnormal_document_dates",
}
_FORBIDDEN_RESPONSE_FIELDS = {
    "pay",
    "partial_pay",
    "deny",
    "payable_amount",
    "recommended_payable_amount",
    "recommended_decision",
}
_REQUIRED_V2_FIELDS = {
    "schema_version",
    "request_id",
    "claim_id",
    "status",
    "fraud_suspected",
    "fraud_reason_codes",
    "risk_score",
    "routing",
    "requires_human_review",
    "engine_version",
    "workflow_version",
}


class RemoteFraudSignalCheckerV2Plugin:
    name = "fraud_signal_checker"
    version = "2.0.0"
    contract_name = "fraud_signal_checker"
    contract_version = "1.0.0"
    owner = "fraud-check"
    timeout_ms = 15000
    failure_policy = "human_review"
    source_system = "automated_claims_processing_template"

    def __init__(
        self,
        service_url: str | None = None,
        timeout_ms: int | None = None,
        claims_internal_base_url: str | None = None,
        analysis_mode: str | None = None,
    ):
        self.service_url = (
            service_url
            or os.environ.get("FRAUD_CHECK_URL")
            or "http://127.0.0.1:8010"
        ).rstrip("/")
        self.timeout_ms = int(
            timeout_ms
            or os.environ.get("FRAUD_CHECK_V2_TIMEOUT_MS")
            or self.timeout_ms
        )
        self.claims_internal_base_url = (
            claims_internal_base_url
            or os.environ.get("CLAIMS_INTERNAL_BASE_URL")
            or ""
        ).rstrip("/")
        self.analysis_mode = (
            analysis_mode
            or os.environ.get("FRAUD_ANALYSIS_MODE")
            or "raw_evidence"
        )

    def run(self, payload: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        started = time.perf_counter()
        request_id = f"REQ-ACP-{uuid.uuid4().hex[:16].upper()}"
        try:
            request_body = self._build_request(payload, context, request_id)
            remote_result = self._post(request_body)
        except HTTPError as exc:
            try:
                return self._failure(
                    "REMOTE_HTTP_ERROR",
                    f"Fraud_Check returned HTTP {exc.code}.",
                    started,
                    request_id=request_id,
                    retryable=500 <= int(exc.code) <= 599,
                )
            finally:
                exc.close()
        except socket.timeout:
            return self._failure("REMOTE_TIMEOUT", "Fraud_Check request timed out.", started, request_id=request_id, retryable=True)
        except TimeoutError:
            return self._failure("REMOTE_TIMEOUT", "Fraud_Check request timed out.", started, request_id=request_id, retryable=True)
        except URLError as exc:
            if _is_timeout_reason(exc.reason):
                return self._failure("REMOTE_TIMEOUT", "Fraud_Check request timed out.", started, request_id=request_id, retryable=True)
            return self._failure(
                "REMOTE_CONNECTION_ERROR",
                "Fraud_Check connection failed.",
                started,
                request_id=request_id,
                retryable=True,
            )
        except json.JSONDecodeError:
            return self._failure("REMOTE_INVALID_JSON", "Fraud_Check returned invalid JSON.", started, request_id=request_id)
        except FraudContextFetchError as exc:
            return self._failure(
                exc.error_code,
                exc.message,
                started,
                request_id=request_id,
                retryable=exc.retryable,
            )
        except Exception as exc:
            return self._failure(
                "REMOTE_UNEXPECTED_ERROR",
                f"Fraud_Check v2 request failed: {type(exc).__name__}.",
                started,
                request_id=request_id,
            )

        validation_error = _validate_v2_response(remote_result, request_body)
        if validation_error:
            return self._failure("REMOTE_CONTRACT_ERROR", validation_error, started, request_id=request_id)
        if remote_result.get("status") == "failed" or remote_result.get("tool_failures"):
            return self._failure(
                "REMOTE_TOOL_FAILURE",
                "Fraud_Check v2 reported an internal tool failure.",
                started,
                request_id=request_id,
                retryable=True,
            )
        return self._success(remote_result, started)

    def _build_request(self, payload: dict[str, Any], context: dict[str, Any], request_id: str) -> dict[str, Any]:
        claim_payload = dict(context.get("claim_payload") or {})
        claim_id = str(claim_payload.get("claim_id") or payload.get("claim_id") or "")
        if not claim_id:
            raise FraudContextFetchError("MISSING_CLAIM_ID", "claim_id is required for Fraud_Check v2.")

        claim = dict(payload.get("claim") or claim_payload.get("claim") or {})
        insured_profile = dict(payload.get("insured_profile") or claim_payload.get("insured_profile") or {})
        fraud_context: dict[str, Any] | None = None
        documents_response: dict[str, Any] | None = None
        if self.claims_internal_base_url:
            fraud_context = self._get_json(f"/internal/v1/fraud-context/claims/{claim_id}")
            documents_response = self._get_json(f"/internal/v1/claims/{claim_id}/documents")

        document_metadata = list((fraud_context or {}).get("document_metadata") or [])
        if not document_metadata and documents_response:
            document_metadata = list(documents_response.get("documents") or [])
        document_refs = [
            {
                "document_id": item.get("document_id"),
                "document_type": item.get("document_type"),
                "content_hash": item.get("content_hash"),
                "mime_type": item.get("mime_type", "application/pdf"),
            }
            for item in document_metadata
            if item.get("document_id")
        ]
        inline_context = {
            "claim_history": (fraud_context or {}).get("claim_history"),
            "document_metadata": document_metadata,
            "historical_document_fingerprints": (fraud_context or {}).get("historical_document_fingerprints", []),
        }
        if not self.claims_internal_base_url:
            inline_context["claim_history"] = dict(payload.get("claim_history") or {})

        return {
            "schema_version": "2.0.0",
            "request_id": request_id,
            "claim_id": claim_id,
            "source_system": self.source_system,
            "analysis_mode": self.analysis_mode,
            "claim": _v2_claim_fields(claim),
            "insured_profile": {"insured_id": insured_profile.get("insured_id")},
            "document_refs": document_refs,
            "inline_context": inline_context,
            "upstream_signals": self._upstream_signals(payload),
            "options": {
                "include_evidence": True,
                "include_tool_trace": False,
                "strict_schema": True,
            },
        }

    def _upstream_signals(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.analysis_mode == "raw_evidence":
            return {}
        signals = dict(payload.get("signals") or {})
        assisted: dict[str, Any] = {}
        for key, value in signals.items():
            if key in _RAW_EVIDENCE_BLOCKED_SIGNALS and isinstance(value, bool):
                assisted[key] = {
                    "signal": key,
                    "value": value,
                    "source": "automated_claims_processing",
                    "detector_version": "1.0.0",
                }
        return assisted

    def _get_json(self, path: str) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        api_key = os.environ.get("CLAIMS_INTERNAL_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        try:
            request = Request(f"{self.claims_internal_base_url}{path}", headers=headers, method="GET")
            with urlopen(request, timeout=self.timeout_ms / 1000) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            try:
                raise FraudContextFetchError(
                    "CLAIMS_INTERNAL_HTTP_ERROR",
                    f"Claims internal API returned HTTP {exc.code}.",
                    retryable=500 <= int(exc.code) <= 599,
                ) from exc
            finally:
                exc.close()
        except json.JSONDecodeError as exc:
            raise FraudContextFetchError(
                "CLAIMS_INTERNAL_INVALID_JSON",
                "Claims internal API returned invalid JSON.",
            ) from exc
        except (URLError, TimeoutError, socket.timeout) as exc:
            raise FraudContextFetchError(
                "CLAIMS_INTERNAL_UNAVAILABLE",
                "Claims internal API is unavailable.",
                retryable=True,
            ) from exc

    def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        api_key = os.environ.get("FRAUD_CHECK_API_KEY")
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        request = Request(
            f"{self.service_url}/v2/fraud/check",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with urlopen(request, timeout=self.timeout_ms / 1000) as response:
            return json.loads(response.read().decode("utf-8"))

    def _success(self, result: dict[str, Any], started: float) -> dict[str, Any]:
        response = {
            "fraud_suspected": bool(result["fraud_suspected"]),
            "fraud_reason_codes": list(result["fraud_reason_codes"]),
            "risk_score": int(result["risk_score"]),
            "routing": str(result["routing"]),
            "requires_human_review": bool(result["requires_human_review"]),
            "engine_version": str(result["engine_version"]),
        }
        for field in [
            "workflow_version",
            "request_id",
            "document_findings",
            "history_findings",
            "evidence",
            "analysis_warnings",
            "tool_failures",
        ]:
            if field in result:
                response[field] = result[field]
        return success(
            self.name,
            response,
            plugin_version=self.version,
            contract_version=self.contract_version,
            duration_ms=_duration_ms(started),
            metadata={
                "api_version": "v2",
                "analysis_mode": self.analysis_mode,
                "request_id": str(result["request_id"]),
                "engine_version": str(result["engine_version"]),
                "workflow_version": str(result["workflow_version"]),
                "routing": str(result["routing"]),
            },
        )

    def _failure(
        self,
        error_code: str,
        message: str,
        started: float,
        *,
        request_id: str | None = None,
        retryable: bool = False,
    ) -> dict[str, Any]:
        metadata = {
            "api_version": "v2",
            "analysis_mode": self.analysis_mode,
            "failure_policy": self.failure_policy,
        }
        if request_id:
            metadata["request_id"] = request_id
        return failure(
            self.name,
            error_code,
            message,
            plugin_version=self.version,
            contract_version=self.contract_version,
            retryable=retryable,
            duration_ms=_duration_ms(started),
            metadata=metadata,
        )


class FraudContextFetchError(Exception):
    def __init__(self, error_code: str, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.retryable = retryable


def _v2_claim_fields(claim: dict[str, Any]) -> dict[str, Any]:
    fields = [
        "receipt_id",
        "receipt_hash",
        "provider_id",
        "claimed_amount",
        "claim_date",
        "treatment_start_date",
        "treatment_end_date",
        "diagnosis_code",
        "treatment_code",
    ]
    return {field: claim.get(field) for field in fields}


def _validate_v2_response(result: Any, request_body: dict[str, Any]) -> str | None:
    if not isinstance(result, dict):
        return "Fraud_Check v2 response must be a JSON object."
    forbidden = sorted(_FORBIDDEN_RESPONSE_FIELDS.intersection(result))
    if forbidden:
        return f"Fraud_Check v2 response includes forbidden payment fields: {', '.join(forbidden)}."
    missing = sorted(_REQUIRED_V2_FIELDS - set(result))
    if missing:
        return f"Fraud_Check v2 response is missing required fields: {', '.join(missing)}."
    if result["schema_version"] != "2.0.0":
        return "schema_version must be 2.0.0."
    if result["request_id"] != request_body["request_id"]:
        return "request_id mismatch."
    if result["claim_id"] != request_body["claim_id"]:
        return "claim_id mismatch."
    if result["status"] not in {"success", "completed", "failed"}:
        return "status must be success, completed, or failed."
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
    if not isinstance(result["requires_human_review"], bool):
        return "requires_human_review must be boolean."
    if not isinstance(result["engine_version"], str) or not result["engine_version"].strip():
        return "engine_version must be a non-empty string."
    if not isinstance(result["workflow_version"], str) or not result["workflow_version"].strip():
        return "workflow_version must be a non-empty string."
    if result["fraud_suspected"] and (
        result["routing"] != "human_review" or result["requires_human_review"] is not True
    ):
        return "fraud_suspected=true requires routing=human_review and requires_human_review=true."
    if result["status"] == "failed" and result["routing"] != "human_review":
        return "failed Fraud_Check status requires routing=human_review."
    tool_failures = result.get("tool_failures")
    if tool_failures and result["routing"] != "human_review":
        return "tool_failures require routing=human_review."
    return None


def _is_timeout_reason(reason: Any) -> bool:
    return isinstance(reason, (TimeoutError, socket.timeout)) or "timed out" in str(reason).lower()


def _duration_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)
