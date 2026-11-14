"""Build compact, filter-ready JSON assets from the PRF Kaggle CSV.

Usage:
  python tools/build_data.py --csv path/to/datatran2017-2024.csv
  python tools/build_data.py  # downloads the Kaggle dataset (requires Kaggle credentials)
"""

import argparse
import gzip
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

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
    "data_inversa", "uf", "br", "km", "municipio", "causa_acidente", "tipo_acidente",
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


def normalize_br(value):
    text = str(value).strip()
    if text.endswith(".0") and text[:-2].isdigit():
        text = text[:-2]
    digits = "".join(character for character in text if character.isdigit())
    return digits.zfill(3) if digits else ""


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
    """Fetch Brazil's outline from IBGE for masking the basemap outside the country."""
    endpoint = "https://servicodados.ibge.gov.br/api/v3/malhas/paises/BR"
    params = {"formato": "application/vnd.geo+json", "qualidade": "minima"}
    with urlopen(f"{endpoint}?{urlencode(params)}", timeout=60) as response:
        body = response.read()
        if body.startswith(b"\x1f\x8b"):
            body = gzip.decompress(body)
        collection = json.loads(body.decode("utf-8"))
    features = collection.get("features", []) if collection.get("type") == "FeatureCollection" else [collection]
    features = [feature for feature in features if feature.get("geometry", {}).get("type") in {"Polygon", "MultiPolygon"}]
    if not features:
        raise RuntimeError("A API de malhas do IBGE não retornou o contorno do Brasil.")
    (roads_dir / "brazil.geojson").write_text(
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
    required_columns = [column for column in CSV_COLUMNS if column not in {"br", "km"}]
    missing = [column for column in required_columns if column not in csv_header]
    if missing:
        raise ValueError(f"Colunas ausentes no CSV: {', '.join(missing)}")

    use_columns = [column for column in CSV_COLUMNS if column in csv_header]
    frame = pd.read_csv(csv_path, sep=";", encoding="latin-1", usecols=use_columns)
    for column in ("br", "km"):
        if column not in frame:
            frame[column] = ""
    frame["data_inversa"] = pd.to_datetime(frame["data_inversa"], format="%d/%m/%Y", errors="coerce")
    frame["ano"] = frame["data_inversa"].dt.year.fillna(0).astype(int)
    for column in ("mortos", "feridos"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0).astype(int)
    for column in ("latitude", "longitude"):
        frame[column] = pd.to_numeric(frame[column].astype(str).str.strip().str.replace(",", "."), errors="coerce")
    frame["uf"] = frame["uf"].fillna("").astype(str).str.upper()
    frame["br"] = frame["br"].fillna("").map(normalize_br)
    frame["km"] = pd.to_numeric(frame["km"], errors="coerce")
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
    road_groups = download_road_geometries(OUT) if not args.skip_roads else {}
    accidents_dir = OUT / "roads" / "accidents"
    accidents_dir.mkdir(parents=True, exist_ok=True)
    route_points = frame[frame["br"].ne("")].copy()
    route_points["data"] = route_points["data_inversa"].dt.strftime("%d/%m/%Y").fillna("—")
    fields = ["latitude", "longitude", "uf", "municipio", "data", "horario", "causa_acidente", "classificacao_acidente", "mortos", "feridos", "km", "ano"]
    for br, rows in route_points.groupby("br", sort=True):
        rows = rows[fields].copy().fillna("—")
        (accidents_dir / f"br_{br}.json").write_text(rows.to_json(orient="values", force_ascii=False), encoding="utf-8")
    routes = sorted(route_points["br"].unique())
    (OUT / "roads" / "accident_manifest.json").write_text(
        json.dumps(routes, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    print(f"Dados criados em {OUT}; {len(frame):,} acidentes válidos; {len(summaries)} filtros preparados.")
    print(f"{len(routes)} BRs com acidentes; {len(road_groups)} BRs com geometrias oficiais.")


if __name__ == "__main__":
    main()
