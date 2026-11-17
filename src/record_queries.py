"""Validated pagination over the prepared full-record JSON assets."""

from datetime import datetime
import math
import re
import unicodedata
from collections.abc import Callable, Mapping
from typing import cast

from analyst_queries import STATES, YEARS
from data_schema import (
    RECORD_COLUMNS,
    RECORD_FILTER_FIELDS,
    RECORD_FLOAT_FIELDS,
    RECORD_GROUPABLE_FIELDS,
    RECORD_INTEGER_FIELDS,
    RECORD_OUTPUT_FIELDS,
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MAX_ANALYSIS_SCAN_RECORDS = 40_000
MAX_ANALYSIS_FILTERS = 10
MAX_ANALYSIS_RESULTS = 10
DEFAULT_ANALYSIS_LIMIT = 5
_PARTITION_PATH = re.compile(r"year_(?:20(?:1[7-9]|2[0-4])|unknown)/uf_(?:[A-Z]{2}|unknown)\Z")
_SHORT_YEAR_DATE = re.compile(r"\d{1,2}/\d{1,2}/\d{2}\Z")
_ANALYSIS_METRIC_FIELDS = {
    "acidentes": None,
    "mortes": "mortos",
    "feridos": "feridos",
    "feridos_leves": "feridos_leves",
    "feridos_graves": "feridos_graves",
    "pessoas": "pessoas",
    "ilesos": "ilesos",
    "ignorados": "ignorados",
    "veiculos": "veiculos",
}
_DEFAULT_SAMPLE_FIELDS = (
    "id",
    "data_inversa",
    "horario",
    "uf",
    "br",
    "km",
    "municipio",
    "causa_acidente",
    "tipo_acidente",
    "classificacao_acidente",
    "condicao_metereologica",
    "mortos",
    "feridos",
)


class RecordValidationError(ValueError):
    """Raised when a record query contains an unsupported filter or page."""


class RecordScopeError(RecordValidationError):
    """Raised when a record analysis would scan too many prepared rows."""


class RecordDataError(ValueError):
    """Raised when the prepared record manifest or a shard is inconsistent."""


def query_records(
    manifest: Mapping[str, object],
    year_value: object,
    state_value: object,
    page_value: object,
    page_size_value: object,
    load_chunk: Callable[[str], object],
) -> dict[str, object]:
    year = _validate_year(year_value)
    state = _validate_state(state_value)
    page = _validate_integer(page_value, "pagina", 1, None, 1)
    page_size = _validate_integer(
        page_size_value, "por_pagina", 1, MAX_PAGE_SIZE, DEFAULT_PAGE_SIZE
    )
    if not isinstance(manifest, Mapping):
        raise RecordDataError("O manifesto de registros está ausente ou inválido.")
    columns, chunk_size, partitions, declared_total = _validate_manifest(manifest)

    selected = []
    total = 0
    for partition in partitions:
        partition_year = partition["ano"]
        partition_state = partition["uf"]
        if year is not None and partition_year != year:
            continue
        if state is not None and partition_state != state:
            continue
        selected.append(partition)
        total += partition["quantidade"]

    if sum(partition["quantidade"] for partition in partitions) != declared_total:
        raise RecordDataError("O total declarado no manifesto de registros está inconsistente.")

    total_pages = math.ceil(total / page_size) if total else 0
    if total_pages and page > total_pages:
        raise RecordValidationError(f"'pagina' deve estar entre 1 e {total_pages}.")

    offset = (page - 1) * page_size
    records = []
    for partition in selected:
        count = partition["quantidade"]
        if offset >= count:
            offset -= count
            continue

        local_offset = offset
        offset = 0
        while local_offset < count and len(records) < page_size:
            chunk_index = local_offset // chunk_size
            if chunk_index >= partition["blocos"]:
                raise RecordDataError("O manifesto aponta para um bloco de registros ausente.")
            path = f"{partition['caminho']}/part_{chunk_index:04d}.json"
            rows = _validate_chunk(load_chunk(path), columns, chunk_size)
            expected_rows = min(chunk_size, count - chunk_index * chunk_size)
            if len(rows) != expected_rows:
                raise RecordDataError("O bloco de registros não corresponde ao manifesto.")
            row_offset = local_offset % chunk_size
            available = min(len(rows) - row_offset, count - local_offset)
            if available <= 0:
                raise RecordDataError("Um bloco de registros não contém as linhas esperadas.")
            take = min(available, page_size - len(records))
            records.extend(
                dict(zip(columns, row, strict=True))
                for row in rows[row_offset:row_offset + take]
            )
            local_offset += take

    if len(records) != min(page_size, max(total - (page - 1) * page_size, 0)):
        raise RecordDataError("Não foi possível montar a página completa de registros.")

    return {
        "filtros": {"ano": year, "uf": state},
        "pagina": page,
        "por_pagina": page_size,
        "total_registros": total,
        "total_paginas": total_pages,
        "registros": records,
    }


def analyze_records(
    manifest: Mapping[str, object],
    payload: object,
    load_chunk: Callable[[str], object],
) -> dict[str, object]:
    query = _as_mapping(payload, "A consulta de registros deve ser um objeto JSON.")
    _check_query_fields(
        query,
        {
            "operacao", "ano", "uf", "filtros", "data_inicio", "data_fim",
            "km_min", "km_max", "agrupar_por", "metrica", "limite", "campos",
        },
    )
    year = _validate_year(query.get("ano"))
    state = _validate_state(query.get("uf"))
    filters = _validate_record_filters(query.get("filtros", {}))
    start_date = _validate_date(query.get("data_inicio"), "data_inicio")
    end_date = _validate_date(query.get("data_fim"), "data_fim")
    if start_date is not None and end_date is not None and start_date > end_date:
        raise RecordValidationError("'data_inicio' deve ser anterior a 'data_fim'.")
    km_min = _validate_number(query.get("km_min"), "km_min")
    km_max = _validate_number(query.get("km_max"), "km_max")
    if km_min is not None and km_max is not None and km_min > km_max:
        raise RecordValidationError("'km_min' deve ser menor ou igual a 'km_max'.")

    exact_date = filters.get("data_inversa")
    if year is None and isinstance(exact_date, str):
        parsed_date = _parse_date(exact_date)
        if parsed_date is not None:
            year = parsed_date.year if parsed_date.year in YEARS else None
    if year is None and start_date is not None and end_date is not None:
        if start_date.year == end_date.year and start_date.year in YEARS:
            year = start_date.year

    if year is None and state is None:
        raise RecordScopeError(
            "Para buscar registros individuais, informe um ano ou uma UF."
        )

    group_by_value = query.get("agrupar_por")
    if group_by_value is not None and (
        not isinstance(group_by_value, str)
        or group_by_value not in RECORD_GROUPABLE_FIELDS
    ):
        raise RecordValidationError("'agrupar_por' contém um campo não suportado.")
    group_by = cast(str | None, group_by_value)

    metric = query.get("metrica", "acidentes")
    if not isinstance(metric, str) or metric not in _ANALYSIS_METRIC_FIELDS:
        raise RecordValidationError("Métrica inválida para a análise dos registros.")
    limit = _validate_integer(
        query.get("limite"),
        "limite",
        1,
        MAX_ANALYSIS_RESULTS,
        DEFAULT_ANALYSIS_LIMIT,
    )
    fields = _validate_output_fields(query.get("campos"), group_by)

    columns, chunk_size, partitions, declared_total = _validate_manifest(manifest)
    if not set(RECORD_COLUMNS).issubset(columns):
        raise RecordDataError("O manifesto não contém todos os campos da base.")
    if sum(partition["quantidade"] for partition in partitions) != declared_total:
        raise RecordDataError("O total declarado no manifesto de registros está inconsistente.")

    selected = [
        partition for partition in partitions
        if (year is None or partition["ano"] == year)
        and (state is None or partition["uf"] == state)
    ]
    scan_count = sum(partition["quantidade"] for partition in selected)
    if scan_count > MAX_ANALYSIS_SCAN_RECORDS:
        raise RecordScopeError(
            "A busca detalhada ultrapassa o limite de registros por consulta. "
            "Informe um ano e uma UF mais específicos."
        )

    totals = _empty_metrics()
    matched_count = 0
    groups: dict[tuple[str, object], dict[str, object]] = {}
    samples = []
    for partition in selected:
        count = partition["quantidade"]
        for chunk_index in range(partition["blocos"]):
            path = f"{partition['caminho']}/part_{chunk_index:04d}.json"
            rows = _validate_chunk(load_chunk(path), columns, chunk_size)
            expected_rows = min(chunk_size, count - chunk_index * chunk_size)
            if len(rows) != expected_rows:
                raise RecordDataError("O bloco de registros não corresponde ao manifesto.")
            for row in rows:
                record = dict(zip(columns, row, strict=True))
                if not _matches_record(
                    record,
                    filters,
                    start_date,
                    end_date,
                    km_min,
                    km_max,
                ):
                    continue
                matched_count += 1
                _add_metrics(totals, record)
                if group_by is not None:
                    value = _record_field_value(record, group_by)
                    key = _group_key(value)
                    group = groups.get(key)
                    if group is None:
                        group = {"valor": value if value is not None else "Não informado"}
                        group.update(_empty_metrics())
                        groups[key] = group
                    _add_metrics(group, record)
                elif len(samples) < limit:
                    samples.append({
                        field: _record_field_value(record, field)
                        for field in fields
                    })

    response_filters = {
        "ano": year,
        "uf": state,
        "filtros": dict(filters),
        "data_inicio": query.get("data_inicio"),
        "data_fim": query.get("data_fim"),
        "km_min": km_min,
        "km_max": km_max,
    }
    if group_by is not None:
        ordered_groups = sorted(
            groups.values(),
            key=lambda item: (
                -cast(int, item[metric]),
                _normalize_text(str(item["valor"])),
            ),
        )
        return {
            "filtros": {
                **response_filters,
                "agrupar_por": group_by,
                "metrica": metric,
            },
            "modo": "agrupamento",
            "total_registros": matched_count,
            "total_categorias": len(groups),
            "resultado": ordered_groups[:limit],
        }

    return {
        "filtros": {**response_filters, "campos": list(fields)},
        "modo": "amostra",
        "total_registros": matched_count,
        "resultado": {"totais": totals, "registros": samples},
    }


def _validate_manifest(
    manifest: Mapping[str, object],
) -> tuple[list[str], int, list[dict[str, object]], int]:
    columns = manifest.get("colunas")
    chunk_size = manifest.get("tamanho_bloco")
    partitions_value = manifest.get("particoes")
    total = manifest.get("total_registros")
    if (
        not isinstance(columns, list)
        or not columns
        or any(not isinstance(column, str) for column in columns)
        or len(set(columns)) != len(columns)
        or isinstance(chunk_size, bool)
        or not isinstance(chunk_size, int)
        or chunk_size < 1
        or not isinstance(partitions_value, list)
        or isinstance(total, bool)
        or not isinstance(total, int)
        or total < 0
    ):
        raise RecordDataError("O manifesto de registros está ausente ou inválido.")

    partitions = []
    for value in partitions_value:
        if not isinstance(value, Mapping):
            raise RecordDataError("O manifesto contém uma partição inválida.")
        year = value.get("ano")
        state = value.get("uf")
        count = value.get("quantidade")
        chunks = value.get("blocos")
        path = value.get("caminho")
        if (
            (year is not None and (
                isinstance(year, bool) or not isinstance(year, int) or year not in YEARS
            ))
            or (state is not None and (not isinstance(state, str) or state not in STATES))
            or isinstance(count, bool)
            or not isinstance(count, int)
            or count < 1
            or isinstance(chunks, bool)
            or not isinstance(chunks, int)
            or chunks < 1
            or not isinstance(path, str)
            or not _PARTITION_PATH.fullmatch(path)
        ):
            raise RecordDataError("O manifesto contém metadados de partição inválidos.")
        if chunks != math.ceil(count / chunk_size):
            raise RecordDataError("O número de blocos não corresponde à quantidade de registros.")
        expected_year_dir = f"year_{year}" if year is not None else "year_unknown"
        expected_state_dir = f"uf_{state}" if state is not None else "uf_unknown"
        if path != f"{expected_year_dir}/{expected_state_dir}":
            raise RecordDataError("O caminho de partição não corresponde aos seus filtros.")
        partitions.append({
            "ano": year,
            "uf": state,
            "quantidade": count,
            "blocos": chunks,
            "caminho": path,
        })
    return cast(list[str], columns), chunk_size, partitions, total


def _validate_chunk(
    value: object,
    columns: list[str],
    chunk_size: int,
) -> list[list[object]]:
    if not isinstance(value, Mapping):
        raise RecordDataError("Um bloco de registros está ausente ou inválido.")
    rows = value.get("rows")
    if (
        not isinstance(rows, list)
        or len(rows) > chunk_size
        or any(not isinstance(row, list) or len(row) != len(columns) for row in rows)
    ):
        raise RecordDataError("Um bloco de registros não corresponde ao esquema publicado.")
    return cast(list[list[object]], rows)


def _validate_year(value: object) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise RecordValidationError("'ano' deve ser um ano entre 2017 e 2024.")
    if isinstance(value, int):
        year = value
    elif isinstance(value, str) and value in {str(year) for year in YEARS}:
        year = int(value)
    else:
        raise RecordValidationError("'ano' deve ser um ano entre 2017 e 2024.")
    if year not in YEARS:
        raise RecordValidationError("'ano' deve ser um ano entre 2017 e 2024.")
    return year


def _validate_state(value: object) -> str | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str) or value.upper() not in STATES:
        raise RecordValidationError("UF inválida.")
    return value.upper()


