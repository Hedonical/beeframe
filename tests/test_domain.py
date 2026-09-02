from datetime import datetime, timedelta, timezone
import random
import re

import polars as pl
import pytest

from beeframe.hierarchy import hidden_ids, insert_positions, move_rows
from beeframe.domain import archive_entity, changed_rows, edit_entity, move_entities, move_hives, repair_legacy_integrity
from beeframe.naming import PLANTS, box_code, equipment_code, frame_code, new_id, plant_name
from beeframe.operations import measured_within_hour, note_order
from beeframe.schemas import SCHEMAS, WORKSHEETS, columns, empty_frame
from beeframe.sheets import frame_to_matrix, matrix_to_frame, recognized_update
from beeframe.time import utc_now
from beeframe.validation import validate_record, validate_workbook


NOW = "2026-08-30T12:00:00Z"


def record(sheet, **values):
    base = {name: field.default for name, field in SCHEMAS[sheet].items()}
    base.update({"id": new_id(), "created_at": NOW, "updated_at": NOW, "is_archived": False}, **values)
    return base


def workbook():
    return {sheet: empty_frame(sheet) for sheet in WORKSHEETS}


def frame(sheet, rows):
    return pl.DataFrame(rows, schema={name: field.dtype for name, field in SCHEMAS[sheet].items()}, strict=False)


def test_uuid_generation_is_canonical_and_unique():
    values = {new_id() for _ in range(100)}
    assert len(values) == 100
    assert all(re.fullmatch(r"[0-9a-f-]{36}", value) for value in values)


def test_codes_exclude_o_and_zero():
    rng = random.Random(4)
    assert all(re.fullmatch(r"[A-NP-Z]{2}", box_code(set(), rng)) for _ in range(100))
    assert all(re.fullmatch(r"[A-NP-Z][1-9][A-NP-Z]", frame_code(set(), rng)) for _ in range(100))
    assert all(re.fullmatch(r"[A-NP-Z]{4}", equipment_code(set(), rng)) for _ in range(100))


def test_plant_name_is_local_and_unique():
    assert plant_name({"Clover"}, random.Random(2)) != "Clover"
    with pytest.raises(ValueError):
        plant_name(set(PLANTS), random.Random(1))


def test_optional_empty_cells_become_null_and_unknown_columns_survive():
    row = record("hives", parent_apiary_id=new_id(), owner=None, name="Clover", grid_column=1, grid_row=2, status="active")
    matrix = [columns("hives") + ["user_column"], [row.get(name, "") for name in columns("hives")] + ["keep me"]]
    loaded = matrix_to_frame("hives", matrix)
    assert loaded["owner"][0] is None
    assert loaded["user_column"][0] == "keep me"


def test_invalid_manually_edited_cell_is_not_coerced():
    values = [columns("boxes"), [new_id(), new_id(), "not an integer", 10, "normal", "AB", False, NOW, NOW, False]]
    with pytest.raises(Exception):
        matrix_to_frame("boxes", values)


def test_recognized_update_preserves_unknown_columns():
    item_id = new_id()
    matrix = [["id", "name", "favorite_color"], [item_id, "Old", "blue"]]
    row, headers, values = recognized_update("apiaries", matrix, item_id, {"name": "New", "favorite_color": "red"})
    assert (row, headers, values) == (2, ["name"], ["New"])


def test_position_insertion_and_move_between_parents():
    rows = [record("frames", parent_box_id="a", position=index, name=f"A{index + 1}B") for index in range(3)]
    df = frame("frames", rows)
    shifted = insert_positions(df, "parent_box_id", "a", 1, 2)
    assert shifted.sort("position")["position"].to_list() == [0, 3, 4]
    moved = move_rows(df, [rows[0]["id"], rows[1]["id"]], "parent_box_id", "b", 0)
    assert moved.filter(pl.col("parent_box_id") == "b").sort("position")["position"].to_list() == [0, 1]


def test_hidden_descendants_follow_archived_ancestor():
    data = workbook()
    apiary = record("apiaries", name="Home", grid_columns=8, grid_rows=6, up_direction="North")
    hive = record("hives", parent_apiary_id=apiary["id"], owner=None, name="Clover", grid_column=2, grid_row=3, status="active")
    box = record("boxes", parent_hive_id=hive["id"], position=0, max_frames=10, type="normal", name="AB")
    apiary["is_archived"] = True
    data.update(apiaries=frame("apiaries", [apiary]), hives=frame("hives", [hive]), boxes=frame("boxes", [box]))
    hidden = hidden_ids(data)
    assert hive["id"] in hidden["hives"] and box["id"] in hidden["boxes"]


