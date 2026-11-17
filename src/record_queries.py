"""Validated pagination over the prepared full-record JSON assets."""

import math
import re
from collections.abc import Callable, Mapping
from typing import cast

from analyst_queries import STATES, YEARS

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
_PARTITION_PATH = re.compile(r"year_(?:20(?:1[7-9]|2[0-4])|unknown)/uf_(?:[A-Z]{2}|unknown)\Z")


class RecordValidationError(ValueError):
    """Raised when a record query contains an unsupported filter or page."""


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
