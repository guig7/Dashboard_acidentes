import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst_ai import (
    AnalystAIError,
    MODEL_ID,
    MAX_ANSWER_COMPLETION_TOKENS,
    MAX_PLAN_COMPLETION_TOKENS,
    MAX_TOOL_CALLS,
    TOOLS,
    analyze_question,
    build_answer_options,
    build_inference_options,
    is_ai_enabled,
    validate_question,
)
from analyst_queries import SOURCE


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "analyst_questions.json"
SUMMARY_PATH = ROOT / "public" / "data" / "summary.json"
ANALYTICS_DIR = ROOT / "public" / "data" / "analytics"


class AnalystAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.summaries = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    def test_inference_request_uses_fixed_model_and_bounded_output(self):
        options = build_inference_options("Quantos acidentes houve em 2022?")

        self.assertEqual(MODEL_ID, "@cf/zai-org/glm-4.7-flash")
        self.assertEqual(options["max_completion_tokens"], MAX_PLAN_COMPLETION_TOKENS)
        self.assertEqual(options["temperature"], 0)
        self.assertFalse(options["store"])
        self.assertEqual(options["tool_choice"], "auto")
        self.assertTrue(options["parallel_tool_calls"])
        self.assertFalse(options["chat_template_kwargs"]["enable_thinking"])
        self.assertTrue(all(tool["type"] == "function" for tool in TOOLS))
        self.assertTrue(all("name" in tool["function"] for tool in TOOLS))

    def test_answer_request_contains_only_question_and_structured_results(self):
        consultations = [{
            "operacao": "consultar_resumo",
            "filtros": {"ano": 2022, "uf": None},
            "resultado": {"acidentes": 25532},
        }]

        options = build_answer_options("Quantos acidentes houve em 2022?", consultations)
        context = json.loads(options["messages"][1]["content"])

        self.assertEqual(options["max_completion_tokens"], MAX_ANSWER_COMPLETION_TOKENS)
        self.assertEqual(options["temperature"], 0.2)
        self.assertNotIn("tools", options)
        self.assertEqual(context["pergunta"], "Quantos acidentes houve em 2022?")
        self.assertEqual(context["consultas"], consultations)
        self.assertIn("não invente valores", options["messages"][0]["content"])
        self.assertNotIn("fonte", context)
        self.assertIn("não cite a fonte", options["messages"][0]["content"])

    def test_reference_cases_flow_through_mocked_tool_calls(self):
        for case in self.fixture["cases"]:
            with self.subTest(case=case["id"]):
                expected = case["expected"]
                model_response = {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "type": "function",
                                "function": {
                                    "name": expected["operation"],
                                    "arguments": json.dumps(expected["parameters"]),
                                },
                            }],
                        },
                    }],
                }

                def infer(options):
                    if "tools" in options:
                        return model_response
                    return {
                        "choices": [{
                            "message": {"content": "Resposta baseada nos dados consultados."},
                        }],
                    }

                result = analyze_question(
                    case["question"],
                    self.summaries,
                    infer,
                    distribution_loader=self._load_distribution,
                )

                if expected["supported"]:
                    self.assertEqual(result["status"], "respondida")
                    self.assertEqual(result["resultado"], expected["result"])
                    self.assertEqual(result["fonte"], SOURCE)
                    self.assertTrue(result["resposta"])
                    self.assertEqual(result["resposta"], "Resposta baseada nos dados consultados.")
                    self.assertNotIn(SOURCE, result["resposta"])
                else:
                    self.assertEqual(result["status"], "recusada")
                    self.assertEqual(result["motivo"], expected["reason"])
                    self.assertIsNone(result["resultado"])

    def test_multi_part_question_runs_each_query_and_synthesizes_all_results(self):
        question = (
            "Qual estado teve mais acidentes em 2023 e qual a maior causa nesse período?"
        )
        plan = {
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
        final_answer = (
            "Em 2023, MG teve 3.536 acidentes. A causa registrada mais frequente foi "
            "Reação tardia ou ineficiente do condutor, com 3.930 acidentes."
        )
        inference_calls = []

        def infer(options):
            inference_calls.append(options)
            if "tools" in options:
                return plan
            context = json.loads(options["messages"][1]["content"])
            self.assertEqual(context["pergunta"], question)
            self.assertEqual(len(context["consultas"]), 2)
            self.assertEqual(context["consultas"][0]["resultado"][0]["valor"], "MG")
            self.assertEqual(context["consultas"][0]["resultado"][0]["acidentes"], 3536)
            self.assertEqual(
                context["consultas"][1]["resultado"][0]["causa"],
                "Reação tardia ou ineficiente do condutor",
            )
            self.assertEqual(context["consultas"][1]["resultado"][0]["acidentes"], 3930)
            return {"choices": [{"message": {"content": final_answer}}]}

        result = analyze_question(
            question,
            self.summaries,
            infer,
            distribution_loader=self._load_distribution,
        )

        self.assertEqual(len(inference_calls), 2)
        self.assertEqual(result["status"], "respondida")
        self.assertEqual(result["resposta"], final_answer)
        self.assertNotIn(SOURCE, result["resposta"])
        self.assertEqual(result["fonte"], SOURCE)
        self.assertEqual(len(result["consultas"]), 2)
        self.assertEqual(result["consulta"][0]["operacao"], "consultar_distribuicao")
        self.assertEqual(result["consulta"][1]["operacao"], "listar_causas")

    def test_rejects_empty_and_overlong_questions(self):
        with self.assertRaises(ValueError):
            validate_question("   ")
        with self.assertRaises(ValueError):
            validate_question("x" * 501)

    def test_analyst_is_available_only_with_flag_and_required_bindings(self):
        self.assertFalse(is_ai_enabled(SimpleNamespace()))
        self.assertFalse(
            is_ai_enabled(
                SimpleNamespace(
                    ANALYST_AI_ENABLED="true",
                    AI=object(),
                    ANALYST_RATE_LIMITER=None,
                )
            )
        )
        self.assertTrue(
            is_ai_enabled(
                SimpleNamespace(
                    ANALYST_AI_ENABLED="true",
                    AI=object(),
                    ANALYST_RATE_LIMITER=object(),
                )
            )
        )

    def test_rejects_oversized_or_malformed_tool_plans(self):
        with self.assertRaises(AnalystAIError):
            analyze_question(
                "Pergunta",
                self.summaries,
                lambda _options: {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "function": {
                                    "name": "consultar_resumo",
                                    "arguments": '{"ano":2022,"metrica":"acidentes"}',
                                },
                            }] * (MAX_TOOL_CALLS + 1),
                        },
                    }],
                },
            )
        with self.assertRaises(AnalystAIError):
            analyze_question(
                "Pergunta",
                self.summaries,
                lambda _options: {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "function": {
                                    "name": "consultar_resumo",
                                    "arguments": "{invalido",
                                },
                            }],
                        },
                    }],
                },
            )

    def test_refusal_tool_never_returns_model_generated_text(self):
        result = analyze_question(
            "Preveja os acidentes de amanhã",
            self.summaries,
            lambda _options: {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "function": {
                                "name": "recusar_pergunta",
                                "arguments": '{"motivo":"previsao_futura"}',
                            },
                        }],
                    },
                }],
            },
        )

        self.assertEqual(result["status"], "recusada")
        self.assertEqual(
            result["resposta"],
            "O painel contém registros históricos e não permite prever acidentes futuros.",
        )

    def test_weather_distribution_answer_is_historical_and_uses_prepared_values(self):
        response = {
            "choices": [{
                "message": {
                    "tool_calls": [{
                        "function": {
                            "name": "consultar_distribuicao",
                            "arguments": json.dumps({
                                "ano": 2023,
                                "dimensao": "condicao_metereologica",
                                "metrica": "acidentes",
                            }),
                        },
                    }],
                },
            }],
        }
        distributions = [
            {
                "valor": "Chuva",
                "acidentes": 12,
                "mortos": 2,
                "feridos": 5,
                "feridos_leves": 4,
                "feridos_graves": 1,
                "pessoas": 18,
                "ilesos": 3,
                "ignorados": 0,
                "veiculos": 14,
            },
        ]

        def infer(options):
            if "tools" in options:
                return response
            context = json.loads(options["messages"][1]["content"])
            weather_result = context["consultas"][0]["resultado"][0]
            self.assertEqual(weather_result["acidentes"], 12)
            self.assertEqual(weather_result["mortes"], 2)
            return {
                "choices": [{
                    "message": {
                        "content": (
                            "A condição mais frequente foi chuva, mas isso não demonstra "
                            "causalidade."
                        ),
                    },
                }],
            }

        result = analyze_question(
            "Quais condições meteorológicas aparecem mais?",
            self.summaries,
            infer,
            distribution_loader=lambda year, state, dimension: (
                distributions
                if (year, state, dimension) == (2023, None, "condicao_metereologica")
                else []
            ),
        )

        self.assertEqual(result["resultado"][0]["valor"], "Chuva")
        self.assertEqual(
            result["consultas"][0]["resultado"][0]["acidentes"],
            12,
        )
        self.assertIn("não demonstra causalidade", result["resposta"])

    @staticmethod
    def _load_distribution(year, state, dimension):
        parts = []
        if year is not None:
            parts.append(f"year_{year}")
        if state is not None:
            parts.append(f"uf_{state}")
        key = "_".join(parts) or "all"
        analytics = json.loads((ANALYTICS_DIR / f"{key}.json").read_text(encoding="utf-8"))
        return analytics["dimensoes"][dimension]

    def test_refusal_tool_rejects_model_generated_fields(self):
        with self.assertRaises(AnalystAIError):
            analyze_question(
                "Preveja os acidentes de amanhã",
                self.summaries,
                lambda _options: {
                    "choices": [{
                        "message": {
                            "tool_calls": [{
                                "function": {
                                    "name": "recusar_pergunta",
                                    "arguments": (
                                        '{"motivo":"previsao_futura",'
                                        '"texto":"resposta inventada"}'
                                    ),
                                },
                            }],
                        },
                    }],
                },
            )


if __name__ == "__main__":
    unittest.main()