def test_note_ordering_and_recent_measurement_warning():
    notes = frame("notes", [
        record("notes", target_type="frame", target_id="x", nature="Todo", description="older", archived=False, archived_at=None, created_at="2026-08-29T12:00:00Z"),
        record("notes", target_type="frame", target_id="x", nature="Todo", description="newer", archived=False, archived_at=None, created_at="2026-08-30T12:00:00Z"),
        record("notes", target_type="frame", target_id="x", nature="Todo", description="archived", archived=True, archived_at="2026-08-31T12:00:00Z"),
    ])
    assert note_order(notes)["description"].to_list() == ["newer", "older", "archived"]
    now = datetime.now(timezone.utc)
    measurements = frame("measurements", [record("measurements", parent_frame_id="x", scope="both", comb_color="brown", bees=0, empty_cells=0, drone_cells=0, capped_brood_cells=0, uncapped_brood_cells=0, capped_honey_cells=0, uncapped_honey_cells=0, pollen_cells=0, queen_cells=0, created_at=(now - timedelta(minutes=30)).isoformat().replace("+00:00", "Z"))])
    assert measured_within_hour(measurements, "x")


def test_measurement_bounds_are_validated():
    measurement = record("measurements", parent_frame_id=new_id(), scope="both", comb_color="white", bees=101, empty_cells=0, drone_cells=0, capped_brood_cells=0, uncapped_brood_cells=0, capped_honey_cells=0, uncapped_honey_cells=0, pollen_cells=0, queen_cells=0)
    assert any(issue.column == "bees" for issue in validate_record("measurements", measurement))
    measurement["bees"] = 0; measurement["queen_cells"] = 6
    assert any(issue.column == "queen_cells" for issue in validate_record("measurements", measurement))


def test_active_uniqueness_is_scoped_and_allows_archived_reuse():
    data = workbook()
    apiary = record("apiaries", name="AB", grid_columns=8, grid_rows=6, up_direction="North")
    box = record("boxes", parent_hive_id=new_id(), position=0, max_frames=10, type="normal", name="AB")
    data["apiaries"] = frame("apiaries", [apiary]); data["boxes"] = frame("boxes", [box])
    assert not any("unique active" in issue.rule for issue in validate_workbook(data))
    apiary["is_archived"] = True; data["apiaries"] = frame("apiaries", [apiary])
    assert not any("globally unique" in issue.rule for issue in validate_workbook(data))


def hierarchy_workbook():
    data = workbook()
    apiary = record("apiaries", name="Home", grid_columns=8, grid_rows=6, up_direction="North")
    hive = record("hives", parent_apiary_id=apiary["id"], owner=None, name="Clover", grid_column=1, grid_row=1, status="active")
    box = record("boxes", parent_hive_id=hive["id"], position=0, max_frames=10, type="normal", name="AB")
    frame_row = record("frames", parent_box_id=box["id"], position=0, name="A1B")
    data.update(apiaries=frame("apiaries", [apiary]), hives=frame("hives", [hive]), boxes=frame("boxes", [box]), frames=frame("frames", [frame_row]))
    return data, apiary, hive, box, frame_row


def test_archive_is_recursive_and_input_is_unchanged():
    data, _, hive, box, frame_row = hierarchy_workbook()
    result = archive_entity(data, "hives", hive["id"])
    assert not data["hives"]["is_archived"][0]
    assert result["hives"]["is_archived"][0]
    assert result["boxes"].filter(pl.col("id") == box["id"])["is_archived"][0]
    assert result["frames"].filter(pl.col("id") == frame_row["id"])["is_archived"][0]
    changes = changed_rows(data, result)
    assert {change["sheet"] for change in changes} == {"hives", "boxes", "frames"}


def test_restore_conflict_rejects_entire_move():
    data, _, hive, box, _ = hierarchy_workbook()
    other = record("boxes", parent_hive_id=hive["id"], position=1, max_frames=10, type="normal", name=box["name"], is_archived=True)
    data["boxes"] = frame("boxes", [box, other])
    before = data["boxes"].to_dicts()
    with pytest.raises(ValueError, match="already used"):
        move_entities(data, "boxes", [other["id"]], hive["id"], 1)
    assert data["boxes"].to_dicts() == before


def test_active_equipment_requires_active_parent():
    data = workbook()
    equipment_type = record("equipment_types", name="Lid")
    item = record("equipment", code="ABCD", equipment_type_id=equipment_type["id"], parent_hive_id=None)
    data["equipment_types"] = frame("equipment_types", [equipment_type]); data["equipment"] = frame("equipment", [item])
    assert any(issue.column == "parent_hive_id" and "active hive" in issue.rule for issue in validate_workbook(data))


