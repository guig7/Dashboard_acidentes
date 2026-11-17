import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analyst_queries import SOURCE, execute_query
from record_queries import query_records


FIXTURE_PATH = ROOT / "tests" / "fixtures" / "analyst_questions.json"
SUMMARY_PATH = ROOT / "public" / "data" / "summary.json"
RECORD_MANIFEST_PATH = ROOT / "public" / "data" / "records" / "manifest.json"
ANALYTICS_DIR = ROOT / "public" / "data" / "analytics"


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
                    distribution_loader=self._load_distribution,
                )

                self.assertEqual(result["operacao"], expected["operation"])
                self.assertEqual(result["resultado"], expected["result"])
                self.assertEqual(result["fonte"], SOURCE)

    def test_summaries_analytics_and_record_manifest_cover_all_source_rows(self):
        manifest = json.loads(RECORD_MANIFEST_PATH.read_text(encoding="utf-8"))
        analytics = json.loads((ANALYTICS_DIR / "all.json").read_text(encoding="utf-8"))
        weather = analytics["dimensoes"]["condicao_metereologica"]
        stats = self.summaries["all"]["stats_gerais"]
        record_page = query_records(
            manifest,
            None,
            None,
            1,
            1,
            lambda path: json.loads(
                (RECORD_MANIFEST_PATH.parent / path).read_text(encoding="utf-8")
            ),
        )

        self.assertEqual(manifest["total_registros"], 547347)
        self.assertEqual(
            sum(partition["quantidade"] for partition in manifest["particoes"] if partition["ano"] is None),
            0,
        )
        self.assertEqual(stats["total_acidentes"], manifest["total_registros"])
        self.assertEqual(
            sum(self.summaries["all"]["acidentes_por_ano"]["data"]),
            manifest["total_registros"],
        )
        self.assertEqual(analytics["total_registros"], manifest["total_registros"])
        self.assertEqual(sum(row["acidentes"] for row in weather), manifest["total_registros"])
        self.assertEqual(sum(row["mortos"] for row in weather), stats["total_mortos"])
        self.assertEqual(len(record_page["registros"]), 1)
        self.assertEqual(len(record_page["registros"][0]), 30)

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


if __name__ == "__main__":
    unittest.main()
