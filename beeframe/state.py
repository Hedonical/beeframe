from dataclasses import dataclass, field
from typing import Any

import polars as pl

from .schemas import WORKSHEETS, empty_frame


@dataclass
class AppState:
    data: dict[str, pl.DataFrame] = field(default_factory=lambda: {sheet: empty_frame(sheet) for sheet in WORKSHEETS})
    selected: dict[str, str | None] = field(default_factory=lambda: {name: None for name in ("apiary", "hive", "box", "frame", "equipment")})
    spreadsheet: dict[str, str] | None = None
    ready: bool = False
    busy: bool = False
    archived_mode: bool = False

    def clear_below(self, level: str) -> None:
        levels = ("apiary", "hive", "box", "frame")
        for child in levels[levels.index(level) + 1:]:
            self.selected[child] = None
        self.selected["equipment"] = None

    def select(self, level: str, record_id: str | None) -> None:
        self.selected[level] = record_id
        if level in ("apiary", "hive", "box", "frame"):
            self.clear_below(level)

    def _archived(self, sheet: str, row: dict[str, Any]) -> bool:
        if row.get("is_archived"):
            return True
        parents = {
            "hives": ("apiaries", "parent_apiary_id"), "boxes": ("hives", "parent_hive_id"),
            "frames": ("boxes", "parent_box_id"), "equipment": ("hives", "parent_hive_id"),
            "measurements": ("frames", "parent_frame_id"),
        }
        if sheet not in parents:
            return False
        parent_sheet, parent_column = parents[sheet]
        parent_id = row.get(parent_column)
        if parent_id is None:
            return sheet == "equipment"
        parent = self.record(parent_sheet, parent_id)
        return parent is None or self._archived(parent_sheet, parent)

    def rows(self, sheet: str, include_all: bool = False, **filters: Any) -> list[dict[str, Any]]:
        df = self.data[sheet]
        for column, value in filters.items():
            df = df.filter(pl.col(column).is_null() if value is None else pl.col(column) == value)
        if "position" in df.columns:
            df = df.sort("position")
        rows = df.to_dicts()
        return rows if include_all else [row for row in rows if self._archived(sheet, row) == self.archived_mode]

    def record(self, sheet: str, record_id: str | None) -> dict[str, Any] | None:
        if not record_id:
            return None
        rows = self.data[sheet].filter(pl.col("id") == record_id).to_dicts()
        return rows[0] if rows else None
