from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

from ai_agent_template.developer_kit.claims_gateway import (
    ClaimsInternalError,
    FraudContextSeedLoader,
    FraudContextService,
)
from ai_agent_template.developer_kit.plugins.synthetic import default_synthetic_plugins
from ai_agent_template.developer_kit.sdk.claim_agent_sdk import TemplateBundle, ToolRegistry, WorkflowRunner
from mvp.app.db.sqlite import SQLiteRepository
from mvp.app.plugins.remote_fraud_signal_checker_v2 import RemoteFraudSignalCheckerV2Plugin
from test_support.fraud_check_server import FraudCheckTestServer, unused_local_url


WORKSPACE = Path(__file__).resolve().parents[1]
FRAUD_WORKSPACE = WORKSPACE.parent / "Fraud_Check"
FRAUD_PYTHON = FRAUD_WORKSPACE / ".venv" / "Scripts" / "python.exe"
GENERATED_DIR = WORKSPACE / "data_generator" / "generated"
MVP_ROOT = WORKSPACE / "mvp"
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"
INTERNAL_KEY = "cross-workspace-internal-secret"
FRAUD_KEY = "cross-workspace-fraud-secret"
FORBIDDEN_RUNTIME_KEYS = {
    "expected_decision",
    "expected_payable_amount",
    "fraud_scenario",
    "fraud_labels",
    "labels_eval",
    "labels_dev",
}


