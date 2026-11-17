import json
import unittest
from pathlib import Path

from src.analyst_queries import SOURCE, execute_query


ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = ROOT / "tests" / "fixtures" / "analyst_questions.json"
SUMMARY_PATH = ROOT / "public" / "data" / "summary.json"


class AnalystReferenceCasesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        cls.summaries = json.loads(SUMMARY_PATH.read_text(encoding="utf-8"))

    def test_reference_case_ids_are_unique(self):
        case_ids = [case["id"] for case in self.fixture["cases"]]

        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_supported_questions_match_expected_queries_and_results(self):
        supported_cases = [
            case for case in self.fixture["cases"]
            if case["expected"]["supported"]
        ]
        self.assertGreaterEqual(len(supported_cases), 5)

        for case in supported_cases:
            with self.subTest(case=case["id"]):
                expected = case["expected"]
                result = execute_query(
                    self.summaries,
                    {
                        "operacao": expected["operation"],
                        **expected["parameters"],
                    },
                )

                self.assertEqual(result["operacao"], expected["operation"])
                self.assertEqual(result["resultado"], expected["result"])
                self.assertEqual(result["fonte"], SOURCE)

    def test_out_of_scope_questions_have_explicit_abstention_reasons(self):
        unsupported_cases = [
            case for case in self.fixture["cases"]
            if not case["expected"]["supported"]
        ]
        self.assertGreaterEqual(len(unsupported_cases), 2)

        for case in unsupported_cases:
            with self.subTest(case=case["id"]):
                expected = case["expected"]

                self.assertEqual(expected.get("operation"), "recusar_pergunta")
                self.assertEqual(
                    expected.get("parameters", {}).get("motivo"),
                    expected.get("reason"),
                )
                self.assertTrue(expected.get("reason"))


if __name__ == "__main__":
    unittest.main()
