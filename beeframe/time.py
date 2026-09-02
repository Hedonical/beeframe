from datetime import datetime, timezone
from zoneinfo import ZoneInfo

DISPLAY_ZONE = ZoneInfo("America/New_York")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def parse_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def display_time(value: str) -> str:
    local = parse_utc(value).astimezone(DISPLAY_ZONE)
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{local.strftime('%b')} {local.day}, {local.year} {hour}:{local.strftime('%M %p')}"
