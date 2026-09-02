"""Transactional hierarchy operations.

Every public function returns a new workbook and leaves its input untouched when
validation fails.  UI code can translate the changed rows into one Sheets
mutation only after these functions succeed.
"""

from copy import deepcopy

import polars as pl


SHEETS = {"apiary": "apiaries", "hive": "hives", "box": "boxes", "frame": "frames", "equipment": "equipment"}
PARENTS = {
    "hives": ("apiaries", "parent_apiary_id"),
    "boxes": ("hives", "parent_hive_id"),
    "frames": ("boxes", "parent_box_id"),
    "equipment": ("hives", "parent_hive_id"),
    "measurements": ("frames", "parent_frame_id"),
}
CHILDREN = {
    "apiaries": (("hives", "parent_apiary_id"),),
    "hives": (("boxes", "parent_hive_id"), ("equipment", "parent_hive_id")),
    "boxes": (("frames", "parent_box_id"),),
    "frames": (("measurements", "parent_frame_id"),),
}
NAME_FIELDS = {"apiaries": "name", "hives": "name", "boxes": "name", "frames": "name", "equipment": "code"}


def _rows(data):
    return {sheet: df.to_dicts() for sheet, df in data.items()}


def _frames(data, rows):
    return {sheet: pl.DataFrame(rows[sheet], schema=df.schema, strict=False) for sheet, df in data.items()}


def _find(rows, sheet, record_id):
    return next((row for row in rows[sheet] if row["id"] == record_id), None)


def _descendants(rows, sheet, record_id):
    found = [(sheet, record_id)]
    for child_sheet, parent_column in CHILDREN.get(sheet, ()):
        for child in rows[child_sheet]:
            if child[parent_column] == record_id:
                found.extend(_descendants(rows, child_sheet, child["id"]))
    return found


def _active_parent(rows, sheet, parent_id):
    parent_sheet, _ = PARENTS[sheet]
    parent = _find(rows, parent_sheet, parent_id)
    if not parent or parent["is_archived"]:
        return False
    if parent_sheet in PARENTS:
        _, parent_column = PARENTS[parent_sheet]
        return _active_parent(rows, parent_sheet, parent[parent_column])
    return True


def _scope_key(sheet, row):
    return row[PARENTS[sheet][1]] if sheet in PARENTS and sheet != "equipment" else None


def _validate_unique(rows, sheet, record):
    field = NAME_FIELDS.get(sheet)
    if not field or record.get("is_archived"):
        return
    value = str(record[field]).casefold()
    scope = _scope_key(sheet, record)
    for other in rows[sheet]:
        if other["id"] == record["id"] or other["is_archived"]:
            continue
        if _scope_key(sheet, other) == scope and str(other[field]).casefold() == value:
            raise ValueError(f"{record[field]} is already used in the destination.")


def archive_entity(data, sheet, record_id):
    """Recursively archive one entity without mutating ``data``."""
    rows = _rows(data)
    if not _find(rows, sheet, record_id):
        raise ValueError("The selected record no longer exists.")
    for child_sheet, child_id in _descendants(rows, sheet, record_id):
        _find(rows, child_sheet, child_id)["is_archived"] = True
    return _frames(data, rows)


def edit_entity(data, sheet, record_id, values):
    """Edit the captured immutable ID and validate before returning a copy."""
    rows = _rows(data)
    record = _find(rows, sheet, record_id)
    if not record:
        raise ValueError("The record opened for editing no longer exists.")
    candidate = {**record, **deepcopy(values), "id": record_id}
    if sheet == "hives" and not candidate["is_archived"]:
        for other in rows["hives"]:
            if other["id"] != record_id and not other["is_archived"] and other["parent_apiary_id"] == candidate["parent_apiary_id"] and (other["grid_column"], other["grid_row"]) == (candidate["grid_column"], candidate["grid_row"]):
                raise ValueError("That apiary grid cell already contains a hive.")
    _validate_unique(rows, sheet, candidate)
    record.update(candidate)
    return _frames(data, rows)


