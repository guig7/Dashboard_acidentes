"""Build compact, filter-ready JSON assets from the PRF Kaggle CSV.

Usage:
  python tools/build_data.py --csv path/to/datatran2017-2024.csv
  python tools/build_data.py  # downloads the Kaggle dataset (requires Kaggle credentials)
"""

import argparse
import json
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "public" / "data"
YEARS = range(2017, 2025)
STATES = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
]
CSV_COLUMNS = [
    "data_inversa", "uf", "municipio", "causa_acidente", "tipo_acidente",
    "classificacao_acidente", "mortos", "feridos", "latitude", "longitude", "horario",
]


def resolve_csv(csv_arg):
    if csv_arg:
        return Path(csv_arg).expanduser().resolve()
    import kagglehub

    folder = Path(kagglehub.dataset_download("guilherme2008/acidentes-em-rodovias-federais"))
    csv_path = folder / "datatran2017-2024.csv"
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV não encontrado no dataset baixado: {csv_path}")
    return csv_path


def jsonable(value):
    return json.loads(json.dumps(value, ensure_ascii=False, allow_nan=False))


def make_entry(frame, prior_frame):
    if frame.empty:
        return {
            "stats_gerais": {}, "acidentes_por_ano": {}, "mortos_por_ano": {},
            "causas": {}, "estados": {}, "taxa_severidade": {},
            "heatmap_horarios": {}, "ranking_estados": {},
        }

    by_year = frame.groupby("ano").size().sort_index()
    by_year = by_year[by_year.index > 0]
    deaths_year = frame.groupby("ano")["mortos"].sum().sort_index()
    deaths_year = deaths_year[deaths_year.index > 0]

    causes = frame.groupby("causa_acidente").agg(
        total=("causa_acidente", "count"), mortos=("mortos", "sum"), feridos=("feridos", "sum")
    ).sort_values("total", ascending=False).head(10).reset_index()
    causes["taxa_severidade"] = (causes["mortos"] / causes["total"] * 100).round(2)

    states = frame["uf"].value_counts()
    ranking = frame.groupby("uf").agg(total_mortos=("mortos", "sum"), acidentes=("mortos", "size"))
    ranking["taxa_severidade"] = (ranking["total_mortos"] / ranking["acidentes"] * 100).round(2)
    ranking = ranking.sort_values("taxa_severidade", ascending=False).head(15)

    hours = frame.copy()
    hours["hora"] = pd.to_numeric(hours["horario"].astype(str).str[:2], errors="coerce").fillna(0).astype(int)
    hour_summary = hours.groupby("hora").agg(mortos=("mortos", "sum"), acidentes=("horario", "count")).sort_index()
    hour_summary["severidade"] = (hour_summary["mortos"] / hour_summary["acidentes"] * 100).round(2)

    accidents = len(frame)
    deaths = int(frame["mortos"].sum())
    rate = deaths / accidents * 100 if accidents else 0
    prior_accidents = len(prior_frame)
    prior_deaths = int(prior_frame["mortos"].sum()) if prior_accidents else 0
    prior_rate = prior_deaths / prior_accidents * 100 if prior_accidents else 0

    return jsonable({
        "stats_gerais": {"total_acidentes": accidents, "total_mortos": deaths, "total_feridos": int(frame["feridos"].sum())},
        "acidentes_por_ano": {"labels": by_year.index.astype(int).tolist(), "data": by_year.astype(int).tolist()},
        "mortos_por_ano": {"labels": deaths_year.index.astype(int).tolist(), "data": deaths_year.astype(int).tolist()},
        "causas": {
            "labels": causes["causa_acidente"].tolist(), "data": causes["total"].astype(int).tolist(),
            "mortos": causes["mortos"].astype(int).tolist(), "feridos": causes["feridos"].astype(int).tolist(),
            "taxa_severidade": causes["taxa_severidade"].astype(float).tolist(),
        },
        "estados": {"labels": states.index.tolist(), "data": states.astype(int).tolist()},
        "taxa_severidade": {
            "taxa_atual": round(rate, 2), "taxa_anterior": round(prior_rate, 2),
            "variacao": round(rate - prior_rate, 2) if prior_accidents else 0,
            "total_acidentes": accidents, "total_mortos": deaths,
        },
        "heatmap_horarios": {
            "labels": [f"{int(hour):02d}:00" for hour in hour_summary.index],
            "acidentes": hour_summary["acidentes"].astype(int).tolist(),
            "severidade": hour_summary["severidade"].astype(float).tolist(),
            "mortos": hour_summary["mortos"].astype(int).tolist(),
        },
        "ranking_estados": {
            "labels": ranking.index.tolist(), "taxa_severidade": ranking["taxa_severidade"].astype(float).tolist(),
            "acidentes": ranking["acidentes"].astype(int).tolist(), "mortos": ranking["total_mortos"].astype(int).tolist(),
        },
    })


