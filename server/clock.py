"""Swiss local time for every timestamp the server writes.

The venue is in Switzerland but laptops may be set to another zone (UK).
Timestamps stay naive ISO strings (same format as before) so sorting and
the exports are unchanged; they are always Europe/Zurich wall-clock time.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

ZONE = ZoneInfo("Europe/Zurich")  # Windows needs the tzdata package (in requirements.txt)


def now() -> datetime:
    """Current Swiss wall-clock time, naive (no offset), to match stored strings."""
    return datetime.now(ZONE).replace(tzinfo=None)


def now_iso() -> str:
    return now().isoformat(timespec="seconds")
