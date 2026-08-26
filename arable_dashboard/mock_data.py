"""
Generates a realistic mock dataset so you can run the dashboard today,
before your Arable API key is wired in. Creates ~15 sites across a few
countries, 14 days of hourly data, with a few sites given deliberate gaps
or an offline stretch so the gap-detection view has something to show.

Usage:
    python mock_data.py
"""

import math
import random
from datetime import datetime, timedelta, timezone

from config import TRACKED_PARAMETERS
from db import init_db, get_conn, upsert_device, upsert_reading

random.seed(42)

SITES = [
    ("A100001", "Kilifi Site 1", "Kenya", -3.63, 39.85),
    ("A100002", "Machakos Site 1", "Kenya", -1.52, 37.26),
    ("A100003", "Kitale Site 1", "Kenya", 1.02, 35.00),
    ("A100004", "Kumasi Site 1", "Ghana", 6.69, -1.62),
    ("A100005", "Tamale Site 1", "Ghana", 9.40, -0.84),
    ("A100006", "Mbale Site 1", "Uganda", 1.08, 34.18),
    ("A100007", "Gulu Site 1", "Uganda", 2.78, 32.30),
    ("A100008", "Kigali Site 1", "Rwanda", -1.94, 30.06),
    ("A100009", "Musanze Site 1", "Rwanda", -1.50, 29.63),
    ("A100010", "Lilongwe Site 1", "Malawi", -13.96, 33.79),
    ("A100011", "Blantyre Site 1", "Malawi", -15.79, 35.00),
    ("A100012", "Parakou Site 1", "Benin", 9.34, 2.63),
    ("A100013", "Cotonou Site 1", "Benin", 6.37, 2.43),
    ("A100014", "Eldoret Site 1", "Kenya", 0.52, 35.27),
    ("A100015", "Accra Site 1", "Ghana", 5.60, -0.19),
]

# device_id -> simulated fault pattern
FAULT_PATTERNS = {
    "A100003": "offline_recent",     # went offline in the last 10 hours
    "A100007": "intermittent_gaps",  # a few scattered multi-hour gaps
    "A100011": "long_outage",        # one big multi-day outage a week ago
}


def simulate_value(param, t: datetime, lat: float):
    hour = t.hour
    day_frac = hour / 24
    seasonal = math.sin((t.timetuple().tm_yday / 365) * 2 * math.pi)

    if param == "tair":
        base = 24 - abs(lat) * 0.3
        return round(base + 8 * math.sin((day_frac - 0.25) * 2 * math.pi) + seasonal * 2 + random.gauss(0, 0.6), 2)
    if param == "rh":
        return round(min(1.0, max(0.2, 0.60 + 0.25 * math.cos((day_frac - 0.25) * 2 * math.pi) + random.gauss(0, 0.04))), 3)
    if param == "precip":
        return round(max(0, random.gauss(0, 1) if random.random() > 0.9 else 0), 2)
    if param == "slp":
        return round(101.3 + random.gauss(0, 0.15), 2)
    if param == "pardw":
        daylight = max(0, math.sin((day_frac - 0.25) * 2 * math.pi))
        return round(daylight * 1800 + random.gauss(0, 30), 1)
    return round(random.gauss(0, 1), 2)


def build():
    init_db()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=14)

    with get_conn() as conn:
        for device_id, name, country, lat, lon in SITES:
            upsert_device(conn, device_id, f"loc_{device_id}", name, country, lat, lon)

    for device_id, name, country, lat, lon in SITES:
        pattern = FAULT_PATTERNS.get(device_id)
        t = start
        with get_conn() as conn:
            while t <= now:
                skip = False
                if pattern == "offline_recent" and t >= now - timedelta(hours=10):
                    skip = True
                if pattern == "intermittent_gaps" and (
                    (start + timedelta(hours=40)) <= t <= (start + timedelta(hours=44))
                    or (start + timedelta(hours=150)) <= t <= (start + timedelta(hours=157))
                ):
                    skip = True
                if pattern == "long_outage" and (now - timedelta(days=8)) <= t <= (now - timedelta(days=6, hours=6)):
                    skip = True

                if not skip:
                    for param in TRACKED_PARAMETERS:
                        upsert_reading(conn, device_id, t.isoformat(), param, simulate_value(param, t, lat))
                t += timedelta(hours=1)

        print(f"Generated mock data for {name} ({device_id}){' [' + pattern + ']' if pattern else ''}")

    print("\nMock database ready -> run: streamlit run app.py")


if __name__ == "__main__":
    build()
