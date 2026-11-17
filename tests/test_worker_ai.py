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
RECORDS_DIR = ROOT / "public" / "data" / "records"


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
                    "tool_calls": [
                        {
                            "function": {
                                "name": "consultar_distribuicao",
                                "arguments": json.dumps({
                                    "ano": 2023,
                                    "dimensao": "uf",
                                    "metrica": "acidentes",
                                    "por_pagina": 1,
                                }),
                            },
                        },
                        {
                            "function": {
                                "name": "listar_causas",
                                "arguments": json.dumps({"ano": 2023, "limite": 1}),
                            },
                        },
                    ],
                },
            }],
        }
        ai_calls = []

        def run_ai(model, options):
            self.assertEqual(model, self.worker.MODEL_ID)
            self.assertIn("messages", options)
            ai_calls.append(options)
            if "tools" in options:
                return model_response
            context = json.loads(options["messages"][1]["content"])
            self.assertEqual(len(context["consultas"]), 2)
            self.assertEqual(context["consultas"][0]["resultado"][0]["valor"], "MG")
            self.assertEqual(context["consultas"][0]["resultado"][0]["acidentes"], 9007)
            self.assertEqual(
                context["consultas"][1]["resultado"][0]["causa"],
                "Reação tardia ou ineficiente do condutor",
            )
            self.assertEqual(context["consultas"][1]["resultado"][0]["acidentes"], 9855)
            return {
                "choices": [{
                    "message": {
                        "content": (
                            "Em 2023, MG teve 9.007 acidentes. A causa registrada mais "
                            "frequente foi Reação tardia ou ineficiente do condutor, "
                            "com 9.855 acidentes."
                        ),
                    },
                }],
            }

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

        def load_distribution(year, state, dimension):
            parts = []
            if year is not None:
                parts.append(f"year_{year}")
            if state is not None:
                parts.append(f"uf_{state}")
            key = "_".join(parts) or "all"
            path = ROOT / "public" / "data" / "analytics" / f"{key}.json"
            return json.loads(path.read_text(encoding="utf-8"))["dimensoes"][dimension]

        with (
            patch.object(self.worker, "load_summaries", return_value=summaries),
            patch.object(
                self.worker,
                "load_analytics_dimension",
                side_effect=load_distribution,
            ),
        ):
            response = self.worker.app.test_client().post(
                "/api/analista/perguntar",
                json={
                    "pergunta": (
                        "Qual estado teve mais acidentes em 2023 e qual a maior causa "
                        "nesse período?"
                    ),
                },
                environ_overrides={"workers.env": env},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "respondida")
        self.assertEqual(len(payload["consultas"]), 2)
        self.assertEqual(payload["consulta"][0]["operacao"], "consultar_distribuicao")
        self.assertEqual(payload["consulta"][1]["operacao"], "listar_causas")
        self.assertEqual(payload["resultado"][0][0]["valor"], "MG")
        self.assertEqual(payload["resultado"][1][0]["causa"], "Reação tardia ou ineficiente do condutor")
        self.assertIn("MG teve 9.007 acidentes", payload["resposta"])
        self.assertIn("9.855 acidentes", payload["resposta"])
        self.assertNotIn("Fonte:", payload["resposta"])
        self.assertIn("Dados PRF pré-processados", payload["fonte"])
        self.assertEqual(len(ai_calls), 2)

    def test_ai_can_analyze_filtered_record_details(self):
        plan = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "analisar_registros",
                            "arguments": json.dumps({
                                "ano": 2023,
                                "uf": "MG",
                                "filtros": {
                                    "br": "116",
                                    "condicao_metereologica": "Chuva",
                                },
                                "agrupar_por": "causa_acidente",
                                "metrica": "acidentes",
                                "limite": 1,
                            }),
                        },
                    }],
                },
            }],
        }
        ai_calls = []

        def run_ai(model, options):
            self.assertEqual(model, self.worker.MODEL_ID)
            ai_calls.append(options)
            if "tools" in options:
                return plan
            context = json.loads(options["messages"][1]["content"])
            consultation = context["consultas"][0]
            self.assertEqual(consultation["total_registros"], 85)
            self.assertEqual(consultation["resultado"][0]["acidentes"], 19)
            category = consultation["resultado"][0]["valor"]
            return {
                "choices": [{
                    "message": {
                        "content": (
                            f"Em 2023, foram encontrados 85 acidentes nesse recorte. "
                            f"A causa registrada mais frequente foi {category}, com 19 registros."
                        ),
                    },
                }],
            }

        env = types.SimpleNamespace(
            ANALYST_AI_ENABLED="true",
            AI=types.SimpleNamespace(run=run_ai),
            ANALYST_RATE_LIMITER=types.SimpleNamespace(
                limit=lambda options: types.SimpleNamespace(success=bool(options))
            ),
        )
        summaries = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))
        manifest = json.loads((RECORDS_DIR / "manifest.json").read_text(encoding="utf-8"))

        def load_chunk(path):
            return json.loads((RECORDS_DIR / path).read_text(encoding="utf-8"))

        with (
            patch.object(self.worker, "load_summaries", return_value=summaries),
            patch.object(self.worker, "load_record_manifest", return_value=manifest),
            patch.object(self.worker, "load_record_chunk", side_effect=load_chunk),
        ):
            response = self.worker.app.test_client().post(
                "/api/analista/perguntar",
                json={
                    "pergunta": (
                        "Qual causa teve mais acidentes com chuva na BR-116 "
                        "em MG em 2023?"
                    ),
                },
                environ_overrides={"workers.env": env},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["status"], "respondida")
        self.assertEqual(payload["consultas"][0]["operacao"], "analisar_registros")
        self.assertEqual(payload["consultas"][0]["total_registros"], 85)
        self.assertIn("causa registrada mais frequente", payload["resposta"])
        self.assertEqual(len(ai_calls), 2)


if __name__ == "__main__":
    unittest.main()
