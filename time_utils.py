"""Parse historical timestamps without assuming Eastern is always UTC-4."""
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

def parse_timestamp(value, default_zone="UTC"):
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    zone = ZoneInfo(default_zone)
    for suffix, tz in [(" ET", ZoneInfo("America/New_York")), (" EST", timezone(timedelta(hours=-5))), (" EDT", timezone(timedelta(hours=-4))), (" UTC", timezone.utc)]:
        if text.endswith(suffix):
            text = text[:-len(suffix)]; zone = tz; break
    try:
        result = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if result.tzinfo is None:
            result = result.replace(tzinfo=zone)
        return result.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return None

def last_completed_scan(path, default_zone="UTC"):
    if not path.exists():
        return None
    for line in reversed(path.read_text().splitlines()):
        if "scan complete" in line.lower():
            stamp = parse_timestamp(line.split("]",1)[0].lstrip("["), default_zone)
            if stamp:
                return stamp.isoformat()
    return None
