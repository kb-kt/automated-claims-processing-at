from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable


ResponseProvider = Callable[[dict[str, Any], dict[str, str]], tuple[int, Any]]


class FraudCheckTestServer:
    def __init__(self, provider: ResponseProvider, *, delay_seconds: float = 0):
        self.provider = provider
        self.delay_seconds = delay_seconds
        self.requests: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("server is not running")
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def __enter__(self) -> "FraudCheckTestServer":
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                length = int(self.headers.get("Content-Length", "0"))
                raw_body = self.rfile.read(length)
                headers = {key: value for key, value in self.headers.items()}
                try:
                    payload = json.loads(raw_body.decode("utf-8"))
                except json.JSONDecodeError:
                    payload = {}
                outer.requests.append(
                    {
                        "path": self.path,
                        "headers": headers,
                        "payload": payload,
                    }
                )
                if outer.delay_seconds:
                    time.sleep(outer.delay_seconds)
                status, body = outer.provider(payload, headers)
                if isinstance(body, str):
                    raw_response = body.encode("utf-8")
                else:
                    raw_response = json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw_response)))
                self.end_headers()
                try:
                    self.wfile.write(raw_response)
                except (BrokenPipeError, ConnectionAbortedError, OSError):
                    pass

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self._server is not None:
            self._server.shutdown() 
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2)


def synthetic_like_fraud_response(payload: dict[str, Any], headers: dict[str, str]) -> tuple[int, dict[str, Any]]:
    claim = payload.get("claim", {})
    claim_history = payload.get("claim_history", {})
    signals = payload.get("signals", {})
    insured_profile = payload.get("insured_profile", {})
    reason_codes: list[str] = []
    receipt_hash = claim.get("receipt_hash")
    receipt_id = claim.get("receipt_id")
    if (
        signals.get("suspected_duplicate_receipt")
        or (receipt_hash and receipt_hash in set(claim_history.get("prior_receipt_hashes", [])))
        or (receipt_id and receipt_id in set(claim_history.get("prior_receipt_ids", [])))
    ):
        reason_codes.append("DUPLICATE_RECEIPT_SUSPECTED")
    if signals.get("fraudulent_document"):
        reason_codes.append("FRAUD_SIGNAL")
    if int(claim_history.get("same_insured_provider_claims_30d", 0)) >= 3 and insured_profile.get("insured_id"):
        reason_codes.append("SAME_INSURED_PROVIDER_REPEAT_SUSPECTED")
    if int(claim_history.get("same_provider_claims_30d", 0)) >= 50 and claim.get("provider_id"):
        reason_codes.append("PROVIDER_PATTERN_ANOMALY_SUSPECTED")
    fraud_suspected = bool(reason_codes)
    return (
        200,
        {
            "fraud_suspected": fraud_suspected,
            "fraud_reason_codes": reason_codes,
            "risk_score": 88 if fraud_suspected else 7,
            "routing": "human_review" if fraud_suspected else "continue_claim_review",
            "engine_version": "test-1.0.0",
        },
    )


def unused_local_url() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        _, port = sock.getsockname()
    return f"http://127.0.0.1:{port}"
