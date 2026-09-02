from shiny import module, reactive, ui
from shiny.session import session_context


def icon(path):
    return ui.HTML(f'<svg viewBox="0 0 24 24" aria-hidden="true"><path d="{path}"/></svg>')


@module.ui
def toolbar_ui():
    return ui.tags.nav(
        ui.tags.button(
            icon("M8 3H3v5M16 3h5v5M8 21H3v-5M16 21h5v-5"), type="button",
            class_="nav-action", data_fullscreen_toggle="true", aria_label="Enter fullscreen", title="Enter fullscreen",
        ),
        ui.input_action_button("summary", icon("M5 20V10h3v10M11 20V4h3v16M17 20v-7h3v7M3 20h19"), class_="nav-action", aria_label="Apiary summary", title="Apiary summary"),
        ui.input_action_button("move", icon("M8 7h11m0 0-3-3m3 3-3 3M16 17H5m0 0 3 3m-3-3 3-3"), class_="nav-action", aria_label="Move", title="Move"),
        ui.input_action_button("edit", icon("M4 20h4L19 9l-4-4L4 16v4Zm9-13 4 4"), class_="nav-action", aria_label="Edit", title="Edit"),
        ui.input_action_button("back", icon("M9 7 4 12l5 5M5 12h9a6 6 0 0 1 6 6"), class_="nav-action", aria_label="Back", title="Back"),
        ui.input_action_button("search", icon("m21 21-4.4-4.4m2.4-5.1A7.5 7.5 0 1 1 4 11.5a7.5 7.5 0 0 1 15 0Z"), class_="nav-action", aria_label="Search", title="Search"),
        ui.input_action_button("add", icon("M12 5v14M5 12h14"), class_="nav-action nav-add", aria_label="Add", title="Add"),
        ui.input_action_button("notes", icon("M6 3h12v18H6zM9 8h6M9 12h6M9 16h4"), class_="nav-action", aria_label="Notes", title="Notes"),
        class_="bottom-nav", aria_label="Primary actions",
    )


@module.server
def toolbar_server(input, output, session, handlers, root_session):
    for name in ("summary", "move", "edit", "back", "search", "add", "notes"):
        def register(action=name):
            @reactive.effect
            @reactive.event(input[action])
            def _event():
                # Dialog inputs belong to the root app, not this toolbar namespace.
                with session_context(root_session):
                    handlers[action]()
        register()
