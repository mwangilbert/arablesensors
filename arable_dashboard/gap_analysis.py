"""
Gap / offline detection.

For a given device and time window, we know what timestamps we *expect*
(one every EXPECTED_INTERVAL_MINUTES). Comparing that to what's actually
in the database tells us:
  - individual gaps (missing stretches within the window)
  - overall data completeness %
  - current status: Online / Data Gaps / Offline
"""

from datetime import datetime, timedelta, timezone

from config import EXPECTED_INTERVAL_MINUTES, GAP_THRESHOLD_HOURS, OFFLINE_AFTER_HOURS
from db import get_readings, get_last_reading_time


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts.replace("Z", "+00:00"))


def expected_timestamps(start: datetime, end: datetime):
    step = timedelta(minutes=EXPECTED_INTERVAL_MINUTES)
    t = start
    out = []
    while t <= end:
        out.append(t)
        t += step
    return out


def find_gaps(device_id: str, parameter: str, start: datetime, end: datetime):
    """Returns (completeness_pct, list_of_gap_dicts) for one device+parameter."""
    rows = get_readings(
        device_id, parameter, start.isoformat(), end.isoformat()
    )
    actual_times = {_parse(r["timestamp"]) for r in rows}
    expected = expected_timestamps(start, end)

    if not expected:
        return 100.0, []

    missing = [t for t in expected if t not in actual_times]
    completeness = 100.0 * (len(expected) - len(missing)) / len(expected)

    # Collapse consecutive missing timestamps into gap ranges
    gaps = []
    step = timedelta(minutes=EXPECTED_INTERVAL_MINUTES)
    i = 0
    while i < len(missing):
        gap_start = missing[i]
        j = i
        while j + 1 < len(missing) and missing[j + 1] - missing[j] == step:
            j += 1
        gap_end = missing[j]
        duration_hours = (gap_end - gap_start).total_seconds() / 3600 + EXPECTED_INTERVAL_MINUTES / 60
        if duration_hours >= GAP_THRESHOLD_HOURS:
            gaps.append({"start": gap_start, "end": gap_end, "hours": round(duration_hours, 1)})
        i = j + 1

    return round(completeness, 1), gaps


def device_status(device_id: str, now: datetime | None = None) -> dict:
    """Quick health check for one device: Online / Data Gaps / Offline."""
    now = now or datetime.now(timezone.utc)
    last_ts = get_last_reading_time(device_id)
    if not last_ts:
        return {"status": "No Data", "last_seen": None, "hours_since": None}

    last_dt = _parse(last_ts)
    hours_since = (now - last_dt).total_seconds() / 3600

    if hours_since >= OFFLINE_AFTER_HOURS:
        status = "Offline"
    elif hours_since >= GAP_THRESHOLD_HOURS:
        status = "Data Gaps"
    else:
        status = "Online"

    return {"status": status, "last_seen": last_ts, "hours_since": round(hours_since, 1)}
