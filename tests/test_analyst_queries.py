import unittest

from analyst_queries import QueryDataError, QueryValidationError, execute_query


SUMMARIES = {
    "all": {
        "stats_gerais": {
            "total_acidentes": 100,
            "total_mortos": 10,
            "total_feridos": 20,
        },
        "acidentes_por_ano": {"labels": [2022, 2023, 2024], "data": [30, 40, 30]},
        "mortos_por_ano": {"labels": [2022, 2023, 2024], "data": [3, 4, 3]},
        "causas": {
            "labels": ["Falta de atenção", "Velocidade incompatível"],
            "data": [60, 40],
            "mortos": [4, 6],
            "feridos": [12, 8],
            "taxa_severidade": [6.67, 15.0],
        },
    },
    "year_2023_uf_GO": {
        "stats_gerais": {
            "total_acidentes": 12,
            "total_mortos": 2,
            "total_feridos": 5,
        },
    },
    "year_2023_uf_SP": {
        "stats_gerais": {
            "total_acidentes": 20,
            "total_mortos": 3,
            "total_feridos": 7,
        },
    },
}


class ExecuteQueryTests(unittest.TestCase):
    def test_summary_returns_requested_metrics_and_normalized_filters(self):
        result = execute_query(SUMMARIES, {
            "operacao": "consultar_resumo",
            "ano": "2023",
            "uf": "go",
            "metrica": "mortes",
        })

        self.assertEqual(result["filtros"], {"ano": 2023, "uf": "GO"})
        self.assertEqual(result["resultado"], {"mortes": 2})
        self.assertIn("fonte", result)

    def test_state_comparison_uses_selected_year_and_metric(self):
        result = execute_query(SUMMARIES, {
            "operacao": "comparar_estados",
            "ano": 2023,
            "ufs": ["GO", "SP"],
            "metrica": "mortes",
        })

        self.assertEqual(result["resultado"], [
            {"uf": "GO", "valor": 2},
            {"uf": "SP", "valor": 3},
        ])

    def test_cause_limit_is_bounded(self):
        result = execute_query(SUMMARIES, {
            "operacao": "listar_causas",
            "limite": 1,
        })

        self.assertEqual(len(result["resultado"]), 1)
        self.assertEqual(result["resultado"][0]["causa"], "Falta de atenção")

    def test_series_filters_year_range(self):
        result = execute_query(SUMMARIES, {
            "operacao": "consultar_serie",
            "metrica": "acidentes",
            "ano_inicio": 2023,
            "ano_fim": 2024,
        })

        self.assertEqual(result["resultado"], [
            {"ano": 2023, "valor": 40},
            {"ano": 2024, "valor": 30},
        ])

    def test_rejects_unknown_fields_and_out_of_range_years(self):
        with self.assertRaises(QueryValidationError):
            execute_query(SUMMARIES, {
                "operacao": "consultar_resumo",
                "sql": "SELECT * FROM acidentes",
            })
        with self.assertRaises(QueryValidationError):
            execute_query(SUMMARIES, {
                "operacao": "consultar_resumo",
                "ano": 2025,
            })

    def test_rejects_unavailable_injury_series_and_invalid_comparison(self):
        with self.assertRaises(QueryValidationError):
            execute_query(SUMMARIES, {
                "operacao": "consultar_serie",
                "metrica": "feridos",
            })
        with self.assertRaises(QueryValidationError):
            execute_query(SUMMARIES, {
                "operacao": "comparar_estados",
                "ufs": ["GO", "go"],
                "metrica": "mortes",
            })

    def test_reports_missing_prepared_data(self):
        with self.assertRaises(QueryDataError):
            execute_query(SUMMARIES, {
                "operacao": "consultar_resumo",
                "ano": 2018,
                "uf": "AC",
            })


if __name__ == "__main__":
    unittest.main()