def _validate_integer(
    value: object,
    field: str,
    minimum: int,
    maximum: int | None,
    default: int,
) -> int:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        raise RecordValidationError(f"'{field}' deve ser um inteiro válido.")
    if isinstance(value, int):
        number = value
    elif isinstance(value, str) and value.isdigit():
        number = int(value)
    else:
        raise RecordValidationError(f"'{field}' deve ser um inteiro válido.")
    if number < minimum or (maximum is not None and number > maximum):
        if maximum is None:
            raise RecordValidationError(f"'{field}' deve ser maior ou igual a {minimum}.")
        raise RecordValidationError(f"'{field}' deve estar entre {minimum} e {maximum}.")
    return number


def _as_mapping(value: object, message: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping) or any(not isinstance(key, str) for key in value):
        raise RecordValidationError(message)
    return cast(Mapping[str, object], value)


def _check_query_fields(query: Mapping[str, object], allowed: set[str]) -> None:
    unexpected = set(query) - allowed
    if unexpected:
        fields = ", ".join(sorted(unexpected))
        raise RecordValidationError(f"Campo(s) não suportado(s): {fields}.")


def _validate_record_filters(value: object) -> dict[str, object]:
    filters = _as_mapping(value, "'filtros' deve ser um objeto JSON.")
    if len(filters) > MAX_ANALYSIS_FILTERS:
        raise RecordValidationError(
            f"Informe no máximo {MAX_ANALYSIS_FILTERS} filtros de campos."
        )
    allowed_fields = RECORD_FILTER_FIELDS
    if set(filters) - allowed_fields:
        raise RecordValidationError("Os filtros contêm um campo não suportado.")

    validated = {}
    for field, selected in filters.items():
        if selected is None:
            validated[field] = None
        elif field in RECORD_INTEGER_FIELDS:
            if isinstance(selected, bool) or not isinstance(selected, int):
                raise RecordValidationError(f"'{field}' deve ser um inteiro.")
            validated[field] = selected
        elif field in RECORD_FLOAT_FIELDS:
            if (
                isinstance(selected, bool)
                or not isinstance(selected, (int, float))
                or not math.isfinite(selected)
            ):
                raise RecordValidationError(f"'{field}' deve ser um número finito.")
            validated[field] = float(selected)
        elif isinstance(selected, str):
            validated[field] = selected
        else:
            raise RecordValidationError(f"Filtro inválido para o campo '{field}'.")
    return validated