def test_notes_can_target_equipment():
    data = workbook()
    equipment_type = record("equipment_types", name="Bottom board")
    item = record("equipment", code="ABCD", equipment_type_id=equipment_type["id"], parent_hive_id=None, is_archived=True)
    note = record("notes", target_type="equipment", target_id=item["id"], nature="Other", description="Retired equipment.", archived=False, archived_at=None)
    data["equipment_types"] = frame("equipment_types", [equipment_type])
    data["equipment"] = frame("equipment", [item])
    data["notes"] = frame("notes", [note])
    assert not any(issue.sheet == "notes" and issue.column == "target_id" for issue in validate_workbook(data))


def test_notes_can_target_apiaries_without_being_repaired_as_orphans():
    data, apiary, _, _, _ = hierarchy_workbook()
    note = record("notes", target_type="apiary", target_id=apiary["id"], nature="Other", description="Checked entrance.", archived=False, archived_at=None)
    data["notes"] = frame("notes", [note])
    assert not any(issue.sheet == "notes" and issue.column == "target_id" for issue in validate_workbook(data))
    assert not repair_legacy_integrity(data, NOW)["notes"]["archived"][0]


def test_duplicate_grid_occupancy_is_rejected():
    data, apiary, hive, _, _ = hierarchy_workbook()
    duplicate = record("hives", parent_apiary_id=apiary["id"], owner=None, name="Thistle", grid_column=1, grid_row=1, status="active")
    data["hives"] = frame("hives", [hive, duplicate])
    assert any("one active hive" in issue.rule for issue in validate_workbook(data))


def test_multi_move_preserves_relative_order_and_normalizes_indexes():
    data, _, hive, _, _ = hierarchy_workbook()
    destination = record("hives", parent_apiary_id=data["apiaries"]["id"][0], owner=None, name="Thistle", grid_column=2, grid_row=1, status="active")
    data["hives"] = frame("hives", [hive, destination])
    boxes = [record("boxes", parent_hive_id=hive["id"], position=i, max_frames=10, type="normal", name=name) for i, name in enumerate(("AB", "CD", "EF"))]
    target = record("boxes", parent_hive_id=destination["id"], position=4, max_frames=10, type="normal", name="GH")
    data["boxes"] = frame("boxes", boxes + [target])
    result = move_entities(data, "boxes", [boxes[2]["id"], boxes[0]["id"]], destination["id"], 0)
    moved = result["boxes"].filter(pl.col("parent_hive_id") == destination["id"]).sort("position")
    assert moved["name"].to_list() == ["AB", "EF", "GH"]
    assert moved["position"].to_list() == [0, 1, 2]
    assert result["boxes"].filter(pl.col("parent_hive_id") == hive["id"])["position"].to_list() == [0]


def test_repositioning_into_an_occupied_position_shifts_siblings():
    data, _, hive, _, _ = hierarchy_workbook()
    boxes = [record("boxes", parent_hive_id=hive["id"], position=i, max_frames=10, type="normal", name=name) for i, name in enumerate(("AB", "CD", "EF"))]
    data["boxes"] = frame("boxes", boxes)
    result = move_entities(data, "boxes", [boxes[0]["id"]], hive["id"], 1)
    ordered = result["boxes"].sort("position")
    assert ordered["name"].to_list() == ["CD", "AB", "EF"]
    assert ordered["position"].to_list() == [0, 1, 2]


@pytest.mark.parametrize("sheet,parent_column", [("boxes", "parent_hive_id"), ("frames", "parent_box_id")])
def test_every_forward_and_backward_reorder_is_contiguous(sheet, parent_column):
    data, _, hive, box, _ = hierarchy_workbook()
    names = ("AB", "CD", "EF", "GH", "JK") if sheet == "boxes" else ("A1B", "A2B", "A3B", "A4B", "A5B")
    parent_id = hive["id"] if sheet == "boxes" else box["id"]
    rows = [
        record(sheet, **{parent_column: parent_id, "position": position, "name": name}, **({"max_frames": 10, "type": "normal"} if sheet == "boxes" else {}))
        for position, name in enumerate(names)
    ]
    data[sheet] = frame(sheet, rows)

    for source in range(len(rows)):
        for target in range(len(rows)):
            result = move_entities(data, sheet, [rows[source]["id"]], parent_id, target)
            expected = list(names)
            moved = expected.pop(source)
            expected.insert(target, moved)
            ordered = result[sheet].sort("position")
            assert ordered["name"].to_list() == expected
            assert ordered["position"].to_list() == list(range(len(rows)))
            assert not any(issue.sheet == sheet and issue.column == "position" for issue in validate_workbook(result))


