import polars as pl


def active(df: pl.DataFrame) -> pl.DataFrame:
    return df.filter(~pl.col("is_archived")) if "is_archived" in df.columns else df


def insert_positions(df: pl.DataFrame, parent_column: str, parent_id: str, position: int, count: int = 1) -> pl.DataFrame:
    return df.with_columns(
        pl.when((pl.col(parent_column) == parent_id) & ~pl.col("is_archived") & (pl.col("position") >= position))
        .then(pl.col("position") + count)
        .otherwise(pl.col("position"))
        .alias("position")
    )


def move_rows(df: pl.DataFrame, ids: list[str], parent_column: str, parent_id: str, position: int) -> pl.DataFrame:
    rows = df.to_dicts()
    moving = sorted((row for row in rows if row["id"] in ids), key=lambda row: row["position"])
    kept = [row for row in rows if row["id"] not in ids]
    affected = {row[parent_column] for row in moving} | {parent_id}
    for parent in affected:
        siblings = sorted((row for row in kept if row[parent_column] == parent and not row["is_archived"]), key=lambda row: row["position"])
        for offset, row in enumerate(siblings):
            row["position"] = offset
    target = sorted((row for row in kept if row[parent_column] == parent_id and not row["is_archived"]), key=lambda row: row["position"])
    position = min(max(position, 0), len(target))
    for row in target[position:]:
        row["position"] += len(moving)
    for offset, row in enumerate(moving):
        row[parent_column] = parent_id
        row["position"] = position + offset
    return pl.DataFrame([*kept, *moving], schema=df.schema, strict=False).sort("id")


def hidden_ids(data: dict[str, pl.DataFrame]) -> dict[str, set[str]]:
    hidden = {name: set(df.filter(pl.col("is_archived"))["id"].to_list()) for name, df in data.items() if "id" in df.columns}
    for sheet, parent_sheet, parent_col in (
        ("hives", "apiaries", "parent_apiary_id"), ("boxes", "hives", "parent_hive_id"), ("frames", "boxes", "parent_box_id")
    ):
        if sheet in data:
            hidden[sheet] |= set(data[sheet].filter(pl.col(parent_col).is_in(hidden.get(parent_sheet, set())))["id"].to_list())
    return hidden