def _validate_date(value: object, field: str) -> datetime | None:
    if value is None or value == "":
        return None
    if not isinstance(value, str):
        raise RecordValidationError(f"'{field}' deve usar o formato DD/MM/AAAA.")
    parsed = _parse_date(value)
    if parsed is None or parsed.year not in YEARS:
        raise RecordValidationError(f"'{field}' deve ser uma data entre 2017 e 2024.")
    return parsed


def _parse_date(value: str) -> datetime | None:
    date_format = "%m/%d/%y" if _SHORT_YEAR_DATE.fullmatch(value) else "%d/%m/%Y"
    try:
        return datetime.strptime(value, date_format)
    except ValueError:
        return None


def _validate_number(value: object, field: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RecordValidationError(f"'{field}' deve ser um número finito.")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise RecordValidationError(f"'{field}' deve ser um número finito não negativo.")
    return number


def _validate_output_fields(value: object, group_by: str | None) -> tuple[str, ...]:
    if group_by is not None:
        if value is not None:
            raise RecordValidationError("'campos' não pode ser usado com 'agrupar_por'.")
        return ()
    if value is None:
        return _DEFAULT_SAMPLE_FIELDS
    if (
        not isinstance(value, list)
        or not value
        or len(value) > len(RECORD_OUTPUT_FIELDS)
        or any(not isinstance(field, str) or field not in RECORD_OUTPUT_FIELDS for field in value)
        or len(set(value)) != len(value)
    ):
        raise RecordValidationError("'campos' deve conter campos distintos da base.")
    return tuple(value)


def _matches_record(
    record: Mapping[str, object],
    filters: Mapping[str, object],
    start_date: datetime | None,
    end_date: datetime | None,
    km_min: float | None,
    km_max: float | None,
) -> bool:
    for field, expected in filters.items():
        actual = _record_field_value(record, field)
        if field == "data_inversa" and isinstance(expected, str):
            actual_date = _parse_date(actual) if isinstance(actual, str) else None
            expected_date = _parse_date(expected)
            if actual_date is not None and expected_date is not None:
                if actual_date != expected_date:
                    return False
                continue
        if isinstance(expected, str) and isinstance(actual, str):
            if _normalize_filter(field, expected) != _normalize_filter(field, actual):
                return False
        elif isinstance(expected, float) and isinstance(actual, (int, float)):
            if not math.isclose(expected, actual, rel_tol=0, abs_tol=1e-6):
                return False
        elif actual != expected:
            return False

    row_date_text = record.get("data_inversa")
    row_date = _parse_date(row_date_text) if isinstance(row_date_text, str) else None
    if start_date is not None or end_date is not None:
        if row_date is None:
            return False
        if start_date is not None and row_date < start_date:
            return False
        if end_date is not None and row_date > end_date:
            return False

    km = record.get("km")
    if km_min is not None or km_max is not None:
        if isinstance(km, bool) or not isinstance(km, (int, float)):
            return False
        if km_min is not None and km < km_min:
            return False
        if km_max is not None and km > km_max:
            return False
    return True


def _record_field_value(record: Mapping[str, object], field: str) -> object:
    if field == "data_inversa":
        value = record.get(field)
        parsed = _parse_date(value) if isinstance(value, str) else None
        return parsed.strftime("%d/%m/%Y") if parsed is not None else value
    if field == "ano":
        value = record.get("data_inversa")
        parsed = _parse_date(value) if isinstance(value, str) else None
        return str(parsed.year) if parsed is not None else "Não informado"
    if field == "mes":
        value = record.get("data_inversa")
        parsed = _parse_date(value) if isinstance(value, str) else None
        return f"{parsed.month:02d}" if parsed is not None else "Não informado"
    if field == "hora":
        value = record.get("horario")
        if isinstance(value, str) and len(value) >= 2 and value[:2].isdigit():
            hour = int(value[:2])
            if 0 <= hour <= 23:
                return f"{hour:02d}:00"
        return "Não informado"
    return record.get(field)


def _normalize_filter(field: str, value: str) -> str:
    if field == "br":
        digits = "".join(character for character in value if character.isdigit())
        if digits:
            return digits.zfill(3)
    return _normalize_text(value)


def _normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.strip().casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _group_key(value: object) -> tuple[str, object]:
    if value is None:
        return ("none", "")
    if isinstance(value, str):
        return ("str", value)
    return (type(value).__name__, value)


def _empty_metrics() -> dict[str, int]:
    return {metric: 0 for metric in _ANALYSIS_METRIC_FIELDS}


def _add_metrics(totals: dict[str, object], record: Mapping[str, object]) -> None:
    totals["acidentes"] = cast(int, totals["acidentes"]) + 1
    for metric, field in _ANALYSIS_METRIC_FIELDS.items():
        if field is None:
            continue
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise RecordDataError(f"Registro preparado contém uma métrica inválida: '{field}'.")
        totals[metric] = cast(int, totals[metric]) + value