def test_edit_position_mutation_includes_moved_box_and_every_shifted_sibling():
    data, _, hive, _, _ = hierarchy_workbook()
    boxes = [record("boxes", parent_hive_id=hive["id"], position=i, max_frames=10, type="normal", name=name) for i, name in enumerate(("AB", "CD", "EF", "GH"))]
    data["boxes"] = frame("boxes", boxes)

    edited = edit_entity(data, "boxes", boxes[0]["id"], {"type": "deep"})
    result = move_entities(edited, "boxes", [boxes[0]["id"]], hive["id"], 3)
    updates = [item for item in changed_rows(data, result) if item["sheet"] == "boxes"]

    assert {item["id"] for item in updates} == {box["id"] for box in boxes}
    assert result["boxes"].sort("position")["name"].to_list() == ["CD", "EF", "GH", "AB"]
    assert result["boxes"].filter(pl.col("id") == boxes[0]["id"])["type"][0] == "deep"


def test_legacy_repair_preserves_orphan_notes_and_normalizes_positions():
    data, _, hive, _, _ = hierarchy_workbook()
    boxes = [
        record("boxes", parent_hive_id=hive["id"], position=1, max_frames=10, type="normal", name=name)
        for name in ("AB", "CD")
    ]
    note = record(
        "notes", target_type="box", target_id=new_id(), nature="Moved",
        description="Legacy move", archived=False, archived_at=None,
    )
    data["boxes"] = frame("boxes", boxes)
    data["notes"] = frame("notes", [note])

    repaired = repair_legacy_integrity(data, NOW)

    assert repaired["boxes"].sort("position")["position"].to_list() == [0, 1]
    assert repaired["notes"]["archived"][0]
    assert repaired["notes"]["archived_at"][0] == NOW
    integrity_issues = [
        issue for issue in validate_workbook(repaired)
        if (issue.sheet == "notes" and issue.column == "target_id")
        or (issue.sheet in ("boxes", "frames") and issue.column == "position")
    ]
    assert not integrity_issues


def test_hives_move_between_apiaries_and_fill_open_grid_cells():
    data, source, hive, box, _ = hierarchy_workbook()
    destination = record("apiaries", name="South", grid_columns=3, grid_rows=2, up_direction="North")
    resident = record("hives", parent_apiary_id=destination["id"], owner=None, name="Mint", grid_column=1, grid_row=1, status="active")
    data["apiaries"] = frame("apiaries", [source, destination])
    data["hives"] = frame("hives", [hive, resident])
    result = move_hives(data, [hive["id"]], destination["id"], 1, 1)
    moved = result["hives"].filter(pl.col("id") == hive["id"]).to_dicts()[0]
    assert (moved["parent_apiary_id"], moved["grid_column"], moved["grid_row"]) == (destination["id"], 2, 1)
    assert not result["boxes"].filter(pl.col("id") == box["id"])["is_archived"][0]


def test_moving_hive_to_archive_archives_descendants():
    data, _, hive, box, _ = hierarchy_workbook()
    result = move_hives(data, [hive["id"]], None)
    assert result["hives"].filter(pl.col("id") == hive["id"])["is_archived"][0]
    assert result["boxes"].filter(pl.col("id") == box["id"])["is_archived"][0]


def test_edit_targets_captured_record_id():
    data, _, hive, _, _ = hierarchy_workbook()
    other = record("hives", parent_apiary_id=data["apiaries"]["id"][0], owner=None, name="Thistle", grid_column=2, grid_row=1, status="active")
    data["hives"] = frame("hives", [hive, other])
    result = edit_entity(data, "hives", hive["id"], {"owner": "Alex"})
    assert result["hives"].filter(pl.col("id") == hive["id"])["owner"][0] == "Alex"
    assert result["hives"].filter(pl.col("id") == other["id"])["owner"][0] is None


def test_matrix_round_trip():
    item = record("equipment_types", name="10-frame lid")
    df = frame("equipment_types", [item])
    assert matrix_to_frame("equipment_types", frame_to_matrix(df)).to_dicts() == df.to_dicts()


def test_apiary_grid_and_hive_cell_are_validated():
    data = workbook()
    apiary = record("apiaries", name="Home", grid_columns=4, grid_rows=3, up_direction="North")
    hive = record("hives", parent_apiary_id=apiary["id"], owner=None, name="Clover", grid_column=5, grid_row=4, status="active")
    data["apiaries"] = frame("apiaries", [apiary]); data["hives"] = frame("hives", [hive])
    rules = {issue.rule for issue in validate_workbook(data)}
    assert "a cell inside the parent apiary grid" in rules


def test_display_time_is_portable_and_uses_new_york_dst():
    from beeframe.time import display_time
    assert display_time("2026-07-01T16:05:00Z") == "Jul 1, 2026 12:05 PM"
