import re
import uuid
from dataclasses import dataclass
from typing import Any

import polars as pl

from .naming import PATTERNS
from .schemas import SCHEMAS, WORKSHEETS
from .time import parse_utc


@dataclass(frozen=True)
class ValidationIssue:
    sheet: str
    row: int
    column: str
    value: Any
    rule: str

    def __str__(self) -> str:
        return f"{self.sheet}, row {self.row}, {self.column}: {self.value!r}; expected {self.rule}"


def _valid_uuid(value: Any) -> bool:
    try:
        return str(uuid.UUID(str(value))) == str(value).lower()
    except (ValueError, TypeError, AttributeError):
        return False


def _issues_for_frame(sheet: str, df: pl.DataFrame) -> list[ValidationIssue]:
    issues = []
    schema = SCHEMAS[sheet]
    for offset, row in enumerate(df.iter_rows(named=True), 2):
        for name, field in schema.items():
            value = row.get(name)
            if field.required and value is None:
                issues.append(ValidationIssue(sheet, offset, name, value, "a non-empty value"))
                continue
            if value is None:
                continue
            if name == "id" and not _valid_uuid(value):
                issues.append(ValidationIssue(sheet, offset, name, value, "a canonical UUID"))
            elif field.choices and str(value) not in field.choices:
                issues.append(ValidationIssue(sheet, offset, name, value, f"one of {', '.join(field.choices)}"))
            elif field.minimum is not None and value < field.minimum:
                issues.append(ValidationIssue(sheet, offset, name, value, f">= {field.minimum}"))
            elif field.maximum is not None and value > field.maximum:
                issues.append(ValidationIssue(sheet, offset, name, value, f"<= {field.maximum}"))
            elif name in ("created_at", "updated_at", "archived_at"):
                try:
                    parse_utc(str(value))
                except ValueError:
                    issues.append(ValidationIssue(sheet, offset, name, value, "an ISO 8601 UTC timestamp"))
        if sheet == "apiaries" and row.get("name") is not None:
            name = row["name"]
            if name != name.strip() or not name.strip() or len(name) > 20:
                issues.append(ValidationIssue(sheet, offset, "name", name, "trimmed text of 1–20 characters"))
        code_field = "code" if sheet == "equipment" else "name"
        kind = {"boxes": "box", "frames": "frame", "equipment": "equipment"}.get(sheet)
        if kind and row.get(code_field) is not None and not PATTERNS[kind].fullmatch(row[code_field]):
            issues.append(ValidationIssue(sheet, offset, code_field, row[code_field], PATTERNS[kind].pattern))
    return issues


