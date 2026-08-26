"""
Generates realistic mock sensor + battery data for the REAL site registry
(sites.py), so the dashboard can be reviewed and tested with your actual
site names/locations before the live Arable sync is fully working.

A few sites get deliberately broken data (offline, gaps, low/draining
battery) matching their real registry status where it makes sense, so the
gap-detection and battery views have something meaningful to show.

Usage:
    python mock_data.py
"""

import math
import random
from datetime import datetime, timedelta, timezone

from config import TRACKED_PARAMETERS
from db import init_db, get_conn, upsert_device, upsert_reading, upsert_battery_reading
from sites import SITE_REGISTRY

random.seed(42)


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


def simulate_battery(t: datetime, days_elapsed: float, profile: str):
    """profile: 'healthy', 'draining', 'low' -- matches registry status."""
    daily_cycle = 5 * math.sin((t.hour / 24 - 0.3) * 2 * math.pi)  # solar charge/discharge
    if profile == "healthy":
        base = 88
    elif profile == "draining":
        base = max(15, 70 - days_elapsed * 1.5)
    else:  # low
        base = max(5, 25 - days_elapsed * 0.5)
    return round(min(100, max(0, base + daily_cycle + random.gauss(0, 2))), 1)


def battery_profile_for_status(status: str) -> str:
    if status.startswith("Active"):
        return "healthy"
    if "Low Battery" in status:
        return "draining"
    return "low"


def build():
    init_db()
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=14)

    with get_conn() as conn:
        for site in SITE_REGISTRY:
            upsert_device(
                conn, site["device_id"], site["site_name"], site["status"], site["country"],
                site.get("region"), site.get("org"), site.get("lat"), site.get("lon"),
                site.get("install_date"), site.get("match"), site.get("note"),
            )

    for site in SITE_REGISTRY:
        device_id = site["device_id"]
        lat = site.get("lat") or 0.0
        status = site["status"]
        profile = battery_profile_for_status(status)

        # Sites with no current location (uninstalled / not installed) get
        # no simulated readings -- there's nothing physically reporting.
        if site.get("lat") is None or status in ("Uninstalled", "Not Installed"):
            continue

        t = start
        with get_conn() as conn:
            while t <= now:
                skip = False
                # A couple of "Active" sites get deliberately broken data so
                # the gap view has something to show, without contradicting
                # their real registry status.
                if device_id == "D008303" and t >= now - timedelta(hours=9):
                    skip = True  # Ikerege: simulate a recent outage
                if device_id == "D005926" and (
                    (start + timedelta(hours=40)) <= t <= (start + timedelta(hours=44))
                ):
                    skip = True  # Kibwezi: simulate a scattered gap
                if "Inactive" in status and t >= now - timedelta(days=2):
                    skip = True  # Inactive sites: no recent data, matching real status

                if not skip:
                    for param in TRACKED_PARAMETERS:
                        upsert_reading(conn, device_id, t.isoformat(), param, simulate_value(param, t, lat))

                # battery: one sample every 6 hours is plenty for a demo trend
                if t.hour % 6 == 0:
                    days_elapsed = (t - start).total_seconds() / 86400
                    pct = simulate_battery(t, days_elapsed, profile)
                    upsert_battery_reading(conn, device_id, t.isoformat(), pct, "auto", f"{pct:.0f}%")

                t += timedelta(hours=1)

        print(f"Generated mock data for {site['site_name']} ({device_id}) [{status}]")

    print("\nMock database ready -> run: streamlit run app.py")


if __name__ == "__main__":
    build()
