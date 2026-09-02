from dataclasses import dataclass
from typing import Any

import polars as pl


@dataclass(frozen=True)
class Field:
    dtype: pl.DataType
    label: str
    required: bool = False
    default: Any = None
    editable: bool = True
    choices: tuple[str, ...] = ()
    minimum: int | None = None
    maximum: int | None = None


TEXT = pl.String
INT = pl.Int64
BOOL = pl.Boolean
BASE = {
    "id": Field(TEXT, "ID", True, editable=False),
    "created_at": Field(TEXT, "Created", True, editable=False),
    "updated_at": Field(TEXT, "Updated", True, editable=False),
    "is_archived": Field(BOOL, "Archived", True, False, editable=False),
}


def entity(*items: tuple[str, Field]) -> dict[str, Field]:
    return {"id": BASE["id"], **dict(items), **{k: BASE[k] for k in ("created_at", "updated_at", "is_archived")}}


SCHEMAS: dict[str, dict[str, Field]] = {
    "metadata": {
        "key": Field(TEXT, "Key", True),
        "value": Field(TEXT, "Value", True),
    },
    "apiaries": entity(
        ("name", Field(TEXT, "Name", True)),
        ("grid_columns", Field(INT, "Columns", True, 8, minimum=1, maximum=26)),
        ("grid_rows", Field(INT, "Rows", True, 6, minimum=1, maximum=50)),
        ("up_direction", Field(TEXT, "Up", True, "North", choices=("North", "South", "East", "West"))),
    ),
    "hives": entity(
        ("parent_apiary_id", Field(TEXT, "Apiary", True, editable=False)),
        ("owner", Field(TEXT, "Owner")),
        ("name", Field(TEXT, "Name", True)),
        ("grid_column", Field(INT, "Grid column", True, 1, minimum=1, maximum=26)),
        ("grid_row", Field(INT, "Grid row", True, 1, minimum=1, maximum=50)),
        ("status", Field(TEXT, "Status", True, "active", choices=("active", "inactive", "storage"))),
    ),
    "boxes": entity(
        ("parent_hive_id", Field(TEXT, "Hive", True, editable=False)),
        ("position", Field(INT, "Position", True, 0, minimum=0)),
        ("max_frames", Field(INT, "Capacity", True, 10, choices=("8", "10"))),
        ("type", Field(TEXT, "Type", True, "normal", choices=("normal", "deep"))),
        ("name", Field(TEXT, "Code", True)),
    ),
    "frames": entity(
        ("parent_box_id", Field(TEXT, "Box", True, editable=False)),
        ("position", Field(INT, "Position", True, 0, minimum=0)),
        ("name", Field(TEXT, "Code", True)),
    ),
    "equipment_types": entity(("name", Field(TEXT, "Name", True))),
    "equipment": entity(
        ("code", Field(TEXT, "Code", True, editable=False)),
        ("equipment_type_id", Field(TEXT, "Equipment type", True)),
        ("parent_hive_id", Field(TEXT, "Hive", editable=False)),
    ),
    "notes": entity(
        ("target_type", Field(TEXT, "Target type", True, choices=("apiary", "hive", "box", "frame", "equipment"))),
        ("target_id", Field(TEXT, "Target", True)),
        ("nature", Field(TEXT, "Nature", True, choices=("Disease", "Maintenance", "Other", "Pest", "Queen", "Temperament", "Treatment", "Todo", "Moved"))),
        ("description", Field(TEXT, "Description", True)),
        ("archived", Field(BOOL, "Archived", True, False)),
        ("archived_at", Field(TEXT, "Archived at")),
    ),
    "measurements": entity(
        ("parent_frame_id", Field(TEXT, "Frame", True, editable=False)),
        ("scope", Field(TEXT, "Scope", True, "both", choices=("both", "left", "right"))),
        ("comb_color", Field(TEXT, "Comb color", True, "white", choices=("white", "brown", "black"))),
        *[(name, Field(INT, label, True, 0, minimum=0, maximum=100)) for name, label in (
            ("bees", "Bees"), ("empty_cells", "Empty cells"), ("drone_cells", "Drone cells"),
            ("capped_brood_cells", "Capped brood"), ("uncapped_brood_cells", "Uncapped brood"),
            ("capped_honey_cells", "Capped honey"), ("uncapped_honey_cells", "Uncapped honey"),
            ("pollen_cells", "Pollen"),
        )],
        ("queen_cells", Field(INT, "Queen cells", True, 0, minimum=0, maximum=5)),
    ),
}

WORKSHEETS = tuple(SCHEMAS)


def columns(sheet: str) -> list[str]:
    return list(SCHEMAS[sheet])


def empty_frame(sheet: str) -> pl.DataFrame:
    return pl.DataFrame(schema={name: field.dtype for name, field in SCHEMAS[sheet].items()})
