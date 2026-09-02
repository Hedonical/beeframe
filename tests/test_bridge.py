from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_parent_bridge_validates_origin_channel_operation_and_payload():
    source = (ROOT / "www/google-sheets-parent.js").read_text()
    assert "event.origin !== window.location.origin" in source
    assert "message.channel !== CHANNEL" in source
    assert "OPERATIONS.has(request.action)" in source
    assert 'typeof message.requestId !== "string"' in source


def test_iframe_bridge_validates_parent_and_message_shape():
    source = (ROOT / "www/shiny-bridge.js").read_text()
    assert "event.origin !== parentOrigin" in source
    assert "event.source !== window.parent" in source
    assert "message.channel !== CHANNEL" in source
    assert 'typeof message.requestId !== "string"' in source


def test_scope_remains_drive_file_only():
    source = (ROOT / "www/google-sheets-parent.js").read_text()
    assert 'const SCOPE = "https://www.googleapis.com/auth/drive.file"' in source
    assert "userinfo.email" not in source and "userinfo.profile" not in source
