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
    TOOLS,
    analyze_question,
    build_inference_options,
    is_ai_enabled,
    validate_question,
)
from analyst_queries import SOURCE


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "analyst_questions.json"
SUMMARY_PATH = ROOT / "public" / "data" / "summary.json"


class AnalystAITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.summaries = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    def test_inference_request_uses_fixed_model_and_bounded_output(self):
        options = build_inference_options("Quantos acidentes houve em 2022?")

        self.assertEqual(MODEL_ID, "@cf/zai-org/glm-4.7-flash")
        self.assertEqual(options["max_completion_tokens"], 160)
        self.assertEqual(options["temperature"], 0)
        self.assertFalse(options["store"])
        self.assertEqual(options["tool_choice"], "auto")
        self.assertFalse(options["parallel_tool_calls"])
        self.assertFalse(options["chat_template_kwargs"]["enable_thinking"])
        self.assertTrue(all(tool["type"] == "function" for tool in TOOLS))
        self.assertTrue(all("name" in tool["function"] for tool in TOOLS))

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
                result = analyze_question(
                    case["question"],
                    self.summaries,
                    lambda _options: model_response,
                )

                if expected["supported"]:
                    self.assertEqual(result["status"], "respondida")
                    self.assertEqual(result["resultado"], expected["result"])
                    self.assertEqual(result["fonte"], SOURCE)
                    self.assertTrue(result["resposta"])
                else:
                    self.assertEqual(result["status"], "recusada")
                    self.assertEqual(result["motivo"], expected["reason"])
                    self.assertIsNone(result["resultado"])

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

    def test_rejects_multiple_or_malformed_tool_calls(self):
        with self.assertRaises(AnalystAIError):
            analyze_question(
                "Pergunta",
                self.summaries,
                lambda _options: {
                    "choices": [{"message": {"tool_calls": [{}, {}]}}],
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
