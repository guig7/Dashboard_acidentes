"""Validated, deterministic queries over the dashboard's prepared summaries."""

from collections.abc import Mapping
from typing import cast

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
}
SOURCE = "Dados PRF pré-processados do painel (2017–2024)."


class QueryValidationError(ValueError):
    """Raised when a query does not follow the supported operation contract."""


class QueryDataError(ValueError):
    """Raised when prepared data needed by a valid query is unavailable."""


def execute_query(
    summaries: Mapping[str, object], payload: object
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
    handler = handlers.get(operation)
    if handler is None:
        raise QueryValidationError("Operação não suportada.")

    result = handler(summaries, query)
    return {
        "operacao": operation,
        "fonte": SOURCE,
        **result,
    }


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
    if metric == "feridos":
        raise QueryValidationError("Séries anuais de feridos não estão disponíveis nos dados preparados.")

    start = _validate_year(query.get("ano_inicio", 2017), "ano_inicio")
    end = _validate_year(query.get("ano_fim", 2024), "ano_fim")
    if start is None or end is None or start > end:
        raise QueryValidationError("'ano_inicio' deve ser menor ou igual a 'ano_fim'.")

    section_name = "acidentes_por_ano" if metric == "acidentes" else "mortos_por_ano"
    series = _get_section(summaries, None, state, section_name)
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
