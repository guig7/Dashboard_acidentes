"""Validated, deterministic queries over the dashboard's prepared summaries."""

import math
from collections.abc import Callable, Mapping
from typing import cast

from data_schema import ANALYTIC_DIMENSIONS, ANALYTIC_METRICS

YEARS = frozenset(range(2017, 2025))
YEAR_STRINGS = frozenset(str(year) for year in YEARS)
STATES = frozenset({
    "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA",
    "MT", "MS", "MG", "PA", "PB", "PR", "PE", "PI", "RJ", "RN",
    "RS", "RO", "RR", "SC", "SP", "SE", "TO",
})
METRICS = {
    "acidentes": "total_acidentes",
    "mortes": "total_mortos",
    "feridos": "total_feridos",
    "feridos_leves": "total_feridos_leves",
    "feridos_graves": "total_feridos_graves",
    "pessoas": "total_pessoas",
    "ilesos": "total_ilesos",
    "ignorados": "total_ignorados",
    "veiculos": "total_veiculos",
}
DISTRIBUTION_METRICS = {
    "acidentes": "acidentes",
    "mortes": "mortos",
    "feridos": "feridos",
    "feridos_leves": "feridos_leves",
    "feridos_graves": "feridos_graves",
    "pessoas": "pessoas",
    "ilesos": "ilesos",
    "ignorados": "ignorados",
    "veiculos": "veiculos",
}
SOURCE = "Dados PRF pré-processados do painel (2017–2024)."
DistributionLoader = Callable[[int | None, str | None, str], object]


class QueryValidationError(ValueError):
    """Raised when a query does not follow the supported operation contract."""


class QueryDataError(ValueError):
    """Raised when prepared data needed by a valid query is unavailable."""


def execute_query(
    summaries: Mapping[str, object],
    payload: object,
    distribution_loader: DistributionLoader | None = None,
) -> dict[str, object]:
    query = _as_mapping(payload, "A consulta deve ser um objeto JSON.")
    operation = query.get("operacao")
    if not isinstance(operation, str):
        raise QueryValidationError("Informe uma operação válida em 'operacao'.")

    handlers = {
        "consultar_resumo": _consultar_resumo,
        "comparar_estados": _comparar_estados,
        "listar_causas": _listar_causas,
        "consultar_serie": _consultar_serie,
    }
    if operation == "consultar_distribuicao":
        result = _consultar_distribuicao(query, distribution_loader)
        return {
            "operacao": operation,
            "fonte": SOURCE,
            **result,
        }

    handler = handlers.get(operation)
    if handler is None:
        raise QueryValidationError("Operação não suportada.")

    result = handler(summaries, query)
    return {
        "operacao": operation,
        "fonte": SOURCE,
        **result,
    }


