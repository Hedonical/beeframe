from datetime import timedelta

import polars as pl

from .time import parse_utc, utc_now


def note_order(df: pl.DataFrame) -> pl.DataFrame:
    """Active notes newest-first, then archived notes newest-archive-first."""
    return df.with_columns(
        pl.when(pl.col("archived")).then(pl.lit(1)).otherwise(pl.lit(0)).alias("_group"),
        pl.when(pl.col("archived")).then(pl.col("archived_at")).otherwise(pl.col("created_at")).alias("_order"),
    ).sort(["_group", "_order"], descending=[False, True]).drop("_group", "_order")


def measured_within_hour(df: pl.DataFrame, frame_id: str, now: str | None = None) -> bool:
    moment = parse_utc(now or utc_now())
    return any(moment - parse_utc(value) <= timedelta(hours=1) for value in df.filter((pl.col("parent_frame_id") == frame_id) & ~pl.col("is_archived"))["created_at"].to_list())
