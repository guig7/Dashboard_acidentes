import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from analyst_queries import QueryDataError, QueryValidationError, execute_query


SUMMARIES = {
    "all": {
        "stats_gerais": {
            "total_acidentes": 100,
            "total_mortos": 10,
            "total_feridos": 20,
            "total_feridos_leves": 16,
            "total_feridos_graves": 4,
            "total_pessoas": 130,
            "total_ilesos": 110,
            "total_ignorados": 3,
            "total_veiculos": 72,
        },
        "acidentes_por_ano": {"labels": [2022, 2023, 2024], "data": [30, 40, 30]},
        "mortos_por_ano": {"labels": [2022, 2023, 2024], "data": [3, 4, 3]},
        "series_por_ano": {
            "acidentes": {"labels": [2022, 2023, 2024], "data": [30, 40, 30]},
            "mortes": {"labels": [2022, 2023, 2024], "data": [3, 4, 3]},
            "feridos": {"labels": [2022, 2023, 2024], "data": [8, 7, 5]},
        },
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

    def test_weather_distribution_sorts_and_paginates_all_metrics(self):
        distribution = [
            {
                "valor": "Chuva",
                "acidentes": 18,
                "mortos": 3,
                "feridos": 20,
                "feridos_leves": 16,
                "feridos_graves": 4,
                "pessoas": 28,
                "ilesos": 5,
                "ignorados": 1,
                "veiculos": 22,
            },
            {
                "valor": "Céu claro",
                "acidentes": 12,
                "mortos": 4,
                "feridos": 10,
                "feridos_leves": 9,
                "feridos_graves": 1,
                "pessoas": 18,
                "ilesos": 7,
                "ignorados": 0,
                "veiculos": 15,
            },
        ]
        result = execute_query(
            SUMMARIES,
            {
                "operacao": "consultar_distribuicao",
                "ano": "2023",
                "uf": "sp",
                "dimensao": "condicao_metereologica",
                "metrica": "mortes",
                "pagina": "1",
                "por_pagina": "1",
            },
            distribution_loader=lambda year, state, dimension: (
                distribution
                if (year, state, dimension) == (2023, "SP", "condicao_metereologica")
                else []
            ),
        )

        self.assertEqual(result["filtros"], {
            "ano": 2023,
            "uf": "SP",
            "dimensao": "condicao_metereologica",
            "metrica": "mortes",
        })
        self.assertEqual(result["total_registros"], 30)
        self.assertEqual(result["total_categorias"], 2)
        self.assertEqual(result["resultado"][0]["valor"], "Céu claro")
        self.assertEqual(result["resultado"][0]["mortes"], 4)

    def test_distribution_rejects_unknown_dimensions_and_unbounded_pages(self):
        with self.assertRaises(QueryValidationError):
            execute_query(
                SUMMARIES,
                {
                    "operacao": "consultar_distribuicao",
                    "dimensao": "sql",
                },
                distribution_loader=lambda *_args: [],
            )
        with self.assertRaises(QueryValidationError):
            execute_query(
                SUMMARIES,
                {
                    "operacao": "consultar_distribuicao",
                    "dimensao": "condicao_metereologica",
                    "por_pagina": 101,
                },
                distribution_loader=lambda *_args: [],
            )

    def test_distribution_requires_prepared_data(self):
        with self.assertRaises(QueryDataError):
            execute_query(SUMMARIES, {
                "operacao": "consultar_distribuicao",
                "dimensao": "condicao_metereologica",
            })

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

    def test_injury_series_is_available_and_invalid_metric_is_rejected(self):
        result = execute_query(SUMMARIES, {
            "operacao": "consultar_serie",
            "metrica": "feridos",
            "ano_inicio": 2023,
            "ano_fim": 2024,
        })

        self.assertEqual(result["resultado"], [
            {"ano": 2023, "valor": 7},
            {"ano": 2024, "valor": 5},
        ])
        with self.assertRaises(QueryValidationError):
            execute_query(SUMMARIES, {
                "operacao": "consultar_serie",
                "metrica": "risco",
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
