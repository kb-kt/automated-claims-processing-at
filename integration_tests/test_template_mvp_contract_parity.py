from __future__ import annotations

import unittest
import json
import importlib.util
import tempfile
from dataclasses import replace
from pathlib import Path

from ai_agent_template.developer_kit.sdk.claim_agent_sdk import (
    PluginLoader,
    TemplateBundle,
    TemplateContractValidator,
)


WORKSPACE = Path(__file__).resolve().parents[1]
TEMPLATE_ROOT = WORKSPACE / "ai_agent_template"
STARTER_CONFIG = TEMPLATE_ROOT / "developer_kit" / "starter_kit" / "config"
MVP_CONFIG = WORKSPACE / "mvp" / "config"


class TemplateMvpContractParityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.template = TemplateBundle.load(TEMPLATE_ROOT)
        TemplateContractValidator(cls.template).validate()

    def test_plugin_profiles_expose_identical_tool_contract_sets(self) -> None:
        expected = set(self.template.tool_contracts())
        for file_name in ("plugins.yaml", "plugins.remote.yaml", "plugins.remote.v2.yaml"):
            with self.subTest(profile=file_name):
                starter = {
                    plugin.name
                    for plugin in PluginLoader(self.template).load_plugins(STARTER_CONFIG / file_name)
                }
                mvp = {
                    plugin.name
                    for plugin in PluginLoader(self.template).load_plugins(MVP_CONFIG / file_name)
                }
                self.assertEqual(starter, expected)
                self.assertEqual(mvp, expected)
                self.assertEqual(starter, mvp)

    def test_specialist_profile_names_match(self) -> None:
        starter_text = (STARTER_CONFIG / "specialist_plugins.synthetic_insurer.yaml").read_text(
            encoding="utf-8"
        )
        mvp_text = (MVP_CONFIG / "specialist_plugins.synthetic_insurer.yaml").read_text(
            encoding="utf-8"
        )
        starter_names = _top_level_entries(starter_text, "specialist_agents")
        mvp_names = _top_level_entries(mvp_text, "specialist_agents")
        self.assertTrue(starter_names)
        self.assertEqual(starter_names, mvp_names)

    def test_model_configs_keep_required_provider_roles(self) -> None:
        for path in (STARTER_CONFIG / "model_config.yaml", MVP_CONFIG / "model_config.yaml"):
            with self.subTest(config=str(path)):
                text = path.read_text(encoding="utf-8")
                self.assertIn("general_llm:", text)
                self.assertIn("role: orchestrator_reasoning", text)
                self.assertIn("document_vlm:", text)
                self.assertIn("role: document_understanding", text)

    def test_review_api_envelopes_share_canonical_dto_fields(self) -> None:
        from ai_agent_template.developer_kit.starter_kit.app.api.reviews import (
            _review_response as starter_response,
        )
        from mvp.app.api.reviews import _review_response as mvp_response

        output = json.loads(
            (TEMPLATE_ROOT / "examples" / "reviewer_assistant_output.example.json").read_text(
                encoding="utf-8"
            )
        )
        starter = starter_response(output)
        mvp = mvp_response({"claim_id": output["claim_id"], "output": output})
        required = {"claim_id", "review_status", "status", "output", "agent_output", "errors"}
        self.assertTrue(required <= set(starter))
        self.assertTrue(required <= set(mvp))
        self.assertEqual(starter["output"], mvp["output"])

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_fastapi_openapi_surfaces_satisfy_template_manifest(self) -> None:
        from ai_agent_template.developer_kit.starter_kit.app.main import create_app as create_starter
        from mvp.app.main import create_app as create_mvp

        contract = json.loads(
            (TEMPLATE_ROOT / "schemas" / "api_surface.contract.json").read_text(encoding="utf-8")
        )
        required = {
            (item["method"].lower(), item["path"])
            for item in contract["required_operations"]
        }
        for name, app in (("starter", create_starter()), ("mvp", create_mvp())):
            openapi = app.openapi()
            actual = {
                (method.lower(), path)
                for path, operations in openapi["paths"].items()
                for method in operations
                if method.lower() in {"get", "post", "put", "patch", "delete"}
            }
            with self.subTest(application=name):
                self.assertTrue(required <= actual, sorted(required - actual))

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_fastapi_rbac_middleware_enforces_authentication_and_roles(self) -> None:
        from fastapi.testclient import TestClient
        from ai_agent_template.developer_kit.starter_kit.app.core.settings import (
            Settings as StarterSettings,
        )
        from ai_agent_template.developer_kit.starter_kit.app.main import create_app as create_starter
        from mvp.app.core.settings import Settings as MvpSettings
        from mvp.app.main import create_app as create_mvp

        with tempfile.TemporaryDirectory() as temp_dir:
            starter_settings = replace(
                StarterSettings.load(),
                auth_enabled=True,
                customer_api_key="customer-key",
                reviewer_api_key="reviewer-key",
                admin_api_key="admin-key",
            )
            mvp_settings = replace(
                MvpSettings.load(),
                sqlite_path=Path(temp_dir) / "mvp.sqlite3",
                reports_dir=Path(temp_dir) / "reports",
                auth_enabled=True,
                customer_api_key="customer-key",
                reviewer_api_key="reviewer-key",
                admin_api_key="admin-key",
            )
            for name, app in (
                ("starter", create_starter(settings=starter_settings)),
                ("mvp", create_mvp(settings=mvp_settings)),
            ):
                client = TestClient(app)
                with self.subTest(application=name, case="missing-token"):
                    self.assertEqual(client.get("/reviews/queue").status_code, 401)
                with self.subTest(application=name, case="wrong-role"):
                    self.assertEqual(
                        client.get(
                            "/reviews/queue",
                            headers={"Authorization": "Bearer customer-key"},
                        ).status_code,
                        403,
                    )
                with self.subTest(application=name, case="reviewer-role"):
                    self.assertEqual(
                        client.get(
                            "/reviews/queue",
                            headers={"Authorization": "Bearer reviewer-key"},
                        ).status_code,
                        200,
                    )

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_fastapi_error_envelopes_are_schema_valid_and_equal(self) -> None:
        from fastapi.testclient import TestClient
        from jsonschema import Draft202012Validator
        from ai_agent_template.developer_kit.starter_kit.app.core.settings import (
            Settings as StarterSettings,
        )
        from ai_agent_template.developer_kit.starter_kit.app.main import create_app as create_starter
        from mvp.app.core.settings import Settings as MvpSettings
        from mvp.app.main import create_app as create_mvp

        schema = json.loads(
            (TEMPLATE_ROOT / "schemas" / "api_error.schema.json").read_text(encoding="utf-8")
        )
        validator = Draft202012Validator(schema)
        with tempfile.TemporaryDirectory() as temp_dir:
            starter_settings = replace(
                StarterSettings.load(),
                sqlite_path=Path(temp_dir) / "starter.sqlite3",
                reports_dir=Path(temp_dir) / "starter-reports",
            )
            mvp_settings = replace(
                MvpSettings.load(),
                sqlite_path=Path(temp_dir) / "mvp.sqlite3",
                reports_dir=Path(temp_dir) / "mvp-reports",
            )
            for name, app in (
                ("starter", create_starter(settings=starter_settings)),
                ("mvp", create_mvp(settings=mvp_settings)),
            ):
                client = TestClient(app, raise_server_exceptions=False)
                with self.subTest(application=name, case="validation"):
                    response = client.post("/claims", json={})
                    self.assertEqual(400, response.status_code)
                    validator.validate(response.json())
                    self.assertEqual("VALIDATION_ERROR", response.json()["error"]["code"])
                    self.assertEqual(
                        response.headers["X-Request-ID"],
                        response.json()["error"]["request_id"],
                    )
                with self.subTest(application=name, case="not-found"):
                    response = client.get("/reviews/CLAIM-DOES-NOT-EXIST")
                    self.assertEqual(404, response.status_code)
                    validator.validate(response.json())
                    self.assertEqual("NOT_FOUND", response.json()["error"]["code"])

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_product_catalog_api_is_equal_and_policy_scoped(self) -> None:
        from fastapi.testclient import TestClient
        from ai_agent_template.developer_kit.starter_kit.app.core.settings import (
            Settings as StarterSettings,
        )
        from ai_agent_template.developer_kit.starter_kit.app.main import create_app as create_starter
        from mvp.app.core.settings import Settings as MvpSettings
        from mvp.app.main import create_app as create_mvp

        with tempfile.TemporaryDirectory() as temp_dir:
            apps = (
                create_starter(
                    settings=replace(
                        StarterSettings.load(),
                        sqlite_path=Path(temp_dir) / "starter-products.sqlite3",
                    )
                ),
                create_mvp(
                    settings=replace(
                        MvpSettings.load(),
                        sqlite_path=Path(temp_dir) / "mvp-products.sqlite3",
                    )
                ),
            )
            responses = []
            for app in apps:
                client = TestClient(app)
                catalog = client.get("/products")
                policies = client.get("/products/SYN-MED-001/policies")
                self.assertEqual(200, catalog.status_code)
                self.assertEqual(200, policies.status_code)
                self.assertEqual(13, len(catalog.json()["products"]))
                self.assertTrue(
                    all(
                        item["product_id"] == "SYN-MED-001"
                        for item in policies.json()["policies"]
                    )
                )
                responses.append((catalog.json(), policies.json()))
            self.assertEqual(responses[0], responses[1])

    @unittest.skipUnless(importlib.util.find_spec("fastapi"), "FastAPI is not installed")
    def test_unexpected_api_error_is_redacted_and_correlated(self) -> None:
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from jsonschema import Draft202012Validator
        from ai_agent_template.developer_kit.claims_gateway.fastapi_errors import (
            install_api_error_handlers,
        )

        app = FastAPI()
        install_api_error_handlers(app, logger_name="test.api.errors")

        @app.get("/boom")
        def boom():
            raise RuntimeError("secret filesystem path C:/private/data")

        response = TestClient(app, raise_server_exceptions=False).get("/boom")
        body = response.json()
        schema = json.loads(
            (TEMPLATE_ROOT / "schemas" / "api_error.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator(schema).validate(body)
        self.assertEqual(500, response.status_code)
        self.assertEqual("INTERNAL_ERROR", body["error"]["code"])
        self.assertNotIn("private", json.dumps(body).lower())


def _top_level_entries(text: str, root_name: str) -> set[str]:
    entries: set[str] = set()
    in_plugins = False
    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0 and stripped == f"{root_name}:":
            in_plugins = True
            continue
        if in_plugins and indent == 2 and stripped.endswith(":"):
            entries.add(stripped[:-1])
    return entries


if __name__ == "__main__":
    unittest.main()