@unittest.skipUnless(
    FRAUD_PYTHON.exists() and (FRAUD_WORKSPACE / "app" / "main.py").exists(),
    "Fraud_Check workspace or its virtual environment is unavailable",
)
class FraudCheckCrossWorkspaceE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.temp_dir = tempfile.TemporaryDirectory()
        cls.runtime_root = Path(cls.temp_dir.name)
        cls.repository = SQLiteRepository(
            db_path=cls.runtime_root / "claims.sqlite3",
            schema_path=MVP_ROOT / "app" / "db" / "schema.sql",
            migrations_dir=MVP_ROOT / "app" / "db" / "migrations",
        )
        FraudContextSeedLoader(cls.repository).load_generated(GENERATED_DIR, split="eval")
        cls.context_service = FraudContextService(
            repository=cls.repository,
            documents_root=GENERATED_DIR,
            uploaded_documents_root=cls.runtime_root / "uploads",
            max_document_bytes=10_000_000,
        )
        cls.claims_server = _ClaimsEvidenceServer(cls.context_service, api_key=INTERNAL_KEY)
        cls.claims_server.start()
        cls.fraud_port = _free_port()
        cls.fraud_url = f"http://127.0.0.1:{cls.fraud_port}"
        cls.fraud_log_path = cls.runtime_root / "fraud-check.log"
        cls.fraud_log = cls.fraud_log_path.open("w", encoding="utf-8")
        env = os.environ.copy()
        env.update(
            {
                "FRAUD_CHECK_API_KEY": FRAUD_KEY,
                "CLAIMS_INTERNAL_API_KEY": INTERNAL_KEY,
                "CLAIMS_MVP_BASE_URL": cls.claims_server.url,
                "REQUEST_TIMEOUT_SECONDS": "3",
                "MAX_DOCUMENT_BYTES": "10000000",
                "FRAUD_THRESHOLD": "50",
            }
        )
        cls.fraud_process = subprocess.Popen(
            [
                str(FRAUD_PYTHON),
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "127.0.0.1",
                "--port",
                str(cls.fraud_port),
            ],
            cwd=FRAUD_WORKSPACE,
            env=env,
            stdout=cls.fraud_log,
            stderr=subprocess.STDOUT,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        _wait_for_health(f"{cls.fraud_url}/health", cls.fraud_process)
        cls.claims = _read_jsonl_by_id(GENERATED_DIR / "claims_eval.jsonl")
        cls.template = TemplateBundle.load(TEMPLATE_ROOT)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.fraud_process.terminate()
        try:
            cls.fraud_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            cls.fraud_process.kill()
            cls.fraud_process.wait(timeout=5)
        cls.fraud_log.close()
        cls.claims_server.stop()
        cls.temp_dir.cleanup()

    def test_01_clean_claim_passes_fraud_and_continues_claim_review(self) -> None:
        envelope = self._run_real_fraud("CLM-EVAL-900001")
        self.assertEqual("success", envelope["status"])
        self.assertFalse(envelope["result"]["fraud_suspected"])
        self.assertEqual("continue_claim_review", envelope["result"]["routing"])

        runner = self._workflow_runner(self._real_plugin())
        with self._plugin_environment():
            runner.run(self.claims["CLM-EVAL-900001"])
        tools = [item["tool_name"] for item in runner.last_context["tool_trace"]]
        fraud_index = tools.index("fraud_signal_checker")
        self.assertIn("document_checker", tools[fraud_index + 1 :])
        self.assertIn("payable_calculator", tools[fraud_index + 1 :])

    def test_02_exact_and_altered_duplicate_documents_are_detected(self) -> None:
        exact = self._run_real_fraud("CLM-EVAL-900002")["result"]
        altered = self._run_real_fraud("CLM-EVAL-900004")["result"]
        self.assertIn("DUPLICATE_RECEIPT_SUSPECTED", exact["fraud_reason_codes"])
        self.assertTrue(
            {"ALTERED_DUPLICATE_RECEIPT_SUSPECTED", "DUPLICATE_RECEIPT_SUSPECTED"}
            & set(altered["fraud_reason_codes"])
        )
        self.assertTrue(exact["evidence"])
        self.assertTrue(altered["evidence"])

    def test_03_amount_date_and_provider_mismatches_include_evidence(self) -> None:
        scenarios = {
            "CLM-EVAL-900005": ("DOCUMENT_AMOUNT_MISMATCH", "claimed_amount"),
            "CLM-EVAL-900006": ("DOCUMENT_DATE_MISMATCH", "treatment_start_date"),
            "CLM-EVAL-900007": ("DOCUMENT_PROVIDER_MISMATCH", "provider_id"),
        }
        for claim_id, (reason_code, field) in scenarios.items():
            with self.subTest(claim_id=claim_id):
                result = self._run_real_fraud(claim_id)["result"]
                self.assertIn(reason_code, result["fraud_reason_codes"])
                self.assertTrue(any(item.get("field") == field for item in result["evidence"]))

    def test_04_behavior_and_provider_volume_boundaries_are_exact(self) -> None:
        repeat_2 = self._run_real_fraud("CLM-EVAL-900009")["result"]
        repeat_3 = self._run_real_fraud("CLM-EVAL-900010")["result"]
        provider_49 = self._run_real_fraud("CLM-EVAL-900011")["result"]
        provider_50 = self._run_real_fraud("CLM-EVAL-900012")["result"]
        self.assertNotIn("SAME_INSURED_PROVIDER_REPEAT_SUSPECTED", repeat_2["fraud_reason_codes"])
        self.assertIn("SAME_INSURED_PROVIDER_REPEAT_SUSPECTED", repeat_3["fraud_reason_codes"])
        self.assertNotIn("PROVIDER_PATTERN_ANOMALY_SUSPECTED", provider_49["fraud_reason_codes"])
        self.assertIn("PROVIDER_PATTERN_ANOMALY_SUSPECTED", provider_50["fraud_reason_codes"])

    def test_05_fraud_suspicion_forces_final_human_review(self) -> None:
        with self._plugin_environment():
            output = self._workflow_runner(self._real_plugin()).run(self.claims["CLM-EVAL-900002"])
        self.assertTrue(output["fraud_suspected"])
        self.assertTrue(output["requires_human_review"])
        self.assertEqual("human_review", output["recommended_decision"])

    def test_06_down_timeout_and_invalid_response_fail_closed(self) -> None:
        claim = self.claims["CLM-EVAL-900016"]
        down = RemoteFraudSignalCheckerV2Plugin(service_url=unused_local_url(), timeout_ms=100)
        down_output = self._workflow_runner(down).run(claim)
        self._assert_human_review(down_output)

        with FraudCheckTestServer(_valid_nonfraud_response, delay_seconds=0.2) as server:
            timeout = RemoteFraudSignalCheckerV2Plugin(service_url=server.url, timeout_ms=50)
            timeout_output = self._workflow_runner(timeout).run(claim)
        self._assert_human_review(timeout_output)

        with FraudCheckTestServer(lambda request, headers: (200, "{invalid-json")) as server:
            invalid = RemoteFraudSignalCheckerV2Plugin(service_url=server.url, timeout_ms=500)
            invalid_output = self._workflow_runner(invalid).run(claim)
        self._assert_human_review(invalid_output)

    def test_07_document_api_auth_and_missing_document_are_safe(self) -> None:
        context_url = f"{self.claims_server.url}/internal/v1/fraud-context/claims/CLM-EVAL-900001"
        with self.assertRaises(HTTPError) as unauthorized:
            urlopen(context_url, timeout=2)
        self.assertEqual(401, unauthorized.exception.code)
        unauthorized.exception.close()
        with self.assertRaises(HTTPError) as forbidden:
            urlopen(Request(context_url, headers={"Authorization": "Bearer wrong"}), timeout=2)
        self.assertEqual(403, forbidden.exception.code)
        forbidden.exception.close()

        missing = self._run_real_fraud("CLM-EVAL-900020")["result"]
        self.assertFalse(missing["fraud_suspected"])
        self.assertTrue(missing["requires_human_review"])
        self.assertEqual("human_review", missing["routing"])
        self.assertTrue(any(item.get("code") == "DOCUMENT_UNAVAILABLE" for item in missing["analysis_warnings"]))

    def test_08_evaluation_labels_are_absent_from_requests_database_and_events(self) -> None:
        claim = self.claims["CLM-EVAL-900005"]
        plugin = self._real_plugin()
        with self._plugin_environment():
            request_body = plugin._build_request(
                _fraud_payload(claim),
                {"claim_payload": claim},
                "REQ-ACP-LABEL-ISOLATION-001",
            )
        keys = _all_keys(request_body)
        self.assertFalse(keys & FORBIDDEN_RUNTIME_KEYS)
        self.assertEqual({}, request_body["upstream_signals"])

        with closing(sqlite3.connect(self.repository.db_path)) as connection:
            dump = "\n".join(connection.iterdump()).lower()
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
        self.assertFalse(any("label" in table.lower() for table in tables))
        for forbidden in FORBIDDEN_RUNTIME_KEYS:
            self.assertNotIn(forbidden.lower(), dump)
        self.assertTrue(all(set(event) <= {"method", "path", "status"} for event in self.claims_server.events))

    def test_09_general_logs_do_not_contain_document_body_or_direct_insured_id(self) -> None:
        self._run_real_fraud("CLM-EVAL-900001")
        time.sleep(0.1)
        log_text = self.fraud_log_path.read_text(encoding="utf-8", errors="replace")
        self.assertNotIn("INS-SYN-EVAL-900001", log_text)
        self.assertNotIn("%PDF-", log_text)
        self.assertNotIn("SYNTHETIC TEST DOCUMENT", log_text)
        self.assertNotIn(FRAUD_KEY, log_text)
        self.assertNotIn(INTERNAL_KEY, log_text)

    def _run_real_fraud(self, claim_id: str) -> dict[str, Any]:
        claim = self.claims[claim_id]
        with self._plugin_environment():
            return self._real_plugin().run(_fraud_payload(claim), {"claim_payload": claim})

    def _real_plugin(self) -> RemoteFraudSignalCheckerV2Plugin:
        return RemoteFraudSignalCheckerV2Plugin(
            service_url=self.fraud_url,
            timeout_ms=10_000,
            claims_internal_base_url=self.claims_server.url,
            analysis_mode="raw_evidence",
        )

    def _plugin_environment(self):
        return patch.dict(
            os.environ,
            {
                "FRAUD_CHECK_API_KEY": FRAUD_KEY,
                "CLAIMS_INTERNAL_API_KEY": INTERNAL_KEY,
            },
        )

    def _workflow_runner(self, fraud_plugin: Any) -> WorkflowRunner:
        registry = ToolRegistry(self.template)
        for plugin in default_synthetic_plugins():
            if plugin.name != "fraud_signal_checker":
                registry.register(plugin)
        registry.register(fraud_plugin)
        registry.validate_registered_plugins()
        return WorkflowRunner(self.template, tool_registry=registry)

    def _assert_human_review(self, output: dict[str, Any]) -> None:
        self.assertEqual("human_review", output["recommended_decision"])
        self.assertTrue(output["requires_human_review"])
        self.assertIn("TOOL_FAILURE", output["reason_codes"])


class _ClaimsEvidenceServer:
    def __init__(self, service: FraudContextService, *, api_key: str):
        self.service = service
        self.api_key = api_key
        self.events: list[dict[str, Any]] = []
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        if self._server is None:
            raise RuntimeError("Claims evidence server is not running")
        host, port = self._server.server_address
        return f"http://{host}:{port}"

    def start(self) -> None:
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self) -> None:  # noqa: N802
                status = 200
                try:
                    if self.headers.get("Authorization") != f"Bearer {outer.api_key}":
                        status = 401 if not self.headers.get("Authorization") else 403
                        self._json(status, {"error": {"code": "UNAUTHORIZED" if status == 401 else "FORBIDDEN"}})
                        return
                    path = urlparse(self.path).path
                    if path.startswith("/internal/v1/fraud-context/claims/"):
                        claim_id = unquote(path.rsplit("/", 1)[1])
                        self._json(200, outer.service.get_fraud_context(claim_id))
                    elif path.startswith("/internal/v1/claims/") and path.endswith("/documents"):
                        claim_id = unquote(path.split("/internal/v1/claims/", 1)[1].rsplit("/documents", 1)[0])
                        self._json(200, {"schema_version": "1.0.0", "claim_id": claim_id, "documents": outer.service.list_documents(claim_id)})
                    elif path.startswith("/internal/v1/documents/") and path.endswith("/content"):
                        document_id = unquote(path.split("/internal/v1/documents/", 1)[1].rsplit("/content", 1)[0])
                        document = outer.service.get_document_content(document_id)
                        self.send_response(200)
                        self.send_header("Content-Type", document.mime_type)
                        self.send_header("Content-Length", str(document.file_size))
                        self.send_header("X-Content-Hash", document.content_hash)
                        self.end_headers()
                        self.wfile.write(document.content)
                    else:
                        status = 404
                        self._json(404, {"error": {"code": "NOT_FOUND"}})
                except ClaimsInternalError as exc:
                    status = exc.status_code
                    self._json(status, {"error": {"code": exc.code, "message": exc.message}})
                finally:
                    outer.events.append({"method": "GET", "path": urlparse(self.path).path, "status": status})

            def _json(self, status: int, value: dict[str, Any]) -> None:
                body = json.dumps(value).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=3)


