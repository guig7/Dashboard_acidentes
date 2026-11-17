import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from data_schema import RECORD_COLUMNS
from record_queries import (
    RecordDataError,
    RecordScopeError,
    RecordValidationError,
    analyze_records,
    query_records,
)


MANIFEST = {
    "versao": 1,
    "total_registros": 5,
    "tamanho_bloco": 2,
    "colunas": ["id", "data_inversa", "uf"],
    "particoes": [
        {
            "ano": 2017,
            "uf": "AC",
            "quantidade": 3,
            "blocos": 2,
            "caminho": "year_2017/uf_AC",
        },
        {
            "ano": 2018,
            "uf": "SP",
            "quantidade": 2,
            "blocos": 1,
            "caminho": "year_2018/uf_SP",
        },
    ],
}

CHUNKS = {
    "year_2017/uf_AC/part_0000.json": {
        "rows": [["1", "01/01/2017", "AC"], ["2", "02/01/2017", "AC"]],
    },
    "year_2017/uf_AC/part_0001.json": {
        "rows": [["3", "03/01/2017", "AC"]],
    },
    "year_2018/uf_SP/part_0000.json": {
        "rows": [["4", "01/01/2018", "SP"], ["5", "02/01/2018", "SP"]],
    },
}

ANALYSIS_MANIFEST = {
    "versao": 1,
    "total_registros": 3,
    "tamanho_bloco": 10,
    "colunas": list(RECORD_COLUMNS),
    "particoes": [
        {
            "ano": 2023,
            "uf": "MG",
            "quantidade": 2,
            "blocos": 1,
            "caminho": "year_2023/uf_MG",
        },
        {
            "ano": 2023,
            "uf": "SP",
            "quantidade": 1,
            "blocos": 1,
            "caminho": "year_2023/uf_SP",
        },
    ],
}


def _record(**overrides):
    values = {column: None for column in RECORD_COLUMNS}
    values.update({
        "id": "1",
        "data_inversa": "01/01/2023",
        "dia_semana": "domingo",
        "horario": "14:55:00",
        "uf": "MG",
        "br": "116",
        "km": 12.5,
        "municipio": "BELO HORIZONTE",
        "causa_acidente": "Acúmulo de água",
        "tipo_acidente": "Colisão",
        "classificacao_acidente": "Com Vítimas Feridas",
        "fase_dia": "Pleno dia",
        "sentido_via": "Crescente",
        "condicao_metereologica": "Chuva",
        "tipo_pista": "Simples",
        "tracado_via": "Reta",
        "uso_solo": "Urbano",
        "pessoas": 3,
        "mortos": 1,
        "feridos_leves": 1,
        "feridos_graves": 0,
        "ilesos": 1,
        "ignorados": 0,
        "feridos": 1,
        "veiculos": 2,
        "regional": "SPRF-MG",
        "delegacia": "DEL01-MG",
        "uop": "UOP01-DEL01-MG",
    })
    values.update(overrides)
    return [values[column] for column in RECORD_COLUMNS]


ANALYSIS_CHUNKS = {
    "year_2023/uf_MG/part_0000.json": {
        "rows": [
            _record(),
            _record(
                id="2",
                data_inversa="02/01/2023",
                horario="08:10:00",
                br="101",
                km=21.0,
                causa_acidente="Velocidade incompatível",
                condicao_metereologica="Céu claro",
                mortos=0,
                feridos=2,
            ),
        ],
    },
    "year_2023/uf_SP/part_0000.json": {
        "rows": [
            _record(
                id="3",
                uf="SP",
                data_inversa="02/01/2023",
                horario="14:15:00",
                br="116",
                km=15.0,
                causa_acidente="Velocidade incompatível",
            ),
        ],
    },
}