def _consultar_distribuicao(
    query: Mapping[str, object],
    distribution_loader: DistributionLoader | None,
) -> dict[str, object]:
    _check_fields(
        query,
        {"operacao", "ano", "uf", "dimensao", "metrica", "pagina", "por_pagina"},
    )
    year = _validate_year(query.get("ano"))
    state = _validate_state(query.get("uf"))
    dimension = query.get("dimensao")
    if not isinstance(dimension, str) or dimension not in ANALYTIC_DIMENSIONS:
        raise QueryValidationError("Dimensão inválida.")
    metric = query.get("metrica", "acidentes")
    if not isinstance(metric, str) or metric not in DISTRIBUTION_METRICS:
        raise QueryValidationError("Métrica inválida para a distribuição solicitada.")
    page = _validate_positive_integer(query.get("pagina"), "pagina", 1)
    page_size = _validate_positive_integer(query.get("por_pagina"), "por_pagina", 10, 100)
    if distribution_loader is None:
        raise QueryDataError("Dados das distribuições não foram disponibilizados.")

    raw_rows = distribution_loader(year, state, dimension)
    if not isinstance(raw_rows, list):
        raise QueryDataError("Distribuição preparada está ausente ou inválida.")

    rows = []
    for item in raw_rows:
        if not isinstance(item, Mapping):
            raise QueryDataError("Distribuição preparada contém uma linha inválida.")
        label = item.get("valor")
        if not isinstance(label, str):
            raise QueryDataError("Distribuição preparada contém uma categoria inválida.")
        values = {}
        for field in ANALYTIC_METRICS:
            value = item.get(field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise QueryDataError("Distribuição preparada contém uma métrica inválida.")
            response_field = "mortes" if field == "mortos" else field
            values[response_field] = value
        rows.append({"valor": label, **values})

    rows.sort(
        key=lambda row: (-cast(int, row[metric]), cast(str, row["valor"]).casefold())
    )
    total_records = sum(cast(int, row["acidentes"]) for row in rows)
    total_categories = len(rows)
    total_pages = math.ceil(total_categories / page_size) if total_categories else 0
    if total_pages and page > total_pages:
        raise QueryValidationError(f"'pagina' deve estar entre 1 e {total_pages}.")
    start = (page - 1) * page_size

    return {
        "filtros": {
            "ano": year,
            "uf": state,
            "dimensao": dimension,
            "metrica": metric,
        },
        "pagina": page,
        "por_pagina": page_size,
        "total_registros": total_records,
        "total_categorias": total_categories,
        "total_paginas": total_pages,
        "resultado": rows[start:start + page_size],
    }


def _validate_positive_integer(
    value: object,
    field: str,
    default: int,
    maximum: int | None = None,
) -> int:
    if value is None:
        return default
    if isinstance(value, bool):
        raise QueryValidationError(f"'{field}' deve ser um inteiro positivo.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.isdigit():
        number = int(value)
    else:
        raise QueryValidationError(f"'{field}' deve ser um inteiro positivo.")
    if number < 1:
        raise QueryValidationError(f"'{field}' deve ser um inteiro positivo.")
    if maximum is not None and number > maximum:
        raise QueryValidationError(f"'{field}' deve estar entre 1 e {maximum}.")
    return number


def _consultar_resumo(
    summaries: Mapping[str, object], query: Mapping[str, object]
) -> dict[str, object]:
    _check_fields(query, {"operacao", "ano", "uf", "metrica"})
    year = _validate_year(query.get("ano"))
    state = _validate_state(query.get("uf"))
    metric = query.get("metrica")
    selected_metrics = list(METRICS) if metric is None else [_require_metric(metric)]

    stats = _get_section(summaries, year, state, "stats_gerais")
    values = {}
    for selected_metric in selected_metrics:
        data_key = METRICS[selected_metric]
        value = stats.get(data_key)
        if not isinstance(value, int):
            raise QueryDataError(f"Dado preparado ausente para a métrica '{selected_metric}'.")
        values[selected_metric] = value

    return {
        "filtros": {"ano": year, "uf": state},
        "resultado": values,
    }


def _comparar_estados(
    summaries: Mapping[str, object], query: Mapping[str, object]
) -> dict[str, object]:
    _check_fields(query, {"operacao", "ano", "ufs", "metrica"})
    year = _validate_year(query.get("ano"))
    metric = _require_metric(query.get("metrica"))
    states_value = query.get("ufs")
    if not isinstance(states_value, list) or not 2 <= len(states_value) <= 10:
        raise QueryValidationError("Informe de 2 a 10 UFs em 'ufs'.")

    states = []
    for state_value in states_value:
        state = _validate_state(state_value)
        if state is None:
            raise QueryValidationError("As UFs devem ser válidas e não podem se repetir.")
        if state in states:
            raise QueryValidationError("As UFs devem ser válidas e não podem se repetir.")
        states.append(state)

    data_key = METRICS[metric]
    comparisons = []
    for state in states:
        stats = _get_section(summaries, year, state, "stats_gerais")
        value = stats.get(data_key)
        if not isinstance(value, int):
            raise QueryDataError(f"Dado preparado ausente para a UF '{state}'.")
        comparisons.append({"uf": state, "valor": value})

    return {
        "filtros": {"ano": year, "ufs": states, "metrica": metric},
        "resultado": comparisons,
    }


def _listar_causas(
    summaries: Mapping[str, object], query: Mapping[str, object]
) -> dict[str, object]:
    _check_fields(query, {"operacao", "ano", "uf", "limite"})
    year = _validate_year(query.get("ano"))
    state = _validate_state(query.get("uf"))
    limit = query.get("limite", 5)
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
        raise QueryValidationError("'limite' deve ser um inteiro entre 1 e 10.")

    causes = _get_section(summaries, year, state, "causas")
    labels = causes.get("labels")
    accidents = causes.get("data")
    deaths = causes.get("mortos")
    injuries = causes.get("feridos")
    severity = causes.get("taxa_severidade")
    if not all(isinstance(values, list) for values in (labels, accidents, deaths, injuries, severity)):
        raise QueryDataError("Dados preparados de causas estão incompletos.")

    rows = []
    for index, label in enumerate(labels[:limit]):
        if (
            not isinstance(label, str)
            or index >= len(accidents)
            or index >= len(deaths)
            or index >= len(injuries)
            or index >= len(severity)
        ):
            raise QueryDataError("Dados preparados de causas estão inconsistentes.")
        values = (accidents[index], deaths[index], injuries[index], severity[index])
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise QueryDataError("Dados preparados de causas estão inconsistentes.")
        rows.append({
            "causa": label,
            "acidentes": accidents[index],
            "mortes": deaths[index],
            "feridos": injuries[index],
            "taxa_severidade": severity[index],
        })

    return {
        "filtros": {"ano": year, "uf": state, "limite": limit},
        "resultado": rows,
    }


def _consultar_serie(
    summaries: Mapping[str, object], query: Mapping[str, object]
) -> dict[str, object]:
    _check_fields(query, {"operacao", "uf", "metrica", "ano_inicio", "ano_fim"})
    state = _validate_state(query.get("uf"))
    metric = _require_metric(query.get("metrica"))
    start = _validate_year(query.get("ano_inicio", 2017), "ano_inicio")
    end = _validate_year(query.get("ano_fim", 2024), "ano_fim")
    if start is None or end is None or start > end:
        raise QueryValidationError("'ano_inicio' deve ser menor ou igual a 'ano_fim'.")

    series_by_metric = _get_section(summaries, None, state, "series_por_ano")
    series = series_by_metric.get(metric)
    if not isinstance(series, Mapping):
        raise QueryDataError(f"Série preparada ausente para a métrica '{metric}'.")
    labels = series.get("labels")
    values = series.get("data")
    if not isinstance(labels, list) or not isinstance(values, list) or len(labels) != len(values):
        raise QueryDataError("Série preparada está incompleta.")

    points = []
    for year, value in zip(labels, values):
        if isinstance(year, bool) or not isinstance(year, int):
            raise QueryDataError("Série preparada contém um ano inválido.")
        if isinstance(value, bool) or not isinstance(value, int):
            raise QueryDataError("Série preparada contém um valor inválido.")
        if start <= year <= end:
            points.append({"ano": year, "valor": value})

    return {
        "filtros": {"uf": state, "metrica": metric, "ano_inicio": start, "ano_fim": end},
        "resultado": points,
    }


def _check_fields(query: Mapping[str, object], allowed: set[str]) -> None:
    unexpected = set(query) - allowed
    if unexpected:
        fields = ", ".join(sorted(unexpected))
        raise QueryValidationError(f"Campo(s) não suportado(s): {fields}.")


def _validate_year(value: object, field: str = "ano") -> int | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise QueryValidationError(f"'{field}' deve ser um ano entre 2017 e 2024.")
    if isinstance(value, int):
        year = value
    elif isinstance(value, str) and value in YEAR_STRINGS:
        year = int(value)
    else:
        raise QueryValidationError(f"'{field}' deve ser um ano entre 2017 e 2024.")
    if year not in YEARS:
        raise QueryValidationError(f"'{field}' deve ser um ano entre 2017 e 2024.")
    return year


def _validate_state(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or value.upper() not in STATES:
        raise QueryValidationError("UF inválida.")
    return value.upper()


def _require_metric(value: object) -> str:
    if not isinstance(value, str) or value not in METRICS:
        raise QueryValidationError("Métrica inválida. Use acidentes, mortes ou feridos.")
    return value


def _get_section(
    summaries: Mapping[str, object],
    year: int | None,
    state: str | None,
    section: str,
) -> Mapping[str, object]:
    parts = []
    if year is not None:
        parts.append(f"year_{year}")
    if state is not None:
        parts.append(f"uf_{state}")
    key = "_".join(parts) or "all"
    entry = summaries.get(key)
    if not isinstance(entry, Mapping):
        raise QueryDataError("Dados preparados indisponíveis para os filtros solicitados.")
    section_value = entry.get(section)
    if not isinstance(section_value, Mapping) or not section_value:
        raise QueryDataError("Dados preparados indisponíveis para os filtros solicitados.")
    return cast(Mapping[str, object], section_value)


def _as_mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise QueryValidationError(message)
    return cast(Mapping[str, object], value)