def move_entities(data, sheet, ids, destination_id, position=0):
    """Atomically move boxes, frames, or equipment; archived is a destination."""
    if sheet not in ("boxes", "frames", "equipment"):
        raise ValueError("Only boxes, frames, and equipment can be moved.")
    rows = _rows(data)
    moving = [_find(rows, sheet, record_id) for record_id in ids]
    if not ids or any(row is None for row in moving) or len(set(ids)) != len(ids):
        raise ValueError("Select one or more valid records to move.")
    parent_sheet, parent_column = PARENTS[sheet]
    if destination_id is not None and not _active_parent(rows, sheet, destination_id):
        raise ValueError(f"Choose an active {parent_sheet[:-1]} destination.")
    if sheet == "equipment":
        for row in moving:
            row[parent_column] = destination_id
            row["is_archived"] = destination_id is None
            if not row["is_archived"]:
                _validate_unique(rows, sheet, row)
        return _frames(data, rows)

    moving.sort(key=lambda row: (row[parent_column] or "", row["position"]))
    old_parents = {row[parent_column] for row in moving}
    for row in moving:
        row[parent_column] = destination_id
        row["is_archived"] = destination_id is None
        for child_sheet, child_id in _descendants(rows, sheet, row["id"]):
            _find(rows, child_sheet, child_id)["is_archived"] = destination_id is None
        if destination_id is not None:
            _validate_unique(rows, sheet, row)
    for parent_id in old_parents - {destination_id}:
        siblings = sorted((row for row in rows[sheet] if row[parent_column] == parent_id and not row["is_archived"]), key=lambda row: row["position"])
        for index, row in enumerate(siblings):
            row["position"] = index
    if destination_id is not None:
        target = sorted((row for row in rows[sheet] if row[parent_column] == destination_id and row not in moving and not row["is_archived"]), key=lambda row: row["position"])
        insertion = min(max(int(position), 0), len(target))
        ordered = target[:insertion] + moving + target[insertion:]
        for index, row in enumerate(ordered):
            row["position"] = index
    return _frames(data, rows)


def move_hives(data, ids, destination_id, grid_column=1, grid_row=1):
    """Move one or more hives to an apiary, filling grid cells left-to-right."""
    rows = _rows(data)
    moving = [_find(rows, "hives", record_id) for record_id in ids]
    if not ids or any(row is None for row in moving) or len(set(ids)) != len(ids):
        raise ValueError("Select one or more valid hives to move.")
    if destination_id is None:
        for hive in moving:
            for child_sheet, child_id in _descendants(rows, "hives", hive["id"]):
                _find(rows, child_sheet, child_id)["is_archived"] = True
        return _frames(data, rows)

    apiary = _find(rows, "apiaries", destination_id)
    if not apiary or apiary["is_archived"]:
        raise ValueError("Choose an active apiary destination.")
    start = (int(grid_row) - 1) * apiary["grid_columns"] + int(grid_column) - 1
    cells = [
        (index % apiary["grid_columns"] + 1, index // apiary["grid_columns"] + 1)
        for index in range(start, apiary["grid_columns"] * apiary["grid_rows"])
    ]
    moving_ids = set(ids)
    occupied = {
        (row["grid_column"], row["grid_row"])
        for row in rows["hives"]
        if row["id"] not in moving_ids and not row["is_archived"] and row["parent_apiary_id"] == destination_id
    }
    available = [cell for cell in cells if cell not in occupied]
    if len(available) < len(moving):
        raise ValueError("There are not enough empty grid cells from that starting position.")
    for hive, (column, row) in zip(moving, available):
        hive.update(parent_apiary_id=destination_id, grid_column=column, grid_row=row, is_archived=False)
        for child_sheet, child_id in _descendants(rows, "hives", hive["id"]):
            _find(rows, child_sheet, child_id)["is_archived"] = False
        _validate_unique(rows, "hives", hive)
    return _frames(data, rows)


def repair_legacy_integrity(data, now):
    """Preserve orphaned notes and normalize duplicate hierarchy positions."""
    rows = _rows(data)
    targets = {
        level: {row["id"] for row in rows[sheet]}
        for level, sheet in SHEETS.items()
    }
    for note in rows["notes"]:
        if note["target_id"] not in targets.get(note["target_type"], set()):
            note.update(archived=True, archived_at=note.get("archived_at") or now)
    for sheet, parent_column in (("boxes", "parent_hive_id"), ("frames", "parent_box_id")):
        parents = {row[parent_column] for row in rows[sheet] if not row["is_archived"]}
        for parent_id in parents:
            siblings = sorted(
                (row for row in rows[sheet] if row[parent_column] == parent_id and not row["is_archived"]),
                key=lambda row: (row["position"], row["created_at"], row["id"]),
            )
            for position, row in enumerate(siblings):
                row["position"] = position
    return _frames(data, rows)


def changed_rows(before, after):
    """Return mutation rows for a transactional workbook result."""
    changes = []
    for sheet, frame in before.items():
        if "id" not in frame.columns:
            continue
        old = {row["id"]: row for row in frame.to_dicts()}
        for row in after[sheet].to_dicts():
            if row["id"] in old:
                values = {key: value for key, value in row.items() if key != "id" and value != old[row["id"]].get(key)}
                if values:
                    changes.append({"sheet": sheet, "id": row["id"], "values": values})
    return changes
