from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_connection_screen_is_minimal():
    source = (ROOT / "beeframe/modules/connection.py").read_text()
    assert "Connect your Google account to open Beeframe." in source
    assert "Connect with Google" in source
    assert "brand-mark" not in source and "ui.h1" not in source


def test_apiary_grid_is_scrollable_oriented_and_selectable():
    app = (ROOT / "app.py").read_text()
    javascript = (ROOT / "www/app-ui.js").read_text()
    styles = (ROOT / "www/styles.css").read_text()
    assert "def apiary_grid(" in app and 'class_="grid-scroll"' in app
    assert 'class_="grid-direction grid-direction-top"' in app
    assert 'f"← {directions' not in app and 'directions[(top + 1) % 4]} →' not in app
    assert 'Shiny.setInputValue("hive_grid_point"' in javascript
    assert ".grid-scroll { overflow-x:auto" in styles
    assert 'aria_label="Hive status legend"' in app
    assert "status-dot status-active" in app and ".status-dot.status-storage" in styles


def test_search_and_notes_have_client_side_filters():
    app = (ROOT / "app.py").read_text()
    javascript = (ROOT / "www/app-ui.js").read_text()
    assert 'id="entity-search-filter"' in app and "filterEntities" in javascript
    assert 'id="search-status-filter"' in app and "data_entity_archived" in app
    assert "data_search_type=level" in app and "data_entity_type=level" in app
    assert 'for level in ("hive", "box", "frame", "equipment")' in app
    assert 'description = equipment_types.get(row["equipment_type_id"]' in app
    assert 'data_search_text=f"{label} {level} {description}"' in app
    assert "matchesQuery" in javascript and "queryTerm.startsWith(term)" in javascript
    assert "matchesType" in javascript and 'closest("[data-search-type]")' in javascript
    assert 'ui.nav_panel("Read notes"' in app and 'ui.nav_panel("Add note"' in app
    assert 'class_="notes-table"' in app and "filterNotes" in javascript
    assert 'class_="note-target"' in app and '"equipment", "equipment", "code"' in app
    assert 'level in ("apiary", "hive", "box", "frame", "equipment")' in app


def test_grid_is_rendered_separately_from_hierarchy_updates():
    app = (ROOT / "app.py").read_text()
    assert 'ui.output_ui("apiary_panel"), ui.output_ui("hierarchy")' in app
    assert "def touch_grid():" in app
    assert app.count('toolbar_server("toolbar"') == 1


def test_relational_tabs_and_frame_measurement_action():
    app = (ROOT / "app.py").read_text()
    styles = (ROOT / "www/styles.css").read_text()
    assert '"Choose an apiary"' in app and 'class_="level relationship-tab apiary-tab"' in app
    assert 'class_="relational-strip"' in app and 'class_="level relationship-tab hive-tab"' in app
    assert 'ui.nav_panel("Measure"' in app and 'ui.nav_panel("Past"' in app
    assert 'ui.nav_panel("Measure", measurement_form())' in app
    assert "measurement_recent_ok" not in app
    assert 'apiary_grid(apiary, state.rows("hives"' in app
    assert 'ui.strong(row["name"])' in app and 'f"Equipment · {len(equipment)}"' in app
    assert 'input_action_button("equipment_panel"' not in app
    assert 'ui.div(ui.strong(row["code"]), ui.tags.small(equipment_types.get(row["equipment_type_id"], "Equipment"))' in app
    assert 'ui.p(equipment_types.get(selected_equipment["equipment_type_id"]' not in app
    assert '} box | {len(state.rows(\'equipment\'' in app
    assert 'script_button("Archived", "archive", "archived"' in app
    assert 'class_="hive-contents-inline"' in app
    assert 'ui.span("Bottom"' in app and 'ui.span("Top"' in app
    assert '], class_="relational-strip boxes"),\n                    ui.span("Top"' in app
    assert 'ui.span("Left", class_="stack-end frame-left")' in app
    assert 'ui.span("Right", class_="stack-end frame-right")' in app
    assert "grid-template-columns:1.1rem minmax(0,1fr) 1.1rem auto" in styles
    assert '("frames", "frame", "Frames", "name")' in app
    assert 'if state.archived_mode and selected_hive' in app
    assert 'if state.archived_mode and selected_box' in app
    assert 'if state.archived_mode and selected_frame' in app
    assert 'ui.navset_tab(ui.nav_panel("Past", past_measurements), selected="Past") if frame_archived' in app
    assert 'state._archived("frames", frame)' in app and "Archived frames are read-only." in app


