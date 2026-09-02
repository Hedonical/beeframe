from shiny import module, reactive, ui


@module.ui
def connection_ui():
    return ui.div(
        ui.p("Connect your Google account to open Beeframe.", class_="login-prompt"),
        ui.input_action_button("connect", "Connect with Google", class_="primary-button"),
        ui.tags.a("Privacy policy", href="../privacy.html", target="_top"),
        class_="connection-panel",
    )


@module.server
def connection_server(input, output, session, connect):
    @reactive.effect
    @reactive.event(input.connect)
    async def _connect():
        await connect()