def _fraud_payload(claim: dict[str, Any]) -> dict[str, Any]:
    return {
        "insured_profile": claim["insured_profile"],
        "claim": claim["claim"],
        "claim_history": claim["claim_history"],
        "signals": claim["signals"],
    }


def _valid_nonfraud_response(request: dict[str, Any], headers: dict[str, str]):
    return 200, {
        "schema_version": "2.0.0",
        "request_id": request.get("request_id"),
        "claim_id": request.get("claim_id"),
        "status": "completed",
        "fraud_suspected": False,
        "fraud_reason_codes": [],
        "risk_score": 0,
        "routing": "continue_claim_review",
        "requires_human_review": False,
        "engine_version": "test-2.0.0",
        "workflow_version": "test-2.0.0",
    }


def _read_jsonl_by_id(path: Path) -> dict[str, dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    return {row["claim_id"]: row for row in rows}


def _all_keys(value: Any) -> set[str]:
    if isinstance(value, dict):
        return set(value) | {key for nested in value.values() for key in _all_keys(nested)}
    if isinstance(value, list):
        return {key for nested in value for key in _all_keys(nested)}
    return set()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_health(url: str, process: subprocess.Popen, timeout: float = 10) -> None:
    deadline = time.monotonic() + timeout
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"Fraud_Check exited during startup with code {process.returncode}")
        try:
            with urlopen(url, timeout=0.5) as response:
                if response.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - startup timing
            last_error = exc
            time.sleep(0.1)
    raise RuntimeError(f"Fraud_Check did not become healthy: {last_error}")


if __name__ == "__main__":
    unittest.main()