def filter_key(year=None, state=None):
    return "_".join(([f"year_{year}"] if year else []) + ([f"uf_{state}"] if state else [])) or "all"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="Caminho para datatran2017-2024.csv")
    parser.add_argument("--map-all-limit", type=int, default=2000, help="Máximo de marcadores no mapa sem filtros")
    parser.add_argument("--map-filter-limit", type=int, default=500, help="Máximo de marcadores por combinação de filtros")
    args = parser.parse_args()

    csv_path = resolve_csv(args.csv)
    csv_header = pd.read_csv(csv_path, sep=";", encoding="latin-1", nrows=0).columns
    missing = [column for column in CSV_COLUMNS if column not in csv_header]
    if missing:
        raise ValueError(f"Colunas ausentes no CSV: {', '.join(missing)}")

    frame = pd.read_csv(csv_path, sep=";", encoding="latin-1", usecols=CSV_COLUMNS)
    frame["data_inversa"] = pd.to_datetime(frame["data_inversa"], format="%d/%m/%Y", errors="coerce")
    frame["ano"] = frame["data_inversa"].dt.year.fillna(0).astype(int)
    for column in ("mortos", "feridos"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    for column in ("latitude", "longitude"):
        frame[column] = pd.to_numeric(frame[column].astype(str).str.strip().str.replace(",", "."), errors="coerce")
    frame["uf"] = frame["uf"].fillna("").astype(str).str.upper()
    frame = frame[frame["latitude"].between(-35, 6) & frame["longitude"].between(-75, -34)].dropna(subset=["latitude", "longitude"])

    OUT.mkdir(parents=True, exist_ok=True)
    maps_dir = OUT / "maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    tables_dir = OUT / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)
    summaries = {}
    filter_sets = [(None, None)]
    filter_sets += [(year, None) for year in YEARS]
    filter_sets += [(None, state) for state in STATES]
    filter_sets += [(year, state) for year in YEARS for state in STATES]

    for year, state in filter_sets:
        selected = frame
        if year:
            selected = selected[selected["ano"] == year]
        if state:
            selected = selected[selected["uf"] == state]

        previous = frame.iloc[0:0]
        if year:
            previous = frame[frame["ano"] == year - 1]
            if state:
                previous = previous[previous["uf"] == state]

        key = filter_key(year, state)
        summaries[key] = make_entry(selected, previous)

        map_rows = selected.dropna(subset=["latitude", "longitude"])
        limit = args.map_all_limit if key == "all" else args.map_filter_limit
        if len(map_rows) > limit:
            map_rows = map_rows.sample(limit, random_state=42)
        map_rows = map_rows.copy()
        map_rows["data"] = map_rows["data_inversa"].dt.strftime("%d/%m/%Y").fillna("—")
        map_rows = map_rows[[
            "latitude", "longitude", "municipio", "uf", "causa_acidente",
            "classificacao_acidente", "mortos", "feridos", "data", "horario",
        ]].fillna("—")
        (maps_dir / f"{key}.json").write_text(
            map_rows.to_json(orient="records", force_ascii=False), encoding="utf-8"
        )

        table_rows = selected.head(args.map_filter_limit).copy()
        table_rows["data_inversa"] = table_rows["data_inversa"].dt.strftime("%d/%m/%Y")
        table_rows = table_rows[[
            "data_inversa", "uf", "municipio", "causa_acidente", "tipo_acidente",
            "classificacao_acidente", "mortos", "feridos", "horario",
        ]].fillna("—")
        (tables_dir / f"{key}.json").write_text(
            table_rows.to_json(orient="records", force_ascii=False), encoding="utf-8"
        )

    (OUT / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"Dados criados em {OUT}; {len(frame):,} acidentes válidos; {len(summaries)} filtros preparados.")


if __name__ == "__main__":
    main()