def validate_workbook(data: dict[str, pl.DataFrame]) -> list[ValidationIssue]:
    issues = []
    for sheet in WORKSHEETS:
        if sheet not in data:
            issues.append(ValidationIssue(sheet, 1, "worksheet", None, "required worksheet"))
            continue
        issues.extend(_issues_for_frame(sheet, data[sheet]))

    active_values: dict[tuple[str, str | None, str], tuple[str, int]] = {}
    for sheet, column in (("apiaries", "name"), ("hives", "name"), ("boxes", "name"), ("frames", "name"), ("equipment", "code")):
        if sheet not in data:
            continue
        for offset, row in enumerate(data[sheet].iter_rows(named=True), 2):
            value = row.get(column)
            if row.get("is_archived") or value is None:
                continue
            parent_column = {"hives": "parent_apiary_id", "boxes": "parent_hive_id", "frames": "parent_box_id"}.get(sheet)
            key = (sheet, str(row.get(parent_column)) if parent_column else None, str(value).casefold())
            if key in active_values:
                issues.append(ValidationIssue(sheet, offset, column, value, "a unique active name or code in its destination scope"))
            else:
                active_values[key] = (sheet, offset)

    for child, parent, column in (
        ("hives", "apiaries", "parent_apiary_id"), ("boxes", "hives", "parent_hive_id"),
        ("frames", "boxes", "parent_box_id"), ("equipment", "equipment_types", "equipment_type_id"),
        ("measurements", "frames", "parent_frame_id"),
    ):
        if child not in data or parent not in data:
            continue
        parent_ids = set(data[parent]["id"].to_list())
        for offset, value in enumerate(data[child][column].to_list(), 2):
            if value is not None and value not in parent_ids:
                issues.append(ValidationIssue(child, offset, column, value, f"an existing {parent} id"))

    if "equipment" in data and "hives" in data:
        hive_ids = set(data["hives"]["id"].to_list())
        for offset, value in enumerate(data["equipment"]["parent_hive_id"].to_list(), 2):
            if value is not None and value not in hive_ids:
                issues.append(ValidationIssue("equipment", offset, "parent_hive_id", value, "an existing hive id or Archived"))
        active_hives = set(data["hives"].filter(~pl.col("is_archived"))["id"].to_list())
        for offset, row in enumerate(data["equipment"].iter_rows(named=True), 2):
            if not row["is_archived"] and row["parent_hive_id"] not in active_hives:
                issues.append(ValidationIssue("equipment", offset, "parent_hive_id", row["parent_hive_id"], "an active hive for active equipment"))

    if "hives" in data and "apiaries" in data:
        apiaries = {row["id"]: row for row in data["apiaries"].iter_rows(named=True)}
        for offset, row in enumerate(data["hives"].iter_rows(named=True), 2):
            parent = apiaries.get(row["parent_apiary_id"])
            if parent and not (1 <= row["grid_column"] <= parent["grid_columns"] and 1 <= row["grid_row"] <= parent["grid_rows"]):
                issues.append(ValidationIssue("hives", offset, "grid_column/grid_row", (row["grid_column"], row["grid_row"]), "a cell inside the parent apiary grid"))
        occupied = data["hives"].filter(~pl.col("is_archived")).group_by("parent_apiary_id", "grid_column", "grid_row").len().filter(pl.col("len") > 1)
        for row in occupied.iter_rows(named=True):
            issues.append(ValidationIssue("hives", 0, "grid_column/grid_row", (row["grid_column"], row["grid_row"]), "one active hive per apiary grid cell"))

    if "notes" in data:
        targets = {
            target_type: set(data[sheet]["id"].to_list())
            for target_type, sheet in (
                ("apiary", "apiaries"), ("hive", "hives"), ("box", "boxes"),
                ("frame", "frames"), ("equipment", "equipment"),
            )
            if sheet in data
        }
        for offset, row in enumerate(data["notes"].iter_rows(named=True), 2):
            if not row.get("archived") and row.get("target_id") not in targets.get(row.get("target_type"), set()):
                issues.append(ValidationIssue("notes", offset, "target_id", row.get("target_id"), "an existing target id of target_type"))

    for sheet, parent_col in (("boxes", "parent_hive_id"), ("frames", "parent_box_id")):
        if sheet not in data:
            continue
        active = data[sheet].filter(~pl.col("is_archived"))
        duplicates = active.group_by(parent_col, "position").len().filter(pl.col("len") > 1)
        for row in duplicates.iter_rows(named=True):
            issues.append(ValidationIssue(sheet, 0, "position", row["position"], f"a unique active position within {parent_col}"))

    if "metadata" in data:
        values = dict(zip(data["metadata"]["key"].to_list(), data["metadata"]["value"].to_list()))
        for key in ("application_name", "schema_version", "initialized_at"):
            if not values.get(key):
                issues.append(ValidationIssue("metadata", 0, "key", key, "required metadata key with a value"))
    return issues


def validate_record(sheet: str, values: dict[str, Any]) -> list[ValidationIssue]:
    try:
        df = pl.DataFrame([values], schema={name: field.dtype for name, field in SCHEMAS[sheet].items()}, strict=True)
    except (TypeError, ValueError) as error:
        return [ValidationIssue(sheet, 2, "record", values, str(error))]
    return _issues_for_frame(sheet, df)
