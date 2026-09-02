import json
import uuid
from collections import Counter
from pathlib import Path
from time import monotonic

from shiny import App, reactive, render, ui

from beeframe import SCHEMA_VERSION
from beeframe.domain import archive_entity, changed_rows, edit_entity, move_entities, move_hives, repair_legacy_integrity
from beeframe.hierarchy import active, insert_positions, move_rows
from beeframe.modules.connection import connection_server, connection_ui
from beeframe.modules.navigation import toolbar_server, toolbar_ui
from beeframe.naming import box_code, equipment_code, frame_code, new_id, plant_name
from beeframe.schemas import SCHEMAS, WORKSHEETS, columns
from beeframe.sheets import matrix_to_frame
from beeframe.state import AppState
from beeframe.time import display_time, parse_utc, utc_now
from beeframe.validation import validate_record, validate_workbook


def script_button(label, level, record_id, class_="entity-button", **attributes):
    return ui.tags.button(label, type="button", class_=class_, data_level=level, data_id=record_id, **attributes)


def signal_button(label, signal):
    return ui.tags.button(
        label, type="button", class_="btn-primary submit-once", data_action_signal=signal,
        onclick=f"document.getElementById('{signal}').click()",
    )


def edit_submit_button():
    return ui.tags.button("Save changes", type="button", class_="btn-primary submit-once", data_edit_submit="true")


def base_record(**values):
    now = utc_now()
    return {"id": new_id(), **values, "created_at": now, "updated_at": now, "is_archived": False}


def column_label(column):
    return chr(64 + column)


def comb_color_value(value):
    return {"white": 1, "brown": 5, "black": 10}.get(str(value).casefold(), 1)


def comb_color_label(value):
    return str(value).title()


def comb_color_hex(value):
    number = comb_color_value(value)
    low, middle, high = ((249, 246, 234), (151, 100, 57), (37, 33, 29))
    start, end, fraction = (low, middle, (number - 1) / 4) if number <= 5 else (middle, high, (number - 5) / 5)
    return "#" + "".join(f"{round(a + (b - a) * fraction):02x}" for a, b in zip(start, end))


def apiary_grid(apiary, hives=(), selected_hive_id=None, editor=False, selected_point=None, editing_hive_id=None, editing_hive_ids=()):
    occupied = {(hive["grid_column"], hive["grid_row"]): hive for hive in hives}
    editable_hive_ids = {*editing_hive_ids, *([editing_hive_id] if editing_hive_id else [])}
    cells = [ui.div(class_="grid-corner"), *[ui.div(column_label(column), class_="grid-axis") for column in range(1, apiary["grid_columns"] + 1)]]
    for row in range(1, apiary["grid_rows"] + 1):
        cells.append(ui.div(str(row), class_="grid-axis"))
        for column in range(1, apiary["grid_columns"] + 1):
            hive = occupied.get((column, row))
            selected = bool(selected_point and selected_point["grid_column"] == column and selected_point["grid_row"] == row)
            if editor:
                cells.append(ui.tags.button(
                    hive["name"] if hive else f"{column_label(column)}{row}", type="button",
                    class_=f"grid-cell grid-editor-cell{' is-selected' if selected else ''}{' is-occupied' if hive else ''}",
                    data_grid_column=column, data_grid_row=row, disabled=bool(hive and hive["id"] not in editable_hive_ids),
                    aria_label=f"Grid cell {column_label(column)}{row}",
                ))
            elif hive:
                cells.append(script_button(
                    hive["name"], "hive", hive["id"],
                    f"grid-cell hive-grid-cell status-{hive['status']}{' is-selected' if hive['id'] == selected_hive_id else ''}",
                ))
            else:
                cells.append(ui.div(class_="grid-cell grid-empty", aria_label=f"Empty grid cell {column_label(column)}{row}"))
    directions = ("North", "East", "South", "West")
    top = directions.index(apiary["up_direction"])
    return ui.div(
        ui.div(f"{directions[top]} ↑", class_="grid-direction grid-direction-top"),
        ui.div(
            ui.div(directions[(top - 1) % 4], class_="grid-direction grid-direction-side"),
            ui.div(ui.div(*cells, class_="grid-matrix", style=f"--grid-columns:{apiary['grid_columns']}"), class_="grid-scroll"),
            ui.div(directions[(top + 1) % 4], class_="grid-direction grid-direction-side"),
            class_="grid-middle",
        ),
        ui.div(f"↓ {directions[(top + 2) % 4]}", class_="grid-direction grid-direction-bottom"),
        class_="apiary-grid",
    )


