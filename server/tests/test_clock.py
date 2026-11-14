from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from server import clock


def test_now_is_swiss_wall_clock_and_naive():
    expected = datetime.now(timezone.utc).astimezone(ZoneInfo("Europe/Zurich")).replace(tzinfo=None)
    got = clock.now()
    assert got.tzinfo is None
    assert abs(got - expected) < timedelta(seconds=5)


def test_now_iso_format_unchanged():
    s = clock.now_iso()
    assert len(s) == 19 and s[10] == "T"   # YYYY-MM-DDTHH:MM:SS, same as stored strings
    datetime.fromisoformat(s)
