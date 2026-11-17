import importlib
import json
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

SUMMARY_PATH = ROOT / "public" / "data" / "summary.json"


class WorkerAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        js_module = types.ModuleType("js")

        def from_entries(entries):
            return dict(entries)

        js_module.Object = types.SimpleNamespace(fromEntries=from_entries)

        pyodide_module = types.ModuleType("pyodide")
        pyodide_module.__path__ = []
        ffi_module = types.ModuleType("pyodide.ffi")
        ffi_module.run_sync = lambda value: value

        def to_js(value, dict_converter):
            if isinstance(value, dict):
                return dict_converter(value.items())
            return value

        ffi_module.to_js = to_js

        workers_module = types.ModuleType("workers")
        workers_module.__path__ = []
        wsgi_module = types.ModuleType("workers.wsgi")
        wsgi_module.entrypoint = lambda app: app
        workers_module.wsgi = wsgi_module

        cls._previous_worker = sys.modules.pop("worker", None)
        with patch.dict(
            sys.modules,
            {
                "js": js_module,
                "pyodide": pyodide_module,
                "pyodide.ffi": ffi_module,
                "workers": workers_module,
                "workers.wsgi": wsgi_module,
            },
        ):
            cls.worker = importlib.import_module("worker")

    @classmethod
    def tearDownClass(cls):
        sys.modules.pop("worker", None)
        if cls._previous_worker is not None:
            sys.modules["worker"] = cls._previous_worker

    def test_ai_response_is_used_without_pyodide_conversion(self):
        model_response = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "consultar_resumo",
                            "arguments": '{"ano":2022,"metrica":"acidentes"}',
                        },
                    }],
                },
            }],
        }

        def run_ai(model, options):
            self.assertEqual(model, self.worker.MODEL_ID)
            self.assertIn("messages", options)
            return model_response

        ai_binding = types.SimpleNamespace(run=run_ai)
        rate_limiter = types.SimpleNamespace(
            limit=lambda options: types.SimpleNamespace(success=bool(options))
        )
        env = types.SimpleNamespace(
            ANALYST_AI_ENABLED="true",
            AI=ai_binding,
            ANALYST_RATE_LIMITER=rate_limiter,
        )
        summaries = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

        with patch.object(self.worker, "load_summaries", return_value=summaries):
            response = self.worker.app.test_client().post(
                "/api/analista/perguntar",
                json={"pergunta": "Quantos acidentes houve em 2022?"},
                environ_overrides={"workers.env": env},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "respondida")
        self.assertEqual(payload["resultado"], {"acidentes": 25532})


if __name__ == "__main__":
    unittest.main()
