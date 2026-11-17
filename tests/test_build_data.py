import csv
import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.data_schema import ANALYTIC_DIMENSIONS, ANALYTIC_METRICS, RECORD_COLUMNS
from tools.build_data import write_analytics, write_record_assets


def source_row(identifier, date, state, weather, deaths, injuries, coordinates=True):
    row = {column: "" for column in RECORD_COLUMNS}
    row.update({
        "id": str(identifier),
        "data_inversa": date,
        "dia_semana": "Segunda-feira",
        "horario": "08:30",
        "uf": state,
        "br": "101",
        "km": "12.5",
        "municipio": "Cidade",
        "causa_acidente": "Chuva",
        "tipo_acidente": "Colisão",
        "classificacao_acidente": "Com Vítimas Feridas",
        "fase_dia": "Pleno dia",
        "sentido_via": "Crescente",
        "condicao_metereologica": weather,
        "tipo_pista": "Simples",
        "tracado_via": "Reta",
        "uso_solo": "Urbano",
        "pessoas": "3",
        "mortos": str(deaths),
        "feridos_leves": str(injuries),
        "feridos_graves": "0",
        "ilesos": "1",
        "ignorados": "0",
        "feridos": str(injuries),
        "veiculos": "2",
        "latitude": "-15.5" if coordinates else "",
        "longitude": "-47.5" if coordinates else "",
        "regional": "Centro",
        "delegacia": "Unidade 1",
        "uop": "UOP 1",
    })
    return row


class BuildDataTests(unittest.TestCase):
    def test_record_assets_keep_all_fields_and_rows_without_coordinates(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            csv_path = root / "records.csv"
            rows = [
                source_row(1, "01/01/2017", "AC", "Chuva", 1, 2),
                source_row(2, "02/01/2017", "AC", "Céu claro", 0, 1, coordinates=False),
                source_row(3, "03/01/2018", "SP", "Chuva", 2, 3),
            ]
            with csv_path.open("w", encoding="latin-1", newline="") as file:
                writer = csv.DictWriter(file, fieldnames=RECORD_COLUMNS, delimiter=";")
                writer.writeheader()
                writer.writerows(rows)

            manifest = write_record_assets(csv_path, root / "data", chunk_size=1)
            first_shard = json.loads(
                (root / "data" / "records" / "year_2017" / "uf_AC" / "part_0000.json")
                .read_text(encoding="utf-8")
            )
            second_shard = json.loads(
                (root / "data" / "records" / "year_2017" / "uf_AC" / "part_0001.json")
                .read_text(encoding="utf-8")
            )

        self.assertEqual(manifest["total_registros"], 3)
        self.assertEqual(manifest["colunas"], list(RECORD_COLUMNS))
        self.assertEqual(first_shard["rows"][0][0], "1")
        self.assertEqual(len(first_shard["rows"][0]), 30)
        self.assertIsNone(second_shard["rows"][0][25])
        self.assertEqual(second_shard["rows"][0][13], "Céu claro")

    def test_weather_analytics_aggregate_full_rows_and_metrics(self):
        input_rows = [
            source_row(1, "01/01/2017", "SP", "Chuva", 1, 2),
            source_row(2, "02/01/2017", "SP", "Chuva", 0, 1, coordinates=False),
            source_row(3, "03/01/2018", "GO", "Céu claro", 2, 3),
        ]
        frame_rows = []
        for row, year in zip(input_rows, (2017, 2017, 2018), strict=True):
            item = {"ano": year, "uf": row["uf"]}
            item.update({
                dimension: year if dimension == "ano" else (
                    row["data_inversa"][3:5] if dimension == "mes" else (
                        "08:00" if dimension == "hora" else
                        row[dimension] or "Não informado"
                    )
                )
                for dimension in ANALYTIC_DIMENSIONS
            })
            item.update({
                metric: 1 if metric == "acidentes" else int(row.get(metric, "0") or 0)
                for metric in ANALYTIC_METRICS
                if metric != "acidentes"
            })
            frame_rows.append(item)
        frame = pd.DataFrame(frame_rows)

        with tempfile.TemporaryDirectory() as temporary_directory:
            output_dir = Path(temporary_directory)
            write_analytics(
                frame,
                output_dir,
                [(None, None), (2017, None), (None, "SP"), (2017, "SP")],
            )
            all_data = json.loads(
                (output_dir / "analytics" / "all.json").read_text(encoding="utf-8")
            )
            selected = json.loads(
                (output_dir / "analytics" / "year_2017_uf_SP.json")
                .read_text(encoding="utf-8")
            )

        self.assertEqual(all_data["total_registros"], 3)
        self.assertEqual(all_data["dimensoes"]["condicao_metereologica"][0], {
            "valor": "Chuva",
            "acidentes": 2,
            "mortos": 1,
            "feridos": 3,
            "feridos_leves": 3,
            "feridos_graves": 0,
            "pessoas": 6,
            "ilesos": 2,
            "ignorados": 0,
            "veiculos": 4,
        })
        self.assertEqual(selected["total_registros"], 2)


if __name__ == "__main__":
    unittest.main()