class QueryRecordsTests(unittest.TestCase):
    def test_paginates_across_shards_and_filter_partitions(self):
        result = query_records(
            MANIFEST,
            None,
            None,
            "2",
            "2",
            CHUNKS.__getitem__,
        )

        self.assertEqual(result["total_registros"], 5)
        self.assertEqual(result["total_paginas"], 3)
        self.assertEqual([row["id"] for row in result["registros"]], ["3", "4"])

    def test_filters_records_without_requiring_coordinates(self):
        result = query_records(
            MANIFEST,
            "2017",
            "ac",
            1,
            2,
            CHUNKS.__getitem__,
        )

        self.assertEqual(result["filtros"], {"ano": 2017, "uf": "AC"})
        self.assertEqual(result["total_registros"], 3)
        self.assertEqual([row["id"] for row in result["registros"]], ["1", "2"])

    def test_rejects_invalid_filters_pages_and_missing_assets(self):
        with self.assertRaises(RecordValidationError):
            query_records(MANIFEST, 2025, None, 1, 50, CHUNKS.__getitem__)
        with self.assertRaises(RecordValidationError):
            query_records(MANIFEST, None, None, 4, 2, CHUNKS.__getitem__)
        with self.assertRaises(RecordDataError):
            query_records(MANIFEST, None, None, 1, 2, lambda _path: None)

    def test_rejects_manifest_paths_that_do_not_match_filters(self):
        invalid_manifest = {
            **MANIFEST,
            "particoes": [
                {**MANIFEST["particoes"][0], "caminho": "year_2018/uf_AC"},
                MANIFEST["particoes"][1],
            ],
        }

        with self.assertRaises(RecordDataError):
            query_records(invalid_manifest, None, None, 1, 2, CHUNKS.__getitem__)

    def test_analysis_combines_filters_and_groups_all_metrics(self):
        result = analyze_records(
            ANALYSIS_MANIFEST,
            {
                "ano": 2023,
                "uf": "mg",
                "filtros": {
                    "br": "BR-116",
                    "condicao_metereologica": "chuva",
                },
                "agrupar_por": "causa_acidente",
                "metrica": "acidentes",
                "limite": 5,
            },
            ANALYSIS_CHUNKS.__getitem__,
        )

        self.assertEqual(result["modo"], "agrupamento")
        self.assertEqual(result["total_registros"], 1)
        self.assertEqual(result["total_categorias"], 1)
        self.assertEqual(result["resultado"][0]["valor"], "Acúmulo de água")
        self.assertEqual(result["resultado"][0]["acidentes"], 1)
        self.assertEqual(result["resultado"][0]["mortes"], 1)
        self.assertEqual(result["resultado"][0]["pessoas"], 3)

    def test_analysis_returns_limited_samples_and_infers_year_from_dates(self):
        result = analyze_records(
            ANALYSIS_MANIFEST,
            {
                "data_inicio": "01/01/2023",
                "data_fim": "01/01/2023",
                "km_min": 12,
                "km_max": 13,
                "filtros": {"mes": "01", "hora": "14:00"},
                "campos": ["id", "data_inversa", "km", "br", "causa_acidente"],
            },
            ANALYSIS_CHUNKS.__getitem__,
        )

        self.assertEqual(result["filtros"]["ano"], 2023)
        self.assertEqual(result["modo"], "amostra")
        self.assertEqual(result["total_registros"], 1)
        self.assertEqual(result["resultado"]["totais"]["acidentes"], 1)
        self.assertEqual(result["resultado"]["registros"], [{
            "id": "1",
            "data_inversa": "01/01/2023",
            "km": 12.5,
            "br": "116",
            "causa_acidente": "Acúmulo de água",
        }])

    def test_analysis_requires_scope_and_rejects_scans_over_budget(self):
        with self.assertRaises(RecordScopeError):
            analyze_records(
                ANALYSIS_MANIFEST,
                {"filtros": {"br": "116"}},
                ANALYSIS_CHUNKS.__getitem__,
            )

        large_manifest = {
            **ANALYSIS_MANIFEST,
            "tamanho_bloco": 1000,
            "total_registros": 40_001,
            "particoes": [{
                **ANALYSIS_MANIFEST["particoes"][0],
                "quantidade": 40_001,
                "blocos": 41,
            }],
        }
        with self.assertRaises(RecordScopeError):
            analyze_records(
                large_manifest,
                {"uf": "MG"},
                lambda _path: self.fail("Broad queries must be rejected before loading chunks"),
            )

    def test_analysis_rejects_unknown_fields_and_invalid_ranges(self):
        for query in (
            {"ano": 2023, "filtros": {"sql": "SELECT"}},
            {"ano": 2023, "km_min": 20, "km_max": 10},
            {"ano": 2023, "data_inicio": "31/02/2023"},
        ):
            with self.subTest(query=query), self.assertRaises(RecordValidationError):
                analyze_records(
                    ANALYSIS_MANIFEST,
                    query,
                    ANALYSIS_CHUNKS.__getitem__,
                )


if __name__ == "__main__":
    unittest.main()