def test_shell_has_no_disconnect_button_or_black_navigation_bar():
    app = (ROOT / "app.py").read_text()
    styles = (ROOT / "www/styles.css").read_text()
    assert 'ui.input_action_button("disconnect"' not in app
    assert "app-topline" not in app and ".app-topline" not in styles
    assert "sync-status" not in app and ".sync-status" not in styles
    assert ".bottom-nav { backdrop-filter" in styles
    assert "grid-template-columns:repeat(8,clamp(2.35rem,10.5vw,3rem))" in styles
    assert 'input_action_button("move", icon(' in (ROOT / "beeframe/modules/navigation.py").read_text()
    assert 'input_action_button("summary", icon(' in (ROOT / "beeframe/modules/navigation.py").read_text()
    assert 'input_switch("archive_mode"' not in app


def test_toolbar_can_enter_fullscreen_and_legacy_workbooks_can_be_repaired():
    app = (ROOT / "app.py").read_text()
    navigation = (ROOT / "beeframe/modules/navigation.py").read_text()
    javascript = (ROOT / "www/app-ui.js").read_text()
    validation = (ROOT / "beeframe/validation.py").read_text()
    assert 'data_fullscreen_toggle="true"' in navigation
    assert 'requestFullscreen({ navigationUI: "hide" })' in javascript
    assert 'document.addEventListener("fullscreenchange"' in javascript
    assert 'repair_legacy_integrity(loaded, utc_now())' in app
    assert 'input_action_button("legacy_repair_confirm"' in app
    assert 'context={"legacy_repair": True}' in app
    assert 'not row.get("archived")' in validation


def test_page_and_move_dialog_are_scrollable_and_searchable():
    app = (ROOT / "app.py").read_text()
    styles = (ROOT / "www/styles.css").read_text()
    javascript = (ROOT / "www/app-ui.js").read_text()
    assert 'id="move-search-filter"' in app and "data_move_id" in app
    assert "filterMove" in javascript and "move_selection" in javascript
    assert "overflow-y:auto!important" in styles and ".move-results" in styles
    assert 'ui.modal_show(ui.modal(ui.output_ui("workflow_panel")' in app
    assert 'options={"create": True' in app and "def owner_choices():" in app


def test_hives_can_move_and_equipment_has_one_creation_flow():
    app = (ROOT / "app.py").read_text()
    assert 'level not in ("hive", "box", "frame", "equipment")' in app
    assert "move_hives(state.data" in app
    assert 'ui.output_ui("move_hive_grid")' in app and "def move_hive_grid():" in app
    assert 'input_numeric("move_grid_column"' not in app and 'input_numeric("move_grid_row"' not in app
    assert 'input_selectize("equipment_name"' in app
    assert "choose_equipment_type" not in app and "manage_equipment_types" not in app


def test_equipment_edit_box_attribute_search_and_apiary_summary():
    app = (ROOT / "app.py").read_text()
    assert 'input_selectize("edit_equipment_name"' in app
    assert 'elif level == "equipment":' in app and 'values = {"equipment_type_id": equipment_type["id"]}' in app
    assert 'box_type = box_type_label(row["type"])' in app
    assert "{row['max_frames']}-frame" in app and "hive.get('status', '')" in app
    assert "def summary():" in app and 'summary_group("Hives by owner"' in app and 'summary_group("Boxes by type"' in app
    assert 'summary_group("Equipment by description"' in app
    assert 'summary_group("Equipment by owner"' in app and 'summary_group("Boxes by capacity"' in app
    assert 'ui.strong("Inventory by hive")' in app
    assert "def audit_note(" in app and 'f"Retired {context[\'level\']}' in app
    assert 'nature="Moved"' in app and 'appends.append({"sheet": "notes"' in app


def test_box_and_frame_positions_can_be_edited_or_dragged():
    app = (ROOT / "app.py").read_text()
    javascript = (ROOT / "www/app-ui.js").read_text()
    styles = (ROOT / "www/styles.css").read_text()
    schemas = (ROOT / "beeframe/schemas.py").read_text()
    assert 'position_editor("edit_box_position"' in app and 'position_editor("edit_frame_position"' in app
    assert 'position = int(form["edit_box_position"])' in app and 'position = int(form["edit_frame_position"])' in app
    assert 'result = move_entities(result, context["sheet"]' in app
    assert 'data_reorder_level="box"' in app and 'data_reorder_level="frame"' in app
    assert 'data_reorder_handle="true"' not in app and "HOLD_TO_REORDER_MS = 500" in javascript
    assert "function showReorderHint(item, target = null)" in javascript and "reorderPositionLabel(target)" in javascript
    assert 'Shiny.setInputValue("reorder_request"' in javascript and 'document.addEventListener("pointermove"' in javascript
    assert "def _reorder_request():" in app and ".position-steps" in styles and ".is-drop-target" in styles
    assert 'position = target["position"]' in app
    assert "edit_submit_button()" in app
    assert '@reactive.event(input.edit_save_payload)' in app
    assert 'form = json.loads(input.edit_save_payload())' in app
    assert 'class_="persistent-action-signals"' in app
    assert 'event.target.closest("[data-edit-submit]")' in javascript
    assert 'Shiny.setInputValue("edit_save_payload"' in javascript
    assert 'optimistic=result' in app
    assert 'state.data = context["rollback"]' in app
    assert '("code", Field(TEXT, "Code", True, editable=False))' in schemas
    assert '("parent_hive_id", Field(TEXT, "Hive", True, editable=False))' in schemas


