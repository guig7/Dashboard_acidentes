import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from record_queries import (
    RecordDataError,
    RecordValidationError,
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


if __name__ == "__main__":
    unittest.main()
