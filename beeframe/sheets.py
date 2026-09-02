from typing import Any

import polars as pl

from .schemas import SCHEMAS, columns, empty_frame


def matrix_to_frame(sheet: str, matrix: list[list[Any]]) -> pl.DataFrame:
    if not matrix:
        return empty_frame(sheet)
    headers = [str(value).strip() for value in matrix[0]]
    if len(headers) != len(set(headers)):
        raise ValueError(f"{sheet}: worksheet headers must be unique")
    width = len(headers)
    rows = [list(row) + [None] * (width - len(row)) for row in matrix[1:]]
    rows = [[None if value == "" else value for value in row[:width]] for row in rows]
    raw = pl.DataFrame(rows, schema=headers, orient="row", infer_schema_length=None) if rows else pl.DataFrame(schema=headers)
    required = set(columns(sheet))
    missing = required - set(headers)
    if missing:
        raise ValueError(f"{sheet}: missing required column(s): {', '.join(sorted(missing))}")
    expressions = []
    for name, field in SCHEMAS[sheet].items():
        expressions.append(pl.col(name).cast(field.dtype, strict=True).alias(name))
    return raw.with_columns(expressions)


def frame_to_matrix(df: pl.DataFrame) -> list[list[Any]]:
    return [df.columns, *[list(row) for row in df.rows()]]


def recognized_update(sheet: str, refreshed_matrix: list[list[Any]], record_id: str, values: dict[str, Any]) -> tuple[int, list[str], list[Any]]:
    headers = [str(value) for value in refreshed_matrix[0]]
    try:
        id_index = headers.index("id")
        row_index = next(index for index, row in enumerate(refreshed_matrix[1:], 2) if len(row) > id_index and row[id_index] == record_id)
    except (ValueError, StopIteration) as error:
        raise ValueError(f"{sheet}: record {record_id} no longer exists") from error
    allowed = SCHEMAS[sheet]
    update_headers = [header for header in headers if header in allowed and header in values]
    return row_index, update_headers, [values[header] for header in update_headers]
