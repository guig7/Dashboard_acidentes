"""Build compact, filter-ready JSON assets from the PRF Kaggle CSV.

Usage:
  python tools/build_data.py --csv path/to/datatran2017-2024.csv
  python tools/build_data.py  # downloads the Kaggle dataset (requires Kaggle credentials)
"""

import argparse
import csv
import gzip
import json
import math
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from data_schema import (
    ANALYTIC_DIMENSIONS,
    ANALYTIC_METRICS,
    RECORD_COLUMNS,
    RECORD_FLOAT_FIELDS,
    RECORD_INTEGER_FIELDS,
)

OUT = ROOT / "public" / "data"
YEARS = range(2017, 2025)
STATES = [
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT",
    "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO",
    "RR", "SC", "SP", "SE", "TO",
]
CSV_COLUMNS = [
    column for column in RECORD_COLUMNS if column != "id"
]
RECORD_CHUNK_SIZE = 1000
MAX_ASSET_BYTES = 20 * 1024 * 1024
_SHORT_YEAR_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{2}\Z")


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
            "heatmap_horarios": {}, "ranking_estados": {}, "series_por_ano": {},
        }

    by_year = frame.groupby("ano", observed=True).size().sort_index()
    by_year = by_year[by_year.index > 0]
    deaths_year = frame.groupby("ano", observed=True)["mortos"].sum().sort_index()
    deaths_year = deaths_year[deaths_year.index > 0]
    annual_metrics = frame[frame["ano"] > 0].groupby("ano", observed=True).agg(
        acidentes=("ano", "size"),
        mortes=("mortos", "sum"),
        feridos=("feridos", "sum"),
        feridos_leves=("feridos_leves", "sum"),
        feridos_graves=("feridos_graves", "sum"),
        pessoas=("pessoas", "sum"),
        ilesos=("ilesos", "sum"),
        ignorados=("ignorados", "sum"),
        veiculos=("veiculos", "sum"),
    ).sort_index()
    annual_series = {
        ("mortes" if metric == "mortos" else metric): {
            "labels": annual_metrics.index.astype(int).tolist(),
            "data": annual_metrics[
                "mortes" if metric == "mortos" else metric
            ].astype(int).tolist(),
        }
        for metric in ANALYTIC_METRICS
    }

    causes = frame.groupby("causa_acidente", observed=True).agg(
        total=("causa_acidente", "count"), mortos=("mortos", "sum"), feridos=("feridos", "sum")
    ).sort_values("total", ascending=False).head(10).reset_index()
    causes["taxa_severidade"] = (causes["mortos"] / causes["total"] * 100).round(2)

    states = frame["uf"].value_counts()
    ranking = frame.groupby("uf", observed=True).agg(
        total_mortos=("mortos", "sum"), acidentes=("mortos", "size")
    )
    ranking["taxa_severidade"] = (ranking["total_mortos"] / ranking["acidentes"] * 100).round(2)
    ranking = ranking.sort_values("taxa_severidade", ascending=False).head(15)

    hours = frame[["horario", "mortos"]].copy()
    hours["hora"] = pd.to_numeric(hours["horario"].astype(str).str[:2], errors="coerce").fillna(0).astype(int)
    hour_summary = hours.groupby("hora", observed=True).agg(
        mortos=("mortos", "sum"), acidentes=("horario", "count")
    ).sort_index()
    hour_summary["severidade"] = (hour_summary["mortos"] / hour_summary["acidentes"] * 100).round(2)

    accidents = len(frame)
    deaths = int(frame["mortos"].sum())
    rate = deaths / accidents * 100 if accidents else 0
    prior_accidents = len(prior_frame)
    prior_deaths = int(prior_frame["mortos"].sum()) if prior_accidents else 0
    prior_rate = prior_deaths / prior_accidents * 100 if prior_accidents else 0

    return jsonable({
        "stats_gerais": {
            "total_acidentes": accidents,
            "total_mortos": deaths,
            "total_feridos": int(frame["feridos"].sum()),
            "total_feridos_leves": int(frame["feridos_leves"].sum()),
            "total_feridos_graves": int(frame["feridos_graves"].sum()),
            "total_pessoas": int(frame["pessoas"].sum()),
            "total_ilesos": int(frame["ilesos"].sum()),
            "total_ignorados": int(frame["ignorados"].sum()),
            "total_veiculos": int(frame["veiculos"].sum()),
        },
        "acidentes_por_ano": {"labels": by_year.index.astype(int).tolist(), "data": by_year.astype(int).tolist()},
        "mortos_por_ano": {"labels": deaths_year.index.astype(int).tolist(), "data": deaths_year.astype(int).tolist()},
        "series_por_ano": annual_series,
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


def normalize_br(value):
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    digits = "".join(character for character in text if character.isdigit())
    return digits.zfill(3) if digits else ""


def parse_accident_date(value):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    date_format = "%m/%d/%y" if _SHORT_YEAR_DATE.fullmatch(text) else "%d/%m/%Y"
    try:
        return datetime.strptime(text, date_format)
    except ValueError:
        return None


def parse_accident_dates(values):
    text = values.astype("string").str.strip()
    short_year = text.str.fullmatch(_SHORT_YEAR_DATE.pattern, na=False)
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    parsed.loc[short_year] = pd.to_datetime(
        text.loc[short_year],
        format="%m/%d/%y",
        errors="coerce",
    )
    long_year = ~short_year
    parsed.loc[long_year] = pd.to_datetime(
        text.loc[long_year],
        format="%d/%m/%Y",
        errors="coerce",
    )
    return parsed


def _record_value(column, raw_value, row_number):
    value = (raw_value or "").strip()
    if not value:
        return None
    if column in RECORD_INTEGER_FIELDS:
        try:
            number = float(value)
            if not number.is_integer():
                raise ValueError("valor não inteiro")
            return int(number)
        except ValueError as error:
            raise ValueError(
                f"Valor inválido na coluna '{column}', linha {row_number}: {value!r}."
            ) from error
    if column in RECORD_FLOAT_FIELDS:
        try:
            number = float(value.replace(",", "."))
            if not math.isfinite(number):
                raise ValueError("valor não finito")
            return number
        except ValueError as error:
            raise ValueError(
                f"Valor inválido na coluna '{column}', linha {row_number}: {value!r}."
            ) from error
    return value


def write_record_assets(csv_path, output_dir, chunk_size=RECORD_CHUNK_SIZE):
    """Write all source rows as schema-backed JSON chunks grouped by year and UF."""
    if isinstance(chunk_size, bool) or not isinstance(chunk_size, int) or chunk_size < 1:
        raise ValueError("O tamanho dos blocos de registros deve ser um inteiro positivo.")

    records_dir = output_dir / "records"
    records_dir.mkdir(parents=True, exist_ok=True)
    for old_shard in records_dir.rglob("part_*.json"):
        old_shard.unlink()

    counts = {}
    chunk_counts = {}
    buffers = {}

    def partition_for(row):
        date_text = (row.get("data_inversa") or "").strip()
        parsed_date = parse_accident_date(date_text)
        year = parsed_date.year if parsed_date is not None else None
        if year not in YEARS:
            year = None

        state_text = (row.get("uf") or "").strip().upper()
        state = state_text if state_text in STATES else None
        return year, state

    def flush_partition(partition):
        rows = buffers[partition]
        if not rows:
            return
        year, state = partition
        year_dir = f"year_{year}" if year is not None else "year_unknown"
        state_dir = f"uf_{state}" if state is not None else "uf_unknown"
        partition_dir = records_dir / year_dir / state_dir
        partition_dir.mkdir(parents=True, exist_ok=True)
        chunk_index = chunk_counts.get(partition, 0)
        serialized = json.dumps(
            {"rows": rows}, ensure_ascii=False, separators=(",", ":"), allow_nan=False
        )
        if len(serialized.encode("utf-8")) > MAX_ASSET_BYTES:
            raise ValueError(
                f"Bloco de registros acima do limite seguro em {year_dir}/{state_dir}; "
                "reduza RECORD_CHUNK_SIZE."
            )
        (partition_dir / f"part_{chunk_index:04d}.json").write_text(
            serialized, encoding="utf-8"
        )
        chunk_counts[partition] = chunk_index + 1
        buffers[partition] = []

    with Path(csv_path).open("r", encoding="latin-1", newline="") as csv_file:
        reader = csv.DictReader(csv_file, delimiter=";")
        missing = [column for column in RECORD_COLUMNS if column not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"Colunas ausentes no CSV completo: {', '.join(missing)}")

        for row_number, row in enumerate(reader, start=2):
            if None in row:
                raise ValueError(f"Quantidade de campos inesperada na linha {row_number} do CSV.")
            partition = partition_for(row)
            rows = buffers.setdefault(partition, [])
            rows.append([
                _record_value(column, row.get(column), row_number)
                for column in RECORD_COLUMNS
            ])
            counts[partition] = counts.get(partition, 0) + 1
            if len(rows) >= chunk_size:
                flush_partition(partition)

    for partition in sorted(
        buffers,
        key=lambda item: (
            item[0] is None, item[0] or 0, item[1] is None, item[1] or ""
        ),
    ):
        flush_partition(partition)

    partitions = []
    for year, state in sorted(
        counts,
        key=lambda item: (
            item[0] is None, item[0] or 0, item[1] is None, item[1] or ""
        ),
    ):
        year_dir = f"year_{year}" if year is not None else "year_unknown"
        state_dir = f"uf_{state}" if state is not None else "uf_unknown"
        partitions.append({
            "ano": year,
            "uf": state,
            "quantidade": counts[(year, state)],
            "blocos": chunk_counts[(year, state)],
            "caminho": f"{year_dir}/{state_dir}",
        })

    manifest = {
        "versao": 1,
        "total_registros": sum(counts.values()),
        "tamanho_bloco": chunk_size,
        "colunas": list(RECORD_COLUMNS),
        "particoes": partitions,
    }
    (records_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    return manifest


def write_analytics(frame, output_dir, filter_sets):
    """Precompute complete categorical distributions for every dashboard filter."""
    analytics_dir = output_dir / "analytics"
    analytics_dir.mkdir(parents=True, exist_ok=True)

    for old_file in analytics_dir.glob("*.json"):
        old_file.unlink()

    grouped_dimensions = {}
    numeric_metrics = [metric for metric in ANALYTIC_METRICS if metric != "acidentes"]
    for dimension in ANALYTIC_DIMENSIONS:
        if dimension == "ano":
            values = frame["ano"].map(
                lambda year: "Não informado" if year == 0 else str(year)
            )
        elif dimension == "mes":
            values = frame["mes"]
        elif dimension in {"uf", "br"}:
            values = frame[dimension].replace("", "Não informado")
        else:
            values = frame[dimension]
        source = frame.assign(_dimension=values)
        grouped = source.groupby(
            ["ano", "uf", "_dimension"], dropna=False, observed=True
        ).agg(
            acidentes=("uf", "size"),
            **{metric: (metric, "sum") for metric in numeric_metrics},
        ).reset_index()
        grouped_dimensions[dimension] = grouped

    for year, state in filter_sets:
        key = filter_key(year, state)
        dimensions = {}
        filtered_frame = frame
        if year is not None:
            filtered_frame = filtered_frame[filtered_frame["ano"] == year]
        if state is not None:
            filtered_frame = filtered_frame[filtered_frame["uf"] == state]
        for dimension, grouped in grouped_dimensions.items():
            selected = grouped
            if year is not None:
                selected = selected[selected["ano"] == year]
            if state is not None:
                selected = selected[selected["uf"] == state]
            if selected.empty:
                dimensions[dimension] = []
                continue

            totals = selected.groupby(
                "_dimension", dropna=False, observed=True
            )[list(ANALYTIC_METRICS)].sum().reset_index()
            totals = totals.sort_values(
                ["acidentes", "_dimension"],
                ascending=[False, True],
                kind="stable",
            )
            dimensions[dimension] = [
                {
                    "valor": str(row["_dimension"]),
                    **{metric: int(row[metric]) for metric in ANALYTIC_METRICS},
                }
                for _, row in totals.iterrows()
            ]

        (analytics_dir / f"{key}.json").write_text(
            json.dumps(
                {"total_registros": int(len(filtered_frame)), "dimensoes": dimensions},
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ),
            encoding="utf-8",
        )


def download_road_geometries(output_dir):
    """Fetch official federal-road centerlines from Infra S.A.'s ArcGIS service."""
    endpoint = "https://geo.infrasa.gov.br/server/rest/services/Hosted/Rodovias_Federais/FeatureServer/0/query"
    params = {
        "where": "ds_jurisdi='Federal' AND nm_tipo_tr='Eixo Principal'",
        "outFields": "vl_br,sg_uf,vl_codigo,vl_km_inic,vl_km_fina",
        "returnGeometry": "true", "outSR": "4326", "maxAllowableOffset": "0.0001",
        "geometryPrecision": "5", "resultRecordCount": "20000", "f": "geojson",
    }
    with urlopen(f"{endpoint}?{urlencode(params)}", timeout=90) as response:
        collection = json.loads(response.read().decode("utf-8"))
    if collection.get("error") or not isinstance(collection.get("features"), list):
        raise RuntimeError(f"Não foi possível obter as geometrias oficiais das BRs: {collection.get('error', 'resposta inválida')}")

    grouped = {}
    for feature in collection["features"]:
        props = feature.get("properties") or {}
        br = normalize_br(props.get("vl_br", ""))
        geometry = feature.get("geometry")
        if not br or not geometry:
            continue
        grouped.setdefault(br, []).append({
            "type": "Feature", "geometry": geometry,
            "properties": {
                "br": br, "uf": props.get("sg_uf") or "", "codigo": props.get("vl_codigo") or "",
                "km_inicio": props.get("vl_km_inic"), "km_fim": props.get("vl_km_fina"),
            },
        })

    roads_dir = output_dir / "roads"
    roads_dir.mkdir(parents=True, exist_ok=True)
    all_features = [feature for features in grouped.values() for feature in features]
    (roads_dir / "all.geojson").write_text(
        json.dumps({"type": "FeatureCollection", "features": all_features}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    manifest = [{"br": br, "trechos": len(features)} for br, features in sorted(grouped.items())]
    (roads_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    download_brazil_boundary(roads_dir)
    return grouped


def download_brazil_boundary(roads_dir):
    """Fetch the country outline and state boundaries from IBGE for the custom map."""
    endpoint = "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    params = {"formato": "application/vnd.geo+json", "qualidade": "minima"}
    def fetch_features(query):
        with urlopen(f"{endpoint}?{urlencode(query)}", timeout=60) as response:
            body = response.read()
            if body.startswith(b"\x1f\x8b"):
                body = gzip.decompress(body)
            collection = json.loads(body.decode("utf-8"))
        features = collection.get("features", []) if collection.get("type") == "FeatureCollection" else [collection]
        return [feature for feature in features if feature.get("geometry", {}).get("type") in {"Polygon", "MultiPolygon"}]

    country_features = fetch_features(params)
    state_features = fetch_features({**params, "intrarregiao": "UF"})
    if not country_features or not state_features:
        raise RuntimeError("A API de malhas do IBGE não retornou o contorno do Brasil e dos estados.")
    for filename, features in (("brazil.geojson", country_features), ("states.geojson", state_features)):
        (roads_dir / filename).write_text(
            json.dumps({"type": "FeatureCollection", "features": features}, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8",
        )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", help="Caminho para datatran2017-2024.csv")
    parser.add_argument("--map-all-limit", type=int, default=2000, help="Máximo de marcadores no mapa sem filtros")
    parser.add_argument("--map-filter-limit", type=int, default=500, help="Máximo de marcadores por combinação de filtros")
    parser.add_argument("--skip-roads", action="store_true", help="Não atualizar as geometrias oficiais do DNIT")
    args = parser.parse_args()

    csv_path = resolve_csv(args.csv)
    csv_header = pd.read_csv(csv_path, sep=";", encoding="latin-1", nrows=0).columns
    missing = [column for column in RECORD_COLUMNS if column not in csv_header]
    if missing:
        raise ValueError(f"Colunas ausentes no CSV completo: {', '.join(missing)}")

    use_columns = [column for column in CSV_COLUMNS if column in csv_header]
    frame = pd.read_csv(
        csv_path,
        sep=";",
        encoding="latin-1",
        usecols=use_columns,
        dtype={
            column: "category"
            for column in ANALYTIC_DIMENSIONS
            if column in use_columns and column not in {"hora"}
        },
    )
    frame["data_inversa"] = parse_accident_dates(frame["data_inversa"])
    frame["ano"] = frame["data_inversa"].dt.year.fillna(0).astype(int)
    for column in (
        "pessoas", "mortos", "feridos_leves", "feridos_graves", "ilesos",
        "ignorados", "feridos", "veiculos",
    ):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    for column in ("latitude", "longitude"):
        frame[column] = pd.to_numeric(frame[column].astype(str).str.strip().str.replace(",", "."), errors="coerce")
    frame["uf"] = frame["uf"].astype("string").fillna("").str.upper()
    frame["br"] = frame["br"].astype("string").fillna("").map(normalize_br)
    frame["km"] = pd.to_numeric(frame["km"], errors="coerce")
    for column in ANALYTIC_DIMENSIONS:
        if column in {"uf", "br", "hora", "ano", "mes"}:
            continue
        frame[column] = frame[column].astype("string").fillna("Não informado").astype("category")
    frame["mes"] = frame["data_inversa"].dt.month.map(
        lambda value: f"{int(value):02d}" if pd.notna(value) else "Não informado"
    )
    frame["hora"] = (
        pd.to_numeric(frame["horario"].astype(str).str[:2], errors="coerce")
        .map(lambda value: f"{int(value):02d}:00" if pd.notna(value) and 0 <= value <= 23 else "Não informado")
    )
    map_frame = frame[
        frame["latitude"].between(-35, 6) & frame["longitude"].between(-75, -34)
    ].dropna(subset=["latitude", "longitude"])

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

        map_selected = map_frame
        if year:
            map_selected = map_selected[map_selected["ano"] == year]
        if state:
            map_selected = map_selected[map_selected["uf"] == state]
        map_rows = map_selected[
            [
                "latitude", "longitude", "municipio", "uf", "causa_acidente",
                "classificacao_acidente", "mortos", "feridos", "data_inversa", "horario",
            ]
        ].dropna(subset=["latitude", "longitude"]).copy()
        limit = args.map_all_limit if key == "all" else args.map_filter_limit
        if len(map_rows) > limit:
            map_rows = map_rows.sample(limit, random_state=42)
        map_rows["data"] = map_rows["data_inversa"].dt.strftime("%d/%m/%Y").fillna("—")
        map_rows = map_rows[[
            "latitude", "longitude", "municipio", "uf", "causa_acidente",
            "classificacao_acidente", "mortos", "feridos", "data", "horario",
        ]].astype(object)
        map_rows = map_rows.where(pd.notna(map_rows), "—")
        (maps_dir / f"{key}.json").write_text(
            map_rows.to_json(orient="records", force_ascii=False), encoding="utf-8"
        )

        table_rows = selected.head(args.map_filter_limit).copy()
        table_rows["data_inversa"] = table_rows["data_inversa"].dt.strftime("%d/%m/%Y")
        table_rows = table_rows[[
            "data_inversa", "uf", "municipio", "causa_acidente", "tipo_acidente",
            "classificacao_acidente", "mortos", "feridos", "horario",
        ]].astype(object)
        table_rows = table_rows.where(pd.notna(table_rows), "—")
        (tables_dir / f"{key}.json").write_text(
            table_rows.to_json(orient="records", force_ascii=False), encoding="utf-8"
        )

    (OUT / "summary.json").write_text(
        json.dumps(summaries, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    write_analytics(frame, OUT, filter_sets)
    record_manifest = write_record_assets(csv_path, OUT)
    print(
        f"Base completa: {record_manifest['total_registros']:,} registros em "
        f"{len(record_manifest['particoes']):,} partições de JSON."
    )
    road_groups = download_road_geometries(OUT) if not args.skip_roads else {}
    accidents_dir = OUT / "roads" / "accidents"
    accidents_dir.mkdir(parents=True, exist_ok=True)
    route_points = map_frame[map_frame["br"].ne("")].copy()
    route_points["data"] = route_points["data_inversa"].dt.strftime("%d/%m/%Y").fillna("—")
    fields = ["latitude", "longitude", "uf", "municipio", "data", "horario", "causa_acidente", "classificacao_acidente", "mortos", "feridos", "km", "ano"]
    for br, rows in route_points.groupby("br", sort=True):
        rows = rows[fields].copy().astype(object)
        rows = rows.where(pd.notna(rows), "—")
        (accidents_dir / f"br_{br}.json").write_text(rows.to_json(orient="values", force_ascii=False), encoding="utf-8")
    routes = sorted(route_points["br"].unique())
    (OUT / "roads" / "accident_manifest.json").write_text(
        json.dumps(routes, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(
        f"Dados criados em {OUT}; {len(frame):,} acidentes na base e "
        f"{len(map_frame):,} com coordenadas válidas; {len(summaries)} filtros preparados."
    )
    print(f"{len(routes)} BRs com acidentes; {len(road_groups)} BRs com geometrias oficiais.")


if __name__ == "__main__":
    main()