def summary_grid(apiary, hives, counts, unit):
    occupied = {(hive["grid_column"], hive["grid_row"]): hive for hive in hives}
    cells = [ui.div(class_="grid-corner"), *[ui.div(column_label(column), class_="grid-axis") for column in range(1, apiary["grid_columns"] + 1)]]
    maximum = max(counts.values(), default=0)
    for row in range(1, apiary["grid_rows"] + 1):
        cells.append(ui.div(str(row), class_="grid-axis"))
        for column in range(1, apiary["grid_columns"] + 1):
            hive = occupied.get((column, row))
            if not hive:
                cells.append(ui.div(class_="grid-cell grid-empty"))
                continue
            count = counts.get(hive["id"], 0)
            strength = round(count / maximum * 100) if maximum else 0
            heat = min(4, max(1, (strength + 24) // 25)) if count else 0
            cells.append(ui.div(
                ui.span(hive["name"], class_="summary-grid-hive"),
                ui.strong(str(count), class_="summary-grid-count"),
                class_=f"grid-cell summary-grid-cell{' has-matches' if count else ''} heat-{heat}",
                style=f"--heat:{strength}%", title=f"{hive['name']}: {count} matching {unit}",
            ))
    directions = ("North", "East", "South", "West")
    top = directions.index(apiary["up_direction"])
    return ui.div(
        ui.div(f"{directions[top]} ↑", class_="grid-direction grid-direction-top"),
        ui.div(
            ui.div(directions[(top - 1) % 4], class_="grid-direction grid-direction-side"),
            ui.div(ui.div(*cells, class_="grid-matrix", style=f"--grid-columns:{apiary['grid_columns']}"), class_="grid-scroll"),
            ui.div(directions[(top + 1) % 4], class_="grid-direction grid-direction-side"),
            class_="grid-middle",
        ),
        ui.div(f"↓ {directions[(top + 2) % 4]}", class_="grid-direction grid-direction-bottom"),
        class_="apiary-grid summary-apiary-grid",
    )


app_ui = ui.page_fluid(
    ui.tags.meta(name="viewport", content="width=device-width, initial-scale=1, viewport-fit=cover"),
    ui.tags.script(src="shiny-bridge.js"), ui.tags.script(src="app-ui.js"),
    ui.tags.link(rel="stylesheet", href="styles.css"), ui.output_ui("application"), title="Beeframe",
)


def server(input, output, session):
    state = AppState()
    changed = reactive.value(0)
    grid_changed = reactive.value(0)
    move_changed = reactive.value(0)
    connected = reactive.value(False)
    status = reactive.value("")
    grid_point = reactive.value(None)
    editing_note = reactive.value(None)
    workflow_kind = reactive.value(None)
    pending = {}
    contexts = {}
    last_measurement_save = (None, 0.0)

    def touch():
        changed.set(changed.get() + 1)

    def touch_grid():
        grid_changed.set(grid_changed.get() + 1)

    def touch_move():
        move_changed.set(move_changed.get() + 1)

    async def request(action, **payload):
        if state.busy:
            return None
        request_id = str(uuid.uuid4())
        pending[request_id] = {"action": action, **payload.pop("_context", {})}
        state.busy = True
        status.set("Working with Google Sheets…")
        touch()
        await session.send_custom_message("google_request", {"requestId": request_id, "request": {"action": action, **payload}})

    async def connect():
        if not state.busy:
            await request("choose_sheet")

    connection_server("connection", connect)

    def active_used_names():
        values = set()
        for sheet, name in (("apiaries", "name"), ("hives", "name"), ("boxes", "name"), ("frames", "name"), ("equipment", "code")):
            df = active(state.data[sheet])
            if name in df.columns:
                values.update(str(value) for value in df[name].drop_nulls().to_list())
        return values

    def load_workbook(workbook):
        contexts.pop("legacy_repair", None)
        sheets = workbook.get("sheets", {})
        if not any(sheets.get(name) for name in sheets):
            ui.modal_show(ui.modal(
                ui.p("Beeframe will create nine worksheets, their headers, and schema metadata. No other data will be added."),
                ui.input_action_button("initialize_confirm", "Create Beeframe workbook", class_="btn-primary"),
                ui.input_action_button("initialize_cancel", "Choose another Sheet", class_="btn-outline-secondary"),
                title="Initialize this empty spreadsheet?", easy_close=False, footer=None,
            ))
            status.set("Empty spreadsheet selected. Confirmation required.")
            return
        try:
            loaded = {name: matrix_to_frame(name, sheets.get(name, [])) for name in WORKSHEETS}
            issues = validate_workbook(loaded)
            metadata = dict(zip(loaded["metadata"]["key"].to_list(), loaded["metadata"]["value"].to_list()))
            if metadata.get("schema_version") != SCHEMA_VERSION:
                raise ValueError(f"metadata: schema_version must be {SCHEMA_VERSION}")
            if issues:
                recoverable = all(
                    (issue.sheet == "notes" and issue.column == "target_id")
                    or (issue.sheet in ("boxes", "frames") and issue.column == "position" and "unique active position" in issue.rule)
                    for issue in issues
                )
                if not recoverable:
                    raise ValueError("\n".join(str(issue) for issue in issues[:25]))
                repaired = repair_legacy_integrity(loaded, utc_now())
                remaining = validate_workbook(repaired)
                if remaining:
                    raise ValueError("\n".join(str(issue) for issue in remaining[:25]))
                contexts["legacy_repair"] = {
                    "updates": changed_rows(loaded, repaired),
                    "notes": sum(issue.sheet == "notes" for issue in issues),
                    "positions": sum(issue.sheet in ("boxes", "frames") for issue in issues),
                }
                loaded = repaired
        except Exception as error:
            state.ready = False
            status.set(f"This workbook is incompatible and was not modified. {error}")
            touch()
            return
        state.data = loaded
        state.ready = True
        connected.set(True)
        state.spreadsheet = {"name": workbook.get("title", "Google Sheet")}
        status.set(f"Connected to {state.spreadsheet['name']}.")
        ui.modal_remove()
        repair = contexts.get("legacy_repair")
        if repair:
            ui.modal_show(ui.modal(
                ui.p("This workbook contains legacy move data that Beeframe can safely repair."),
                ui.p(f"Orphaned notes preserved as archived: {repair['notes']}. Position groups normalized: {repair['positions']}."),
                ui.input_action_button("legacy_repair_confirm", "Repair workbook", class_="btn-primary submit-once"),
                title="Workbook repair required", easy_close=False, footer=None,
            ))
            status.set("Workbook repair required before editing.")
        touch()

    @reactive.effect
    @reactive.event(input.legacy_repair_confirm)
    async def _legacy_repair_confirm():
        repair = contexts.get("legacy_repair")
        if repair:
            await mutate(repair["updates"], context={"legacy_repair": True})

    @reactive.effect
    @reactive.event(input.fullscreen_error)
    def _fullscreen_error():
        ui.notification_show("Fullscreen is not available in this browser window.", type="warning", duration=5)

    @reactive.effect
    @reactive.event(input.google_result)
    async def _google_result():
        message = json.loads(input.google_result())
        context = pending.pop(message.get("requestId", ""), {})
        state.busy = bool(pending)
        if not message.get("ok"):
            if context.get("rollback") is not None:
                state.data = context["rollback"]
                touch()
            status.set(message.get("error", "Google Sheets request failed."))
            ui.notification_show(status.get(), type="error", duration=8)
            if context.get("equipment_codes"):
                await request("load_workbook", _context={"equipment_verify": context["equipment_codes"]})
            touch()
            return
        data = message.get("data", {})
        if context.get("action") in ("choose_sheet", "initialize", "load_workbook"):
            load_workbook(data)
            if context.get("equipment_verify"):
                existing = set(state.data["equipment"]["code"].to_list())
                codes = context["equipment_verify"]
                ui.modal_show(ui.modal(
                    ui.p("The write result was ambiguous, so Beeframe refreshed equipment without retrying."),
                    *[ui.div(f"{code}: {'saved' if code in existing else 'not found'}", class_="code-result") for code in codes],
                    title="Equipment write check", easy_close=False, footer=ui.modal_button("Close"),
                ))
        elif context.get("action") in ("append", "update_by_id"):
            sheet = data["sheet"]
            try:
                refreshed = matrix_to_frame(sheet, data["values"])
                candidate = {**state.data, sheet: refreshed}
                issues = validate_workbook(candidate)
                if issues:
                    raise ValueError(str(issues[0]))
                state.data[sheet] = refreshed
                if sheet in ("apiaries", "hives"):
                    touch_grid()
                status.set("Saved to Google Sheets.")
                if context.get("equipment_codes"):
                    ui.modal_show(ui.modal(
                        ui.p("Google confirmed every item. Keep this list open while marking the equipment."),
                        *[ui.div(code, class_="code-result") for code in context["equipment_codes"]],
                        title="Equipment saved", easy_close=False, footer=ui.modal_button("Close"),
                    ))
                elif context.get("reopen_notes"):
                    ui.modal_remove()
                    notes()
                else:
                    ui.modal_remove()
                ui.notification_show("Saved", type="message", duration=1.5)
            except Exception as error:
                status.set(f"Google saved the write, but refreshed data is invalid: {error}")
        elif context.get("action") == "mutate":
            try:
                refreshed = {sheet: matrix_to_frame(sheet, values) for sheet, values in data["sheets"].items()}
                candidate = {**state.data, **refreshed}
                issues = validate_workbook(candidate)
                if issues:
                    raise ValueError(str(issues[0]))
                state.data.update(refreshed)
                if {"apiaries", "hives"} & refreshed.keys():
                    touch_grid()
                if context.get("legacy_repair"):
                    contexts.pop("legacy_repair", None)
                    status.set("Workbook repaired and saved to Google Sheets.")
                else:
                    status.set("Saved to Google Sheets.")
                ui.modal_remove()
                ui.notification_show("Saved", type="message", duration=1.5)
            except Exception as error:
                status.set(f"Google saved the write, but refreshed data is invalid: {error}")
        elif data.get("disconnected"):
            state.ready = False
            connected.set(False)
            state.spreadsheet = None
            status.set("Disconnected.")
        touch()

    @reactive.effect
    @reactive.event(input.initialize_confirm)
    async def _initialize():
        now = utc_now()
        sheets = []
        for name in WORKSHEETS:
            values = [columns(name)]
            if name == "metadata":
                values += [["application_name", "Beeframe"], ["schema_version", SCHEMA_VERSION], ["initialized_at", now]]
            sheets.append({"name": name, "values": values})
        await request("initialize", sheets=sheets)

    @reactive.effect
    @reactive.event(input.initialize_cancel)
    def _initialize_cancel():
        ui.modal_remove()
        status.set("Choose a different spreadsheet.")

    def append(sheet, records, unique_column=None, unique_value=None, context=None):
        issues = [issue for record in records for issue in validate_record(sheet, record)]
        if issues:
            ui.notification_show(str(issues[0]), type="error", duration=7)
            return None
        domain_column = {"apiaries": "name", "hives": "name", "boxes": "name", "frames": "name", "equipment": "code"}.get(sheet)
        unique_values = [record[domain_column] for record in records if domain_column]
        return request("append", sheet=sheet, rows=records, uniqueColumn=unique_column, uniqueValue=unique_value, uniqueValues=unique_values, _context=context or {})

    def update(sheet, record_id, values):
        values = {**values, "updated_at": utc_now()}
        domain_column = {"apiaries": "name", "hives": "name", "boxes": "name", "frames": "name", "equipment": "code"}.get(sheet)
        unique_values = [values[domain_column]] if domain_column in values else []
        return request("update_by_id", sheet=sheet, id=record_id, values=values, recognizedColumns=columns(sheet), uniqueValues=unique_values)

    async def mutate(updates=(), appends=(), context=None, optimistic=None):
        if state.busy:
            return None
        now = utc_now()
        prepared_updates = [
            {"sheet": item["sheet"], "id": item["id"], "values": {**item["values"], "updated_at": now}, "recognizedColumns": columns(item["sheet"])}
            for item in updates
        ]
        prepared_appends = [{"sheet": item["sheet"], "rows": item["rows"]} for item in appends]
        domain_columns = {"apiaries": "name", "hives": "name", "boxes": "name", "frames": "name", "equipment": "code"}
        unique_values = [record[domain_columns[item["sheet"]]] for item in appends for record in item["rows"] if item["sheet"] in domain_columns]
        request_context = {**(context or {}), **({"rollback": state.data} if optimistic is not None else {})}
        await request("mutate", updates=prepared_updates, appends=prepared_appends, uniqueValues=unique_values, _context=request_context)
        if optimistic is not None:
            state.data = optimistic
            ui.modal_remove()
            touch()
        return None

    @render.ui
    def application():
        if not connected.get():
            return ui.div(
                connection_ui("connection"),
                ui.div(status.get(), class_="connection-status") if status.get() else None,
                class_="connection-screen",
            )
        return ui.div(
            ui.output_ui("apiary_panel"), ui.output_ui("hierarchy"), toolbar_ui("toolbar"),
            ui.div(
                ui.input_action_button("move_save_signal", "Move signal"),
                class_="persistent-action-signals", aria_hidden="true",
            ),
            class_="app-shell",
        )

    @render.ui
    def apiary_panel():
        grid_changed()
        apiaries = [row for row in state.rows("apiaries", include_all=True) if not state._archived("apiaries", row)]
        apiary = None if state.archived_mode else state.record("apiaries", state.selected["apiary"])
        choices = ui.div(*[
            script_button(row["name"], "apiary", row["id"], f"relational-choice{' is-selected' if apiary and row['id'] == apiary['id'] else ''}")
            for row in apiaries
        ], script_button("Archived", "archive", "archived", f"relational-choice archive-choice{' is-selected' if state.archived_mode else ''}"), class_="relational-strip")
        grid_view = None
        if apiary:
            hives = state.rows("hives", parent_apiary_id=apiary["id"])
            grid_view = apiary_grid(apiary, hives, selected_hive_id=state.selected["hive"])
        return ui.tags.section(
            ui.div(ui.span("Apiary"), ui.strong("Archived" if state.archived_mode else apiary["name"] if apiary else "Choose an apiary"), class_="selection-heading"),
            choices,
            ui.div(
                ui.span(ui.tags.i(class_="status-dot status-active"), "Active"),
                ui.span(ui.tags.i(class_="status-dot status-inactive"), "Inactive"),
                ui.span(ui.tags.i(class_="status-dot status-storage"), "Storage"),
                class_="status-legend", aria_label="Hive status legend",
            ) if apiary else None,
            grid_view, class_="level relationship-tab apiary-tab",
        )

    def selected_record():
        for level, sheet in (("equipment", "equipment"), ("frame", "frames"), ("box", "boxes"), ("hive", "hives"), ("apiary", "apiaries")):
            record = state.record(sheet, state.selected[level])
            if record:
                return level, sheet, record
        return None, None, None

    def owner_choices():
        return sorted({row["owner"] for row in state.rows("hives", include_all=True) if row.get("owner")}, key=str.casefold)

    def equipment_name_choices():
        return sorted({row["name"] for row in state.rows("equipment_types", include_all=True) if not row["is_archived"]}, key=str.casefold)

    def position_editor(input_id, value, maximum, lower_label, higher_label):
        return ui.div(
            ui.input_numeric(input_id, "Position", value, min=0, max=maximum),
            ui.div(
                ui.tags.button(lower_label, type="button", class_="position-step", data_position_input=input_id, data_position_delta=-1),
                ui.tags.button(higher_label, type="button", class_="position-step", data_position_input=input_id, data_position_delta=1),
                class_="position-steps",
            ),
            class_="position-editor",
        )

    def box_type_label(value):
        return "Medium" if value == "normal" else str(value).title()

    def audit_note(level, target_id, description, nature="Other"):
        return base_record(target_type=level, target_id=target_id, nature=nature, description=description, archived=False, archived_at=None)

    def audit_value(field, value):
        if value is None or value == "":
            return "Unassigned"
        if field == "type":
            return box_type_label(value)
        if field == "equipment_type_id":
            row = state.record("equipment_types", value)
            return row["name"] if row else "Unknown"
        return str(value)

    def edit_audit_description(level, record, values):
        labels = {
            "name": "name", "owner": "owner", "status": "status", "grid_column": "grid column", "grid_row": "grid row",
            "grid_columns": "columns", "grid_rows": "rows", "up_direction": "orientation", "type": "type",
            "max_frames": "capacity", "equipment_type_id": "description",
        }
        changes = [
            f"{labels.get(field, field.replace('_', ' '))} changed from {audit_value(field, record.get(field))} to {audit_value(field, value)}"
            for field, value in values.items() if record.get(field) != value
        ]
        item = record.get("name", record.get("code", level))
        return f"Edited {level} {item}: {'; '.join(changes)}." if changes else None

    def measurement_form():
        fields = [(name, field.label) for name, field in SCHEMAS["measurements"].items() if field.maximum == 100]

        def control(name, label, maximum=100, step=5):
            input_id = f"measurement_{name}"
            colors = {
                "bees": ("#9cc8f5", "#edf6ff"), "empty_cells": ("#d7dce2", "#f4f5f6"),
                "drone_cells": ("#cbb6eb", "#f4effc"), "capped_brood_cells": ("#f0aeaa", "#fff0ef"),
                "uncapped_brood_cells": ("#f6c79a", "#fff5e9"), "capped_honey_cells": ("#f3d47c", "#fff9df"),
                "uncapped_honey_cells": ("#f6e99a", "#fffde5"), "pollen_cells": ("#aad6a1", "#f1faef"),
                "queen": ("#e6b2d0", "#fff0f8"),
            }
            color, surface = colors[name]
            return ui.div(
                ui.div(
                    ui.strong(label),
                    ui.tags.input(type="range", id=f"{input_id}_slider", min=0, max=maximum, step=step, value=0, class_="measurement-slider", data_measurement_input=input_id, aria_label=f"{label} value"),
                    ui.input_numeric(input_id, "", 0, min=0, max=maximum, step=step),
                    class_="measurement-control-heading",
                ),
                class_="measurement-control", style=f"--measurement-color:{color};--measurement-surface:{surface}",
            )

        return ui.div(
            ui.div(ui.input_radio_buttons("measurement_scope", "Area", {"both": "Whole", "left": "Left", "right": "Right"}, selected="both", inline=True), class_="measurement-segment"),
            ui.div(ui.input_radio_buttons("measurement_color", "Comb color", ("white", "brown", "black"), selected="white", inline=True), class_="measurement-segment"),
            *[control(name, label) for name, label in fields],
            control("queen", "Queen cells", maximum=5, step=1),
            ui.input_action_button("measurement_save", "Save measurement", class_="btn-primary submit-once measurement-save"),
            class_="measurement-form",
        )

    @render.ui
    def hierarchy():
        changed()
        selected_apiary = state.record("apiaries", state.selected["apiary"])
        if state.archived_mode and not selected_apiary:
            groups = []
            equipment_types = {row["id"]: row["name"] for row in state.rows("equipment_types", include_all=True)}
            for sheet, level, title, field in (
                ("hives", "hive", "Hives", "name"), ("boxes", "box", "Boxes", "name"),
                ("frames", "frame", "Frames", "name"),
                ("equipment", "equipment", "Equipment", "code"),
            ):
                rows = state.rows(sheet)
                selected_id = state.selected[level]
                groups.append(ui.tags.section(
                    ui.div(ui.span("Archived"), ui.strong(title), ui.tags.small(str(len(rows))), class_="selection-heading"),
                    ui.div(*[script_button(
                        ui.div(ui.strong(row["code"]), ui.tags.small(equipment_types.get(row["equipment_type_id"], "Equipment")), class_="equipment-label") if level == "equipment" else row[field],
                        level, row["id"], f"relational-choice{' is-selected' if row['id'] == selected_id else ''}",
                    ) for row in rows], class_="relational-strip")
                    if rows else ui.p(f"No archived {title.lower()}.", class_="empty-inline"),
                    class_="level relationship-tab archive-inventory-tab",
                ))
            return ui.tags.main(*groups, class_="hierarchy")
        if not selected_apiary:
            return None
        hives = state.rows("hives", parent_apiary_id=selected_apiary["id"])
        selected_hive = state.record("hives", state.selected["hive"])
        if state.archived_mode and selected_hive and all(row["id"] != selected_hive["id"] for row in hives):
            hives.insert(0, selected_hive)
        children = [ui.tags.section(
            ui.div(ui.span("Hive"), ui.strong(selected_hive["name"] if selected_hive else "Choose a hive"), class_="selection-heading"),
            ui.div(*[
                script_button(
                    ui.div(
                        ui.strong(row["name"]),
                        ui.tags.small(f"{len(state.rows('boxes', parent_hive_id=row['id']))} box | {len(state.rows('equipment', parent_hive_id=row['id']))} equip"),
                        class_="hive-choice-label",
                    ), "hive", row["id"],
                    f"relational-choice status-{row['status']}{' is-selected' if selected_hive and row['id'] == selected_hive['id'] else ''}",
                ) for row in hives
            ], class_="relational-strip") if hives else ui.p("No hives yet. Use Add to create one.", class_="empty-inline"),
            class_="level relationship-tab hive-tab",
        )]
        if selected_hive:
            boxes = state.rows("boxes", parent_hive_id=selected_hive["id"])
            equipment = state.rows("equipment", parent_hive_id=selected_hive["id"])
            selected_box = state.record("boxes", state.selected["box"])
            selected_equipment = state.record("equipment", state.selected["equipment"])
            if state.archived_mode and selected_box and all(row["id"] != selected_box["id"] for row in boxes):
                boxes.insert(0, selected_box)
            if state.archived_mode and selected_equipment and all(row["id"] != selected_equipment["id"] for row in equipment):
                equipment.insert(0, selected_equipment)
            children[0].append(ui.div(
                ui.div("Boxes", class_="contents-label"),
                ui.div(
                    ui.span("Bottom", class_="stack-end stack-bottom"),
                    ui.div(*[
                        script_button(
                            row["name"], "box", row["id"],
                            f"box-choice{' is-selected' if selected_box and row['id'] == selected_box['id'] else ''}",
                            data_reorder_level="box", data_reorder_parent=row["parent_hive_id"], data_reorder_position=row["position"], title="Long press to reorder box",
                        ) for row in boxes
                    ], class_="relational-strip boxes"),
                    ui.span("Top", class_="stack-end stack-top"),
                    class_="stack-selector",
                ) if boxes or equipment else ui.p("No boxes or equipment yet. Use Add to create one.", class_="empty-inline"),
                class_="hive-contents-inline",
            ))
            if not selected_box:
                equipment_types = {row["id"]: row["name"] for row in state.rows("equipment_types", include_all=True)}
                children.append(ui.tags.section(
                    ui.div(ui.span(f"Equipment · {len(equipment)}"), ui.strong(selected_equipment["code"] if selected_equipment else "None"), class_="selection-heading"),
                    ui.div(*[script_button(
                        ui.div(ui.strong(row["code"]), ui.tags.small(equipment_types.get(row["equipment_type_id"], "Equipment")), class_="equipment-label"),
                        "equipment", row["id"], f"equipment-choice{' is-selected' if selected_equipment and row['id'] == selected_equipment['id'] else ''}",
                    ) for row in equipment], class_="relational-strip") if equipment else ui.p("No equipment in this hive."),
                    class_="level relationship-tab equipment-tab",
                ))
            if selected_box:
                frames = state.rows("frames", parent_box_id=selected_box["id"])
                selected_frame = state.record("frames", state.selected["frame"])
                if state.archived_mode and selected_frame and all(row["id"] != selected_frame["id"] for row in frames):
                    frames.insert(0, selected_frame)
                children.append(ui.tags.section(
                    ui.div(ui.span("Box"), ui.strong(selected_box["name"]), ui.tags.small(f"{box_type_label(selected_box['type'])} · {selected_box['max_frames']}-frame"), class_="selection-heading"),
                    ui.div(
                        ui.span("Left", class_="stack-end frame-left"),
                        ui.div(*[
                            script_button(
                                row["name"], "frame", row["id"],
                                f"frame-choice{' over-capacity' if row['position'] >= selected_box['max_frames'] else ''}{' is-selected' if selected_frame and row['id'] == selected_frame['id'] else ''}",
                                data_reorder_level="frame", data_reorder_parent=row["parent_box_id"], data_reorder_position=row["position"], title="Long press to reorder frame",
                            ) for row in frames
                        ], class_="relational-strip frames"),
                        ui.span("Right", class_="stack-end frame-right"),
                        class_="frame-selector",
                    ) if frames else ui.p("No frames yet. Use Add to create one.", class_="empty-inline"),
                    class_="level relationship-tab box-tab",
                ))
                if selected_frame:
                    past_measurements = measurement_cards(state.rows("measurements", include_all=True, parent_frame_id=selected_frame["id"]))
                    frame_archived = state._archived("frames", selected_frame)
                    children.append(ui.tags.section(
                        ui.div(ui.span("Frame"), ui.strong(selected_frame["name"]), class_="selection-heading"),
                        ui.navset_tab(ui.nav_panel("Past", past_measurements), selected="Past") if frame_archived else
                        ui.navset_tab(ui.nav_panel("Measure", measurement_form()), ui.nav_panel("Past", past_measurements), selected="Measure"),
                        class_="level relationship-tab frame-tab",
                    ))
        return ui.tags.main(*children, class_="hierarchy")

    def measurement_cards(rows):
        rows = sorted(rows, key=lambda row: row["created_at"], reverse=True)
        if not rows:
            return ui.p("No measurements yet.", class_="empty-inline")
        excluded = {"id", "parent_frame_id", "scope", "comb_color", "queen_cells", "created_at", "updated_at", "is_archived"}
        percent_fields = [(name, SCHEMAS["measurements"][name].label) for name in SCHEMAS["measurements"] if name not in excluded]
        return ui.div(*[ui.tags.article(
            ui.div(ui.strong(display_time(row["created_at"])), ui.span(f"{row['scope']} · {comb_color_label(row['comb_color'])}"), class_="card-heading"),
            *[ui.div(ui.span(label), ui.tags.progress(value=row[name], max=100), ui.span(f"{row[name]}%"), class_="measure-row") for name, label in percent_fields],
            ui.strong(f"Queen cells: {row['queen_cells']}"), class_="measurement-card",
        ) for row in rows], class_="measurement-history")

    def select_default_equipment(hive_id):
        rows = state.rows("equipment", parent_hive_id=hive_id)
        state.selected["equipment"] = rows[0]["id"] if rows else None

    def select_entity(level, record_id):
        previous_apiary = state.selected["apiary"]
        previous_hive = state.selected["hive"]
        if level == "archive":
            state.archived_mode = True
            for key in state.selected:
                state.selected[key] = None
        elif level == "hive":
            row = state.record("hives", record_id)
            if not row: return
            state.select("apiary", row["parent_apiary_id"]); state.select("hive", record_id); select_default_equipment(record_id)
        elif level == "box":
            row = state.record("boxes", record_id)
            if not row: return
            hive = state.record("hives", row["parent_hive_id"])
            state.select("apiary", hive["parent_apiary_id"]); state.select("hive", hive["id"]); state.select("box", record_id)
        elif level == "frame":
            row = state.record("frames", record_id)
            if not row: return
            box = state.record("boxes", row["parent_box_id"]); hive = state.record("hives", box["parent_hive_id"])
            state.select("apiary", hive["parent_apiary_id"]); state.select("hive", hive["id"]); state.select("box", box["id"]); state.select("frame", record_id)
        elif level == "equipment":
            row = state.record("equipment", record_id)
            if not row: return
            hive = state.record("hives", row["parent_hive_id"])
            if hive:
                state.select("apiary", hive["parent_apiary_id"]); state.select("hive", hive["id"])
            state.selected["box"] = None; state.selected["frame"] = None
            state.selected["equipment"] = record_id
        elif level == "apiary":
            state.archived_mode = False
            state.select("apiary", record_id)
        else:
            return
        if level in ("apiary", "archive") or state.selected["apiary"] != previous_apiary or state.selected["hive"] != previous_hive:
            touch_grid()
        touch()

    @reactive.effect
    @reactive.event(input.entity_selection)
    def _selection():
        selection = json.loads(input.entity_selection())
        if selection.get("source") == "search":
            sheet = {"apiary": "apiaries", "hive": "hives", "box": "boxes", "frame": "frames", "equipment": "equipment"}.get(selection.get("level"))
            row = state.record(sheet, selection.get("id")) if sheet else None
            if row:
                state.archived_mode = state._archived(sheet, row)
        select_entity(selection.get("level"), selection.get("id"))
        if selection.get("source") == "search":
            ui.modal_remove()

    @reactive.effect
    @reactive.event(input.reorder_request)
    async def _reorder_request():
        request_data = json.loads(input.reorder_request())
        level = request_data.get("level")
        sheet = {"box": "boxes", "frame": "frames"}.get(level)
        parent_column = {"box": "parent_hive_id", "frame": "parent_box_id"}.get(level)
        record = state.record(sheet, request_data.get("id")) if sheet else None
        target = state.record(sheet, request_data.get("target")) if sheet else None
        if not record or not target or record["is_archived"] or target["is_archived"] or record[parent_column] != target[parent_column]:
            ui.notification_show("Those items cannot be reordered together.", type="warning"); return
        # Dropping on an occupied position takes that exact position; the
        # transactional move shifts every sibling between the two positions.
        position = target["position"]
        result = move_entities(state.data, sheet, [record["id"]], record[parent_column], position)
        note = audit_note(level, record["id"], f"Moved {level} {record['name']} from position {record['position']} to {position}.", nature="Moved")
        await mutate(changed_rows(state.data, result), [{"sheet": "notes", "rows": [note]}], optimistic=result)

    @reactive.effect
    @reactive.event(input.hive_grid_point)
    def _hive_grid_point():
        grid_point.set(json.loads(input.hive_grid_point()))

    @reactive.effect
    @reactive.event(input.disconnect)
    async def _disconnect():
        await request("disconnect")

    def back():
        previous_apiary = state.selected["apiary"]
        previous_hive = state.selected["hive"]
        if state.selected["frame"]: state.select("box", state.selected["box"])
        elif state.selected["box"]:
            state.select("hive", state.selected["hive"])
            select_default_equipment(state.selected["hive"])
        elif state.selected["hive"]: state.select("apiary", state.selected["apiary"])
        else: state.select("apiary", None)
        if state.selected["apiary"] != previous_apiary or state.selected["hive"] != previous_hive:
            touch_grid()
        touch()

    def summary():
        apiary = state.record("apiaries", state.selected["apiary"])
        if not apiary or state.archived_mode:
            ui.notification_show("Select an active apiary to view its summary.", type="warning"); return
        hives = state.rows("hives", parent_apiary_id=apiary["id"])
        hive_by_id = {row["id"]: row for row in hives}
        hive_ids = {row["id"] for row in hives}
        boxes = [row for row in state.rows("boxes") if row["parent_hive_id"] in hive_ids]
        box_by_id = {row["id"]: row for row in boxes}
        box_ids = {row["id"] for row in boxes}
        frames = [row for row in state.rows("frames") if row["parent_box_id"] in box_ids]
        equipment = [row for row in state.rows("equipment") if row["parent_hive_id"] in hive_ids]
        equipment_types = {row["id"]: row["name"] for row in state.rows("equipment_types", include_all=True)}

        def owner(hive):
            return hive.get("owner") or "Unassigned"

        def summary_list(values):
            return ui.tags.ul(*[ui.tags.li(ui.span(label), ui.strong(str(count))) for label, count in sorted(values.items())], class_="summary-list") if values else ui.p("None", class_="empty-inline")

        def summary_group(title, values):
            return ui.div(ui.strong(title), summary_list(values), class_="summary-section")

        hive_inventory = []
        for hive in sorted(hives, key=lambda row: row["name"].casefold()):
            hive_boxes = [row for row in boxes if row["parent_hive_id"] == hive["id"]]
            hive_box_ids = {row["id"] for row in hive_boxes}
            hive_frames = sum(row["parent_box_id"] in hive_box_ids for row in frames)
            hive_equipment = sum(row["parent_hive_id"] == hive["id"] for row in equipment)
            hive_inventory.append(ui.tags.li(ui.span(hive["name"]), ui.strong(f"{len(hive_boxes)} box · {hive_frames} frame · {hive_equipment} equip")))

        selected_hive = state.selected["hive"] if state.selected["hive"] in hive_ids else next(iter(hive_ids), None)
        ui.modal_show(ui.modal(
            ui.navset_tab(
                ui.nav_panel(
                    "Apiary map",
                    ui.input_radio_buttons("summary_entity", "Count on map", {"hive": "Hives", "box": "Boxes", "frame": "Frames", "equipment": "Equipment"}, selected="box", inline=True),
                    ui.output_ui("summary_filters"),
                    ui.output_ui("summary_map"),
                ),
                ui.nav_panel(
                    "Hive report",
                    ui.input_select("summary_hive", "Hive", {row["id"]: row["name"] for row in sorted(hives, key=lambda item: item["name"].casefold())}, selected=selected_hive),
                    ui.output_ui("hive_summary_report"),
                ),
                ui.nav_panel(
                    "All totals",
                    ui.div(
                        ui.div(ui.strong(str(len(hives))), ui.span("Hives"), class_="summary-stat"),
                        ui.div(ui.strong(str(len(boxes))), ui.span("Boxes"), class_="summary-stat"),
                        ui.div(ui.strong(str(len(frames))), ui.span("Frames"), class_="summary-stat"),
                        ui.div(ui.strong(str(len(equipment))), ui.span("Equipment"), class_="summary-stat"),
                        class_="summary-totals",
                    ),
                    ui.div(
                        summary_group("Hives by owner", Counter(owner(row) for row in hives)),
                        summary_group("Hives by status", Counter(row["status"].title() for row in hives)),
                        summary_group("Boxes by owner", Counter(owner(hive_by_id[row["parent_hive_id"]]) for row in boxes)),
                        summary_group("Boxes by type", Counter(box_type_label(row["type"]) for row in boxes)),
                        summary_group("Boxes by capacity", Counter(f"{row['max_frames']}-frame" for row in boxes)),
                        summary_group("Boxes by hive status", Counter(hive_by_id[row["parent_hive_id"]]["status"].title() for row in boxes)),
                        summary_group("Frames by owner", Counter(owner(hive_by_id[box_by_id[row["parent_box_id"]]["parent_hive_id"]]) for row in frames)),
                        summary_group("Frames by box type", Counter(box_type_label(box_by_id[row["parent_box_id"]]["type"]) for row in frames)),
                        summary_group("Frames by box capacity", Counter(f"{box_by_id[row['parent_box_id']]['max_frames']}-frame" for row in frames)),
                        summary_group("Equipment by description", Counter(equipment_types.get(row["equipment_type_id"], "Unknown") for row in equipment)),
                        summary_group("Equipment by owner", Counter(owner(hive_by_id[row["parent_hive_id"]]) for row in equipment)),
                        summary_group("Equipment by hive status", Counter(hive_by_id[row["parent_hive_id"]]["status"].title() for row in equipment)),
                        class_="summary-breakdowns",
                    ),
                    ui.div(ui.strong("Inventory by hive"), ui.tags.ul(*hive_inventory, class_="summary-list") if hive_inventory else ui.p("None"), class_="summary-section summary-inventory"),
                ),
                selected="Apiary map",
            ),
            title=f"{apiary['name']} summary", easy_close=True, footer=None, size="xl",
        ))

    def summary_input(name, default="all"):
        try:
            return input[name]() or default
        except (AttributeError, KeyError):
            return default

    @render.ui
    def summary_filters():
        apiary = state.record("apiaries", state.selected["apiary"])
        if not apiary:
            return None
        hives = state.rows("hives", parent_apiary_id=apiary["id"])
        owners = sorted({row.get("owner") or "Unassigned" for row in hives}, key=str.casefold)
        types = sorted(state.rows("equipment_types", include_all=True), key=lambda row: row["name"].casefold())
        return ui.div(
            ui.input_select("summary_owner", "Owner", {"all": "All owners", **{value: value for value in owners}}),
            ui.input_select("summary_status", "Hive status", {"all": "All statuses", "active": "Active", "inactive": "Inactive", "storage": "Storage"}),
            ui.input_select("summary_box_type", "Box type", {"all": "All types", "normal": "Medium", "deep": "Deep"}),
            ui.input_select("summary_capacity", "Box capacity", {"all": "All capacities", "8": "8-frame", "10": "10-frame"}),
            ui.input_select("summary_equipment_type", "Equipment description", {"all": "All equipment", **{row["id"]: row["name"] for row in types}}),
            class_="summary-filter-grid",
        )

    @render.ui
    def summary_map():
        apiary = state.record("apiaries", state.selected["apiary"])
        if not apiary or state.archived_mode:
            return None
        entity = summary_input("summary_entity", "box")
        hives = state.rows("hives", parent_apiary_id=apiary["id"])
        hive_by_id = {row["id"]: row for row in hives}
        hive_ids = set(hive_by_id)
        owner_filter = summary_input("summary_owner")
        status_filter = summary_input("summary_status")

        def matching_hive(hive):
            owner = hive.get("owner") or "Unassigned"
            return (owner_filter == "all" or owner == owner_filter) and (status_filter == "all" or hive["status"] == status_filter)

        counts = Counter()
        if entity == "hive":
            counts.update({hive["id"]: 1 for hive in hives if matching_hive(hive)})
        else:
            boxes = [row for row in state.rows("boxes") if row["parent_hive_id"] in hive_ids]
            box_type = summary_input("summary_box_type")
            capacity = summary_input("summary_capacity")
            boxes = [row for row in boxes if matching_hive(hive_by_id[row["parent_hive_id"]]) and (box_type == "all" or row["type"] == box_type) and (capacity == "all" or str(row["max_frames"]) == capacity)]
            if entity == "box":
                counts.update(row["parent_hive_id"] for row in boxes)
            elif entity == "frame":
                box_by_id = {row["id"]: row for row in boxes}
                counts.update(box_by_id[row["parent_box_id"]]["parent_hive_id"] for row in state.rows("frames") if row["parent_box_id"] in box_by_id)
            else:
                equipment_type = summary_input("summary_equipment_type")
                equipment = [row for row in state.rows("equipment") if row["parent_hive_id"] in hive_ids and matching_hive(hive_by_id[row["parent_hive_id"]])]
                counts.update(row["parent_hive_id"] for row in equipment if equipment_type == "all" or row["equipment_type_id"] == equipment_type)
        units = {"hive": "hives", "box": "boxes", "frame": "frames", "equipment": "equipment"}
        total = sum(counts.values())
        matched_hives = sum(bool(counts.get(hive["id"])) for hive in hives)
        return ui.div(
            ui.div(ui.strong(str(total)), ui.span(f"matching {units[entity]} across {matched_hives} hives"), class_="summary-map-total"),
            summary_grid(apiary, hives, counts, units[entity]),
            class_="summary-map-view",
        )

    @render.ui
    def hive_summary_report():
        apiary = state.record("apiaries", state.selected["apiary"])
        if not apiary:
            return None
        hives = state.rows("hives", parent_apiary_id=apiary["id"])
        hive_id = summary_input("summary_hive", state.selected["hive"])
        hive = next((row for row in hives if row["id"] == hive_id), None)
        if not hive:
            return ui.p("No hives in this apiary.", class_="empty-inline")
        boxes = sorted(state.rows("boxes", parent_hive_id=hive["id"]), key=lambda row: row["position"], reverse=True)
        box_ids = {row["id"] for row in boxes}
        frames = [row for row in state.rows("frames") if row["parent_box_id"] in box_ids]
        frames_by_box = {box["id"]: sorted((row for row in frames if row["parent_box_id"] == box["id"]), key=lambda row: row["position"]) for box in boxes}
        equipment = state.rows("equipment", parent_hive_id=hive["id"])
        equipment_types = {row["id"]: row["name"] for row in state.rows("equipment_types", include_all=True)}
        measurements = state.rows("measurements", include_all=True)
        latest = {}
        for row in measurements:
            key = (row["parent_frame_id"], row["scope"])
            if key not in latest or parse_utc(row["created_at"]) > parse_utc(latest[key]["created_at"]):
                latest[key] = row
        measured_frame_ids = {frame_id for frame_id, _ in latest}
        comb_fields = (
            ("drone_cells", "Drone"), ("capped_brood_cells", "Capped brood"),
            ("uncapped_brood_cells", "Uncapped brood"), ("capped_honey_cells", "Capped honey"),
            ("uncapped_honey_cells", "Uncapped honey"), ("pollen_cells", "Pollen"),
        )

        def stacked_bar(label, values, remainder_label, remainder_kind):
            total = sum(value for _, _, value in values)
            scale = 100 / total if total > 100 else 1
            segments = [(kind, name, value * scale, value) for kind, name, value in values if value]
            remainder = max(0, 100 - sum(value for _, _, value, _ in segments))
            if remainder:
                segments.append((remainder_kind, remainder_label, remainder, remainder))
            return ui.div(
                ui.span(label, class_="compact-plot-label"),
                ui.div(
                    *[ui.span(
                        ui.strong(f"{round(relative)}%"),
                        class_=f"stacked-segment segment-{kind}{' is-small' if relative < 10 else ''}",
                        style=f"height:{relative}%", title=f"{name}: {round(relative, 1)}% of bar" + (f" ({original}% recorded)" if scale != 1 else ""),
                    ) for kind, name, relative, original in segments],
                    class_="compact-frame-track stacked-frame-track",
                ),
                class_="compact-frame-plot",
            )

        def scope_visual(scope, measurement):
            bees = min(100, measurement["bees"]) if measurement else 0
            comb_values = [(name, label, measurement[name] if measurement else 0) for name, label in comb_fields]
            queen_cells = measurement["queen_cells"] if measurement else 0
            return ui.div(
                ui.strong(scope, class_="frame-scope-label"),
                ui.div(
                    stacked_bar("Bees", (("bees", "Bees", bees),), "No bees", "no-bees"),
                    stacked_bar("Comb", tuple((name.replace("_cells", "").replace("_", "-"), label, value) for name, label, value in comb_values), "Empty / no comb", "empty-comb"),
                    class_="frame-scope-bars",
                ),
                ui.div(comb_color_label(measurement["comb_color"]) if measurement else "No data", class_="compact-frame-meta"),
                ui.div(f"{queen_cells} queen {'cell' if queen_cells == 1 else 'cells'}", class_="frame-queen-cells") if queen_cells else None,
                class_="frame-scope-report",
            )

        def frame_visual(frame):
            left = latest.get((frame["id"], "left"))
            right = latest.get((frame["id"], "right"))
            scopes = [("Left", left), ("Right", right)] if left or right else [("Whole", latest.get((frame["id"], "both")))]
            recorded = [measurement for _, measurement in scopes if measurement]
            latest_measurement = max(recorded, key=lambda row: parse_utc(row["created_at"])) if recorded else None
            return ui.tags.article(
                ui.div(ui.strong(frame["name"]), ui.span(display_time(max(recorded, key=lambda row: parse_utc(row["created_at"]))["created_at"]) if recorded else "Not measured"), class_="hive-frame-heading"),
                ui.div(*[scope_visual(scope, measurement) for scope, measurement in scopes], class_="frame-scope-list"),
                class_=f"hive-frame-report{' is-unmeasured' if not recorded else ''}",
                style=f"--frame-comb-color:{comb_color_hex(latest_measurement['comb_color'])}" if latest_measurement else None,
            )

        def plot_legend():
            def group(title, items, class_name):
                return ui.div(
                    ui.strong(title),
                    ui.div(*[
                        ui.tags.button(
                            ui.tags.i(class_=f"legend-swatch segment-{kind}"), ui.span(label),
                            type="button", class_="legend-toggle is-active", data_chart_series=kind, aria_pressed="true",
                        ) for kind, label in items
                    ]),
                    class_=f"legend-group {class_name}",
                )
            return ui.div(
                group("Bee coverage", (("bees", "Bees"), ("no-bees", "No bees")), "legend-bees"),
                group("Comb composition", (("drone", "Drone"), ("capped-brood", "Capped brood"), ("uncapped-brood", "Uncapped brood"), ("capped-honey", "Capped honey"), ("uncapped-honey", "Uncapped honey"), ("pollen", "Pollen"), ("empty-comb", "Empty / no comb")), "legend-comb"),
                ui.tags.button("Show all", type="button", class_="legend-reset", data_chart_reset="true"),
                class_="frame-plot-legend",
            )

        box_reports = [ui.tags.section(
            ui.div(
                ui.div(ui.span(f"Position {box['position']}"), ui.strong(box["name"])),
                ui.span(f"{box_type_label(box['type'])} · {box['max_frames']}-frame · {len(frames_by_box[box['id']])} frames"),
                class_="hive-box-heading",
            ),
            plot_legend(),
            ui.div(
                *[frame_visual(frame) for frame in frames_by_box[box["id"]]],
                class_=f"hive-frame-list{' few-frames' if len(frames_by_box[box['id']]) < 5 else ''}",
                style=f"--frame-count:{len(frames_by_box[box['id']])};--mobile-frame-count:{min(5, len(frames_by_box[box['id']]))}",
            ) if frames_by_box[box["id"]] else ui.p("No frames", class_="empty-inline"),
            class_="hive-box-report",
        ) for box in boxes]
        return ui.div(
            ui.div(
                ui.div(ui.strong(hive["name"]), ui.span(hive["status"].title()), class_="hive-report-title"),
                ui.span(f"Owner: {hive.get('owner') or 'Unassigned'} · Grid {column_label(hive['grid_column'])}{hive['grid_row']}"),
                class_="hive-report-header",
            ),
            ui.div(
                ui.div(ui.strong(str(len(boxes))), ui.span("Boxes"), class_="summary-stat"),
                ui.div(ui.strong(str(len(frames))), ui.span("Frames"), class_="summary-stat"),
                ui.div(ui.strong(str(len(equipment))), ui.span("Equipment"), class_="summary-stat"),
                ui.div(ui.strong(str(sum(frame["id"] in measured_frame_ids for frame in frames))), ui.span("Measured frames"), class_="summary-stat"),
                class_="summary-totals",
            ),
            ui.div(ui.strong("Equipment"), ui.div(*[ui.span(f"{row['code']} · {equipment_types.get(row['equipment_type_id'], 'Unknown')}", class_="hive-equipment-chip") for row in equipment], class_="hive-equipment-list") if equipment else ui.p("None", class_="empty-inline"), class_="hive-report-equipment"),
            ui.div("TOP", class_="hive-stack-marker hive-stack-top"),
            *box_reports,
            ui.div("BOTTOM", class_="hive-stack-marker hive-stack-bottom"),
            class_="hive-summary-report",
        )

    def search():
        results = []
        equipment_types = {row["id"]: row["name"] for row in state.rows("equipment_types", include_all=True)}
        hives = {row["id"]: row for row in state.rows("hives", include_all=True)}
        for sheet, level, field in (("hives", "hive", "name"), ("boxes", "box", "name"), ("frames", "frame", "name"), ("equipment", "equipment", "code")):
            for row in state.rows(sheet, include_all=True):
                label = str(row[field]); archived = state._archived(sheet, row)
                description = equipment_types.get(row["equipment_type_id"], "") if level == "equipment" else ""
                if level == "box":
                    hive = hives.get(row["parent_hive_id"], {})
                    box_type = box_type_label(row["type"])
                    description = f"{box_type} {row['max_frames']}-frame {hive.get('status', '')}"
                results.append(ui.tags.button(
                    ui.span(label), ui.tags.small(f"{level.title()} · {description}" if description else level.title()), type="button", class_="search-result",
                    data_level=level, data_id=row["id"], data_search_text=f"{label} {level} {description}".casefold(),
                    data_entity_type=level, data_entity_archived=str(archived).lower(), hidden=archived,
                ))
        ui.modal_show(ui.modal(
            ui.tags.input(type="search", id="entity-search-filter", class_="form-control", placeholder="Type a name, code, or type…", aria_label="Filter entities"),
            ui.div(*[
                ui.tags.button(level.title(), type="button", class_="search-type-toggle is-active", data_search_type=level, aria_pressed="true")
                for level in ("hive", "box", "frame", "equipment")
            ], class_="search-type-filters", aria_label="Result types"),
            ui.tags.select(ui.tags.option("Active", value="active"), ui.tags.option("Archived", value="archived"), ui.tags.option("Active and Archived", value="all"), id="search-status-filter", class_="form-select search-status-filter", aria_label="Archive status"),
            ui.div(*results, class_="search-results"), ui.p("No matching names or types.", class_="search-empty", hidden=True),
            title="Search", easy_close=True, footer=None,
        ))

    def add():
        if state.archived_mode:
            ui.notification_show("Switch to Active to add records.", type="message"); return
        level, _, _ = selected_record()
        if level == "frame": ui.notification_show("Use Record measurement in the Frame tab.", type="message")
        elif level == "box": show_frame_form()
        elif level == "hive": show_hive_child_form()
        elif level == "apiary": show_hive_form()
        else: show_apiary_form()

    def show_apiary_form():
        ui.modal_show(ui.modal(
            ui.input_text("apiary_name", "Apiary name", placeholder="20 characters maximum"),
            ui.div(ui.input_numeric("apiary_columns", "Columns (letters)", 8, min=1, max=26), ui.input_numeric("apiary_rows", "Rows (numbers)", 6, min=1, max=50), class_="dimension-fields"),
            ui.input_radio_buttons("apiary_up", "Cardinal direction at the top", ("North", "East", "South", "West"), selected="North", inline=True),
            ui.input_action_button("apiary_save", "Create apiary", class_="btn-primary submit-once"), title="Add apiary", easy_close=True, footer=None,
        ))

    @reactive.effect
    @reactive.event(input.apiary_save)
    async def _apiary_save():
        name = input.apiary_name().strip(); columns = int(input.apiary_columns()); rows = int(input.apiary_rows())
        if not name or len(name) > 20 or name.casefold() in {value.casefold() for value in active_used_names()}:
            ui.notification_show("Use a unique apiary name of 1–20 characters.", type="error"); return
        if not (1 <= columns <= 26 and 1 <= rows <= 50):
            ui.notification_show("Use 1–26 columns and 1–50 rows.", type="error"); return
        record = base_record(name=name, grid_columns=columns, grid_rows=rows, up_direction=input.apiary_up())
        await append("apiaries", [record], "name", name); state.selected["apiary"] = record["id"]

    def show_hive_form():
        apiary = state.record("apiaries", state.selected["apiary"])
        if not apiary: return
        grid_point.set(None)
        hives = state.rows("hives", parent_apiary_id=apiary["id"])
        ui.modal_show(ui.modal(
            ui.input_text("hive_name", "Hive name", value=plant_name(active_used_names())),
            ui.input_selectize("hive_owner", "Owner", owner_choices(), options={"create": True, "placeholder": "Select or enter an owner"}),
            ui.p("Choose an empty grid cell.", class_="grid-instruction"), apiary_grid(apiary, hives, editor=True),
            ui.input_select("hive_status", "Status", ("active", "inactive", "storage")), ui.input_action_button("hive_save", "Save hive", class_="btn-primary submit-once"), title="Add hive", easy_close=True, footer=None,
        ))

    @reactive.effect
    @reactive.event(input.hive_save)
    async def _hive_save():
        apiary = state.record("apiaries", state.selected["apiary"]); name = input.hive_name().strip(); point = grid_point.get()
        if not name or name.casefold() in {value.casefold() for value in active_used_names()}:
            ui.notification_show("Hive name must be unique.", type="error"); return
        if not point:
            ui.notification_show("Choose an empty grid cell.", type="error"); return
        occupied = {(row["grid_column"], row["grid_row"]) for row in state.rows("hives", parent_apiary_id=apiary["id"])}
        if (point["grid_column"], point["grid_row"]) in occupied:
            ui.notification_show("That grid cell already contains a hive.", type="error"); return
        record = base_record(parent_apiary_id=apiary["id"], owner=(input.hive_owner() or "").strip() or None, name=name, grid_column=point["grid_column"], grid_row=point["grid_row"], status=input.hive_status())
        await append("hives", [record], "name", name); state.selected["hive"] = record["id"]

    def show_hive_child_form():
        ui.modal_show(ui.modal(
            ui.p("What do you want to add?"),
            ui.input_action_button("choose_add_boxes", "Boxes", class_="btn-primary w-100"),
            ui.input_action_button("choose_add_equipment", "Equipment", class_="btn-outline-primary w-100 mt-2"),
            title="Add", easy_close=True, footer=None,
        ))

    @reactive.effect
    @reactive.event(input.choose_add_boxes)
    def _choose_boxes():
        position = len(state.rows("boxes", parent_hive_id=state.selected["hive"]))
        ui.modal_show(ui.modal(ui.input_numeric("box_quantity", "Quantity", 1, min=1, max=80), ui.input_select("box_capacity", "Capacity", {8: "8 frames", 10: "10 frames"}, selected=10), ui.input_select("box_type", "Type", {"normal": "Medium", "deep": "Deep"}), ui.input_numeric("box_position", "Starting position", position, min=0), ui.input_action_button("box_save", "Create boxes", class_="btn-primary submit-once"), title="Add boxes", easy_close=True, footer=None))

    @reactive.effect
    @reactive.event(input.box_save)
    async def _box_save():
        quantity = int(input.box_quantity()); used = active_used_names(); now = utc_now(); records = []
        for offset in range(quantity):
            code = box_code(used); used.add(code)
            records.append({"id": new_id(), "parent_hive_id": state.selected["hive"], "position": int(input.box_position()) + offset, "max_frames": int(input.box_capacity()), "type": input.box_type(), "name": code, "created_at": now, "updated_at": now, "is_archived": False})
        original = state.data["boxes"]
        shifted = insert_positions(original, "parent_hive_id", state.selected["hive"], int(input.box_position()), quantity)
        updates = [{"sheet": "boxes", "id": before["id"], "values": {"position": after["position"]}} for before, after in zip(original.sort("id").to_dicts(), shifted.sort("id").to_dicts()) if before["position"] != after["position"]]
        await mutate(updates, [{"sheet": "boxes", "rows": records}])

    def show_frame_form():
        ui.modal_show(ui.modal(ui.input_numeric("frame_quantity", "Quantity", 1, min=1, max=100), ui.input_numeric("frame_position", "Starting position", len(state.rows("frames", parent_box_id=state.selected["box"])), min=0), ui.input_action_button("frame_save", "Create frames", class_="btn-primary submit-once"), title="Add frames", easy_close=True, footer=None))

    @reactive.effect
    @reactive.event(input.frame_save)
    async def _frame_save():
        quantity = int(input.frame_quantity()); used = active_used_names(); now = utc_now(); records = []
        for offset in range(quantity):
            code = frame_code(used); used.add(code)
            records.append({"id": new_id(), "parent_box_id": state.selected["box"], "position": int(input.frame_position()) + offset, "name": code, "created_at": now, "updated_at": now, "is_archived": False})
        original = state.data["frames"]
        shifted = insert_positions(original, "parent_box_id", state.selected["box"], int(input.frame_position()), quantity)
        updates = [{"sheet": "frames", "id": before["id"], "values": {"position": after["position"]}} for before, after in zip(original.sort("id").to_dicts(), shifted.sort("id").to_dicts()) if before["position"] != after["position"]]
        await mutate(updates, [{"sheet": "frames", "rows": records}])

    @reactive.effect
    @reactive.event(input.choose_add_equipment)
    def _equipment_form():
        names = sorted({row["name"] for row in state.rows("equipment_types")}, key=str.casefold)
        ui.modal_show(ui.modal(
            ui.input_selectize("equipment_name", "Name", names, options={"create": True, "placeholder": "Select or enter equipment"}),
            ui.input_numeric("equipment_quantity", "Quantity", 1, min=1, max=200),
            ui.input_action_button("equipment_save", "Add equipment", class_="btn-primary submit-once"),
            title="Add equipment", easy_close=True, footer=None,
        ))

    @reactive.effect
    @reactive.event(input.equipment_save)
    async def _equipment_save():
        name = (input.equipment_name() or "").strip()
        if not name:
            ui.notification_show("Select or enter an equipment name.", type="error"); return
        existing = next((row for row in state.rows("equipment_types") if row["name"].casefold() == name.casefold()), None)
        equipment_type = existing or base_record(name=name)
        used = active_used_names(); now = utc_now(); records = []
        for _ in range(int(input.equipment_quantity())):
            code = equipment_code(used); used.add(code)
            records.append(base_record(code=code, equipment_type_id=equipment_type["id"], parent_hive_id=state.selected["hive"]))
        appends = [] if existing else [{"sheet": "equipment_types", "rows": [equipment_type]}]
        appends.append({"sheet": "equipment", "rows": records})
        await mutate(appends=appends)
        state.selected["equipment"] = records[0]["id"]

    @reactive.effect
    @reactive.event(input.measurement_save)
    async def _measurement_save():
        nonlocal last_measurement_save
        frame_id = state.selected["frame"]
        frame = state.record("frames", frame_id)
        if not frame or state._archived("frames", frame):
            ui.notification_show("Archived frames are read-only.", type="warning"); return
        values = {name: int(input[f"measurement_{name}"]()) for name, field in SCHEMAS["measurements"].items() if field.maximum == 100}
        queen_cells = int(input.measurement_queen())
        color = input.measurement_color()
        signature = (frame_id, input.measurement_scope(), color, *values.values(), queen_cells)
        now = monotonic()
        if signature == last_measurement_save[0] and now - last_measurement_save[1] < 5:
            ui.notification_show("That measurement was already saved.", type="warning"); return
        if state.busy:
            ui.notification_show("A save is already in progress.", type="message"); return
        last_measurement_save = (signature, now)
        await append("measurements", [base_record(parent_frame_id=frame_id, scope=input.measurement_scope(), comb_color=color, **values, queen_cells=queen_cells)])

    def notes():
        level, _, record = selected_record(); target_level = level if level in ("apiary", "hive", "box", "frame", "equipment") else None
        rows = state.rows("notes", include_all=True)
        rows.sort(key=lambda row: (row["archived"], -(parse_utc(row["archived_at"] or row["created_at"]).timestamp())))
        labels = {}
        for sheet, kind, field in (("apiaries", "apiary", "name"), ("hives", "hive", "name"), ("boxes", "box", "name"), ("frames", "frame", "name"), ("equipment", "equipment", "code")):
            labels.update({f"{kind}:{row['id']}": row[field] for row in state.rows(sheet, include_all=True)})
        nature_counts = state.data["notes"].group_by("nature").len().sort("len", descending=True)["nature"].to_list() if state.data["notes"].height else []
        natures = nature_counts + [value for value in SCHEMAS["notes"]["nature"].choices if value not in nature_counts]
        table_rows = []
        for row in rows:
            target_key = f"{row['target_type']}:{row['target_id']}"
            target_label = labels.get(target_key, "Unknown")
            status_label = "Archived" if row["archived"] else "Active"
            table_rows.append(ui.tags.tr(
                ui.tags.td(row["nature"]),
                ui.tags.td(ui.strong(target_label), ui.tags.small(row["target_type"].title())),
                ui.tags.td(row["description"]),
                ui.tags.td(display_time(row["archived_at"] or row["created_at"])),
                ui.tags.td(status_label),
                ui.tags.td(ui.tags.button("Edit", type="button", class_="note-edit", data_note_id=row["id"])),
                data_note_current=str(bool(target_level and row["target_type"] == target_level and row["target_id"] == record["id"])).lower(),
                data_note_search=f"{row['nature']} {row['target_type']} {target_label} {row['description']} {status_label}".casefold(),
            ))
        read_tab = ui.div(
            ui.div(
                ui.tags.input(type="search", id="notes-table-filter", class_="form-control", placeholder="Filter notes…", aria_label="Filter notes"),
                ui.tags.select(
                    ui.tags.option("Current selection", value="current", selected=bool(target_level)),
                    ui.tags.option("All visible notes", value="all", selected=not bool(target_level)),
                    id="notes-scope-filter", class_="form-select", disabled=not bool(target_level),
                ), class_="notes-filters",
            ),
            ui.div(ui.tags.table(
                ui.tags.thead(ui.tags.tr(*[ui.tags.th(label) for label in ("Type", "Target", "Note", "Date", "Status", "")])),
                ui.tags.tbody(*table_rows), class_="notes-table",
            ), class_="notes-table-wrap") if rows else ui.p("No visible notes."),
            ui.p("No notes match these filters.", class_="notes-empty", hidden=True),
        )
        add_tab = ui.div(
            ui.div(ui.span("Saving note to"), ui.strong(f"{target_level.title()}: {record.get('name', record.get('code'))}"), class_="note-target") if target_level else None,
            ui.input_select("note_nature", "Nature", natures),
            ui.input_text_area("note_description", "Description", rows=4),
            ui.input_action_button("note_save", "Add note", class_="btn-primary submit-once", disabled=not bool(target_level)),
            ui.p("Select an apiary, hive, box, frame, or equipment item before adding a note.", class_="grid-instruction") if not target_level else None,
        )
        ui.modal_show(ui.modal(
            ui.navset_tab(ui.nav_panel("Read notes", read_tab), ui.nav_panel("Add note", add_tab), selected="Add note"),
            title=f"Notes · {record.get('name', record.get('code', 'All')) if record else 'All'}", easy_close=True, footer=None, size="l",
        ))

    @reactive.effect
    @reactive.event(input.note_save)
    async def _note_save():
        level, _, record = selected_record(); description = input.note_description().strip()
        if level not in ("apiary", "hive", "box", "frame", "equipment") or not description:
            ui.notification_show("Choose a target and enter a description.", type="error"); return
        await append("notes", [base_record(target_type=level, target_id=record["id"], nature=input.note_nature(), description=description, archived=False, archived_at=None)], context={"reopen_notes": True})

    @reactive.effect
    @reactive.event(input.note_action)
    def _note_action():
        row = state.record("notes", input.note_action())
        if not row: return
        editing_note.set(row["id"])
        ui.modal_show(ui.modal(
            ui.input_select("edit_note_nature", "Nature", SCHEMAS["notes"]["nature"].choices, selected=row["nature"]),
            ui.input_text_area("edit_note_description", "Description", value=row["description"], rows=4),
            ui.input_action_button("edit_note_save", "Save", class_="btn-primary submit-once"),
            ui.input_action_button("edit_note_archive", "Archive", class_="btn-outline-secondary", disabled=row["archived"]),
            title="Edit note", easy_close=True, footer=None,
        ))

    @reactive.effect
    @reactive.event(input.edit_note_save)
    async def _edit_note_save():
        description = input.edit_note_description().strip()
        if not description:
            ui.notification_show("Description is required.", type="error"); return
        await update("notes", editing_note.get(), {"nature": input.edit_note_nature(), "description": description})

    @reactive.effect
    @reactive.event(input.edit_note_archive)
    async def _edit_note_archive():
        await update("notes", editing_note.get(), {"archived": True, "archived_at": utc_now()})

    @render.ui
    def move_hive_grid():
        move_changed()
        context = contexts.get("move_context") or {}
        if context.get("level") != "hive":
            return None
        destination_id = input.move_destination()
        if not destination_id:
            return ui.p("Hives will be placed in Archived.", class_="grid-instruction")
        apiary = state.record("apiaries", destination_id)
        if not apiary:
            return None
        hives = [row for row in state.rows("hives", include_all=True, parent_apiary_id=destination_id) if not state._archived("hives", row)]
        return ui.div(
            ui.p("Choose the starting grid cell.", class_="grid-instruction"),
            apiary_grid(apiary, hives, editor=True, selected_point=grid_point.get(), editing_hive_ids=context.get("selection", [])),
            class_="move-hive-grid",
        )

    @render.ui
    def workflow_panel():
        changed()
        kind = workflow_kind.get()
        if kind == "move":
            context = contexts.get("move_context") or {}
            record = state.record(context.get("sheet", "boxes"), context.get("id"))
            if not record:
                return None
            level, sheet = context["level"], context["sheet"]
            parent_sheet = "apiaries" if level == "hive" else "hives" if level in ("box", "equipment") else "boxes"
            parent_column = "parent_apiary_id" if level == "hive" else "parent_hive_id" if level in ("box", "equipment") else "parent_box_id"
            candidates = [row for row in state.rows(sheet, include_all=True) if state._archived(sheet, row) == state.archived_mode]
            parent_names = {row["id"]: row["name"] for row in state.rows(parent_sheet, include_all=True)}
            parents = {"": "Archived", **{row["id"]: row["name"] for row in state.rows(parent_sheet, include_all=True) if not state._archived(parent_sheet, row)}}
            body = [
                ui.tags.input(type="search", id="move-search-filter", class_="form-control", placeholder=f"Search {level}s to add…", aria_label=f"Search {level}s"),
                ui.div(*[ui.tags.button(
                    ui.span(row.get("name", row.get("code"))), ui.tags.small(parent_names.get(row[parent_column], "Archived")),
                    type="button", class_=f"move-option{' is-selected' if row['id'] in context.get('selection', []) else ''}",
                    data_move_id=row["id"], data_move_search=f"{row.get('name', row.get('code'))} {parent_names.get(row[parent_column], 'archived')}".casefold(),
                ) for row in candidates], class_="move-results"),
                ui.input_select("move_destination", "Destination", parents, selected=record[parent_column] or ""),
            ]
            if level == "hive":
                body.append(ui.output_ui("move_hive_grid"))
            elif level != "equipment":
                body.append(ui.input_numeric("move_position", "Starting position", record["position"], min=0))
            body.append(signal_button("Confirm move", "move_save_signal"))
            title = f"Move {level}"
        elif kind == "edit":
            context = contexts.get("edit_context") or {}
            level = context.get("level")
            record = state.record(context.get("sheet", "apiaries"), context.get("id"))
            if not record:
                return None
            if level == "apiary":
                body = [ui.input_text("edit_apiary_name", "Name", value=record["name"]), ui.div(ui.input_numeric("edit_apiary_columns", "Columns", record["grid_columns"], min=1, max=26), ui.input_numeric("edit_apiary_rows", "Rows", record["grid_rows"], min=1, max=50), class_="dimension-fields"), ui.input_radio_buttons("edit_apiary_up", "Direction above grid", ("North", "East", "South", "West"), selected=record["up_direction"], inline=True)]
            elif level == "hive":
                apiary = state.record("apiaries", record["parent_apiary_id"])
                point = grid_point.get() or {"grid_column": record["grid_column"], "grid_row": record["grid_row"]}
                owners = owner_choices()
                if record.get("owner") and record["owner"] not in owners:
                    owners.append(record["owner"])
                body = [ui.input_text("edit_hive_name", "Name", value=record["name"]), ui.input_selectize("edit_hive_owner", "Owner", owners, selected=record["owner"] or None, options={"create": True, "placeholder": "Select or enter an owner"}), ui.input_select("edit_hive_status", "Status", ("active", "inactive", "storage"), selected=record["status"]), ui.p("Choose a grid cell.", class_="grid-instruction"), apiary_grid(apiary, state.rows("hives", include_all=True, parent_apiary_id=apiary["id"]), editor=True, selected_point=point, editing_hive_id=record["id"])]
            elif level == "box":
                maximum = max(0, len(state.rows("boxes", parent_hive_id=record["parent_hive_id"])) - 1)
                body = [ui.input_text("edit_box_name", "Name", value=record["name"]), ui.input_select("edit_box_type", "Type", {"normal": "Medium", "deep": "Deep"}, selected=record["type"]), ui.input_select("edit_box_capacity", "Capacity", {8: "8 frames", 10: "10 frames"}, selected=record["max_frames"]), position_editor("edit_box_position", record["position"], maximum, "Move toward bottom", "Move toward top")]
            elif level == "frame":
                maximum = max(0, len(state.rows("frames", parent_box_id=record["parent_box_id"])) - 1)
                body = [ui.input_text("edit_frame_name", "Name", value=record["name"]), position_editor("edit_frame_position", record["position"], maximum, "Move earlier", "Move later")]
            elif level == "equipment":
                type_row = state.record("equipment_types", record["equipment_type_id"])
                body = [
                    ui.p(f"Tracking code: {record['code']}", class_="grid-instruction"),
                    ui.input_selectize("edit_equipment_name", "Description", equipment_name_choices(), selected=type_row["name"] if type_row else None, options={"create": True, "placeholder": "Select or enter equipment"}),
                ]
            else:
                return None
            if not state.archived_mode:
                body.append(ui.input_action_button("archive_one", "Archive", class_="btn-outline-danger"))
            body.append(edit_submit_button())
            title = f"Edit {level}"
        else:
            return None
        return ui.div(*body, class_="workflow-body")

    def move():
        level, sheet, record = selected_record()
        if level not in ("hive", "box", "frame", "equipment"):
            ui.notification_show("Select a hive, box, frame, or equipment item to move.", type="warning"); return
        contexts["move_context"] = {"level": level, "sheet": sheet, "id": record["id"], "selection": [record["id"]]}
        workflow_kind.set("move"); touch()
        ui.modal_show(ui.modal(ui.output_ui("workflow_panel"), title=f"Move {level}", easy_close=True, footer=None))

    @reactive.effect
    @reactive.event(input.move_selection)
    def _move_selection():
        context = contexts.get("move_context")
        if context is not None:
            context["selection"] = json.loads(input.move_selection())
            touch_move()

    @reactive.effect
    @reactive.event(input.move_destination)
    def _move_hive_destination():
        context = contexts.get("move_context") or {}
        if context.get("level") != "hive":
            return
        record = state.record("hives", context.get("id"))
        destination_id = input.move_destination() or None
        if record and destination_id == record["parent_apiary_id"]:
            grid_point.set({"grid_column": record["grid_column"], "grid_row": record["grid_row"]})
        else:
            grid_point.set(None)
        touch_move()

    @reactive.effect
    @reactive.event(input.move_save_signal)
    async def _move_save():
        context = contexts.get("move_context") or {}
        ids = context.get("selection") or [context.get("id")]
        destination = input.move_destination() or None
        try:
            if context["level"] == "hive":
                point = grid_point.get()
                if destination and not point:
                    raise ValueError("Choose a destination grid cell.")
                result = move_hives(state.data, ids, destination, point["grid_column"] if point else 1, point["grid_row"] if point else 1)
            else:
                position = int(input.move_position()) if context["level"] != "equipment" else 0
                result = move_entities(state.data, context["sheet"], ids, destination, position)
        except (KeyError, TypeError, ValueError) as error:
            ui.notification_show(str(error), type="error", duration=7); return
        parent_sheet = "apiaries" if context["level"] == "hive" else "hives" if context["level"] in ("box", "equipment") else "boxes"
        destination_record = state.record(parent_sheet, destination)
        destination_name = destination_record["name"] if destination_record else "Archived"
        notes_to_add = []
        for record_id in ids:
            record = state.record(context["sheet"], record_id)
            label = record.get("name", record.get("code", context["level"]))
            notes_to_add.append(audit_note(context["level"], record_id, f"Moved {context['level']} {label} to {destination_name}.", nature="Moved"))
        await mutate(changed_rows(state.data, result), [{"sheet": "notes", "rows": notes_to_add}])
        if destination is None:
            state.archived_mode = True
            for key in state.selected:
                state.selected[key] = None
            touch_grid(); touch()

    def edit():
        level, sheet, record = selected_record()
        if not record:
            ui.notification_show("Select an item first.", type="warning"); return
        contexts["edit_context"] = {"level": level, "sheet": sheet, "id": record["id"]}
        if level == "hive":
            grid_point.set({"grid_column": record["grid_column"], "grid_row": record["grid_row"]})
        workflow_kind.set("edit"); touch()
        ui.modal_show(ui.modal(ui.output_ui("workflow_panel"), title=f"Edit {level}", easy_close=True, footer=None))

    @reactive.effect
    @reactive.event(input.edit_save_payload)
    async def _edit_save():
        context = contexts.get("edit_context") or {}
        level = context.get("level")
        form = json.loads(input.edit_save_payload()).get("fields", {})
        appends = []
        audit_description = None
        position = None
        try:
            if level == "apiary":
                values = {"name": form["edit_apiary_name"].strip(), "grid_columns": int(form["edit_apiary_columns"]), "grid_rows": int(form["edit_apiary_rows"]), "up_direction": form["edit_apiary_up"]}
                if not values["name"] or not (1 <= values["grid_columns"] <= 26 and 1 <= values["grid_rows"] <= 50): raise ValueError("Enter a name, 1–26 columns, and 1–50 rows.")
                outside = [hive for hive in state.rows("hives", include_all=True, parent_apiary_id=context["id"]) if not hive["is_archived"] and (hive["grid_column"] > values["grid_columns"] or hive["grid_row"] > values["grid_rows"])]
                if outside: raise ValueError("Move hives before shrinking the grid past them.")
            elif level == "hive":
                point = grid_point.get(); name = form["edit_hive_name"].strip()
                if not name or not point: raise ValueError("Enter a name and choose a grid cell.")
                values = {"name": name, "owner": (form.get("edit_hive_owner") or "").strip() or None, "status": form["edit_hive_status"], **point}
            elif level == "box":
                position = int(form["edit_box_position"])
                values = {"name": form["edit_box_name"].strip(), "type": form["edit_box_type"], "max_frames": int(form["edit_box_capacity"])}
            elif level == "frame":
                position = int(form["edit_frame_position"])
                values = {"name": form["edit_frame_name"].strip()}
            elif level == "equipment":
                name = (form.get("edit_equipment_name") or "").strip()
                if not name: raise ValueError("Select or enter an equipment description.")
                existing = next((row for row in state.rows("equipment_types", include_all=True) if not row["is_archived"] and row["name"].casefold() == name.casefold()), None)
                equipment_type = existing or base_record(name=name)
                values = {"equipment_type_id": equipment_type["id"]}
                old_type = state.record("equipment_types", state.record("equipment", context["id"])["equipment_type_id"])
                if not old_type or old_type["name"] != name:
                    audit_description = f"Edited equipment {state.record('equipment', context['id'])['code']}: description changed from {old_type['name'] if old_type else 'Unknown'} to {name}."
                if not existing:
                    appends.append({"sheet": "equipment_types", "rows": [equipment_type]})
            else: raise ValueError("The edit form is no longer valid.")
            record = state.record(context["sheet"], context["id"])
            edit_values = {**values, **({"position": position} if position is not None and record["is_archived"] else {})}
            result = edit_entity(state.data, context["sheet"], context["id"], edit_values)
            if position is not None and not record["is_archived"]:
                parent_column = "parent_hive_id" if level == "box" else "parent_box_id"
                result = move_entities(result, context["sheet"], [context["id"]], record[parent_column], position)
            audit_values = {**values, **({"position": position} if position is not None else {})}
        except (KeyError, TypeError, ValueError) as error:
            ui.notification_show(str(error), type="error", duration=7); return
        changes = changed_rows(state.data, result)
        audit_description = audit_description or edit_audit_description(level, record, audit_values)
        if changes and audit_description:
            appends.append({"sheet": "notes", "rows": [audit_note(level, context["id"], audit_description)]})
        await mutate(changes, appends, optimistic=result)

    @reactive.effect
    @reactive.event(input.archive_one)
    def _archive_one():
        context = contexts.get("edit_context") or {}
        record = state.record(context.get("sheet", "apiaries"), context.get("id"))
        if not record: return
        label = record.get("name", record.get("code", context.get("level")))
        ui.modal_show(ui.modal(ui.p(f"Archive {label} and all descendants?"), ui.input_action_button("archive_confirm", "Archive", class_="btn-danger submit-once"), title="Confirm archive", easy_close=True, footer=None))

    @reactive.effect
    @reactive.event(input.archive_confirm)
    async def _archive_confirm():
        context = contexts.get("edit_context") or {}
        record = state.record(context.get("sheet", "apiaries"), context.get("id"))
        try: result = archive_entity(state.data, context["sheet"], context["id"])
        except (KeyError, ValueError) as error:
            ui.notification_show(str(error), type="error"); return
        label = record.get("name", record.get("code", context["level"]))
        note = audit_note(context["level"], context["id"], f"Retired {context['level']} {label} and its contents.")
        await mutate(changed_rows(state.data, result), [{"sheet": "notes", "rows": [note]}])
        state.archived_mode = True
        for key in state.selected:
            state.selected[key] = None
        touch_grid(); touch()

    toolbar_server("toolbar", {"summary": summary, "move": move, "edit": edit, "back": back, "search": search, "add": add, "notes": notes}, session)


app = App(app_ui, server, static_assets=Path(__file__).parent / "www")