def test_mock_workbook_supports_persisted_reorder_testing():
    source = (ROOT / "www/google-sheets-parent.js").read_text()
    assert "function mockMutate(request)" in source
    assert "box2:" in source and "box3:" in source
    assert "frame2:" in source and "frame3:" in source
    assert 'if (request.action === "mutate") return mockMutate(request)' in source


def test_summary_has_drilldown_map_and_vertical_hive_report():
    app = (ROOT / "app.py").read_text()
    javascript = (ROOT / "www/app-ui.js").read_text()
    styles = (ROOT / "www/styles.css").read_text()
    assert "def summary_grid(" in app and 'ui.output_ui("summary_map")' in app
    assert 'input_radio_buttons("summary_entity"' in app
    assert 'input_select("summary_box_type"' in app and 'input_select("summary_capacity"' in app
    assert 'input_select("summary_equipment_type"' in app
    assert "def hive_summary_report():" in app and 'class_="hive-summary-report"' in app
    assert "def stacked_bar(" in app and 'class_="compact-frame-track stacked-frame-track"' in app
    assert 'stacked_bar("Bees"' in app and 'stacked_bar("Comb"' in app
    assert 'class_="frame-queen-cells"' in app and 'class_="frame-plot-legend"' in app
    assert 'key = (row["parent_frame_id"], row["scope"])' in app
    assert 'scopes = [("Left", left), ("Right", right)] if left or right' in app
    assert 'ui.div("TOP"' in app and 'ui.div("BOTTOM"' in app
    assert ".summary-grid-count" in styles and ".stacked-segment" in styles
    assert ".segment-capped-honey" in styles and ".frame-queen-cells" in styles
    assert "flex-direction:column-reverse" in styles and "height:7.5rem" in styles
    assert ".legend-group>strong" in styles and ".segment-bees { background:#2563eb" in styles
    assert ".hive-frame-list { display:grid" in styles and "repeat(var(--frame-count)" in styles
    assert ".hive-frame-list.few-frames" in styles
    assert 'data_chart_series=kind' in app and 'data_chart_reset="true"' in app
    assert 'closest("[data-chart-series]")' in javascript and "segment.hidden = !active" in javascript
    assert ".legend-toggle:not(.is-active)" in styles and "8.5rem" in styles


def test_submit_actions_are_locked_against_double_clicks():
    app = (ROOT / "app.py").read_text()
    javascript = (ROOT / "www/app-ui.js").read_text()
    styles = (ROOT / "www/styles.css").read_text()
    assert 'if (state.busy):' not in app
    assert "if state.busy:" in app and 'closest(".submit-once")' in javascript
    assert 'button.dataset.submitting === "true"' in javascript and "submissionLocks" in javascript
    assert 'window.setTimeout(() => {' in javascript and 'button.setAttribute("aria-disabled", "true")' in javascript
    assert 'button.classList.contains("measurement-save")' in javascript and 'button.textContent = "Saving…"' in javascript
    assert "last_measurement_save" in app and 'now - last_measurement_save[1] < 5' in app
    assert ".submit-once.is-submitting" in styles


def test_measurement_form_is_glove_friendly():
    app = (ROOT / "app.py").read_text()
    javascript = (ROOT / "www/app-ui.js").read_text()
    styles = (ROOT / "www/styles.css").read_text()
    assert 'type="range"' in app and 'class_="measurement-slider"' in app
    assert "data_measurement_value" not in app and "data_measurement_delta" not in app
    assert 'ui.input_radio_buttons("measurement_color", "Comb color", ("white", "brown", "black")' in app
    assert "--frame-comb-color" in app
    assert 'data_measurement_clear="true"' not in app and '"measurement_copy_last"' not in app
    assert "setMeasurementValue" in javascript and ".measurement-slider" in javascript
    assert "updateMeasurementPreset" not in javascript
    assert ".measurement-slider::-webkit-slider-runnable-track" in styles and ".measurement-save" in styles
    assert ".measurement-segment .form-check-label" in styles and "border-radius:.2rem" in styles
    assert ".btn-primary" in styles and "color:white!important" in styles
