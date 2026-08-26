"""
Populates the local database from two sources:

1. sites.py -- our own curated registry (site names, GPS, status, install
   dates), built from your installation tracking spreadsheet. This is the
   source of truth for WHERE each device is and WHAT it's called, since
   Arable's own /locations naming didn't always match your records.

2. The real Arable API -- for actual sensor readings (/data/hourly) and,
   best-effort, device battery (/devices). NOTE: Arable's public API docs
   don't document a battery field on /devices, so battery capture here is
   defensive: it looks for a few likely field names and records whatever
   it finds under battery_readings with source="auto". If nothing usable
   turns up, the in-app manual battery log (in app.py) is the reliable
   fallback -- log it yourself, e.g. after a site visit, same way you were
   already tracking it in the spreadsheet.

Usage:
    export ARABLE_API_KEY="your-key-here"
    python ingest.py                 # incremental: since last stored reading
    python ingest.py --days 14       # force a 14-day backfill for all devices
"""

import argparse
from datetime import datetime, timedelta, timezone

from arable_client import ArableClient
from config import DATA_TABLE, TRACKED_PARAMETERS
from db import (
    init_db, get_conn, upsert_device, upsert_reading, upsert_battery_reading,
    get_last_reading_time,
)
from sites import SITE_REGISTRY

# Field names to try, in order, when looking for battery on a /devices item.
# Values may come as a number (already a %) or a string like "80-90 %".
_BATTERY_FIELD_CANDIDATES = ["battery", "battery_pct", "battery_percent", "batv", "batt"]


def seed_site_registry():
    """Load our curated site list into the devices table. Always safe to
    re-run -- it's an upsert, so it just refreshes site metadata."""
    with get_conn() as conn:
        for site in SITE_REGISTRY:
            upsert_device(
                conn,
                device_id=site["device_id"],
                site_name=site["site_name"],
                status=site["status"],
                country=site["country"],
                region=site.get("region"),
                org=site.get("org"),
                lat=site.get("lat"),
                lon=site.get("lon"),
                install_date=site.get("install_date"),
                match_type=site.get("match"),
                note=site.get("note"),
            )
    print(f"Seeded {len(SITE_REGISTRY)} sites from the registry.")


def _parse_battery_value(raw):
    """Turn '80-90 %' or 85 or '85%' into a single float percentage."""
    if raw is None:
        return None, None
    if isinstance(raw, (int, float)):
        return float(raw), str(raw)
    s = str(raw).strip()
    label = s
    s = s.replace("%", "").strip()
    if "-" in s:
        parts = [p.strip() for p in s.split("-") if p.strip()]
        try:
            nums = [float(p) for p in parts]
            return sum(nums) / len(nums), label
        except ValueError:
            return None, label
    try:
        return float(s), label
    except ValueError:
        return None, label


def sync_battery_from_devices(client: ArableClient):
    """Best-effort: pull whatever /devices returns and record battery if any
    of the candidate field names are present. Safe no-op if not."""
    try:
        devices = client.get_devices()
    except Exception as e:
        print(f"  Could not fetch /devices for battery sync: {e}")
        return

    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    found_any = False
    with get_conn() as conn:
        for d in devices:
            device_id = d.get("name")
            if not device_id:
                continue
            for field in _BATTERY_FIELD_CANDIDATES:
                if field in d and d[field] is not None:
                    pct, label = _parse_battery_value(d[field])
                    if pct is not None:
                        upsert_battery_reading(conn, device_id, now_iso, pct, "auto", label)
                        found_any = True
                    break

    if found_any:
        print("  Battery data found on /devices and recorded.")
    else:
        print("  No recognizable battery field on /devices for any device -- "
              "use the manual battery log in the app instead.")


def sync_readings(client: ArableClient, device_ids, backfill_days=None):
    select_cols = ["time"] + list(TRACKED_PARAMETERS.keys())
    now = datetime.now(timezone.utc)

    for device_id in device_ids:
        if backfill_days:
            start_time = (now - timedelta(days=backfill_days)).isoformat()
        else:
            last = get_last_reading_time(device_id)
            start_time = last if last else (now - timedelta(days=7)).isoformat()

        try:
            rows = client.get_data(
                DATA_TABLE,
                device=device_id,
                start_time=start_time,
                end_time=now.isoformat(),
                select=select_cols,
            )
        except Exception as e:
            print(f"  {device_id}: FAILED ({e})")
            continue

        with get_conn() as conn:
            for row in rows:
                ts = row.get("time")
                if not ts:
                    continue
                for param in TRACKED_PARAMETERS:
                    if param in row and row[param] is not None:
                        upsert_reading(conn, device_id, ts, param, row[param])

        print(f"  {device_id}: {len(rows)} rows pulled since {start_time}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=None, help="Force backfill this many days for every device")
    args = parser.parse_args()

    init_db()
    seed_site_registry()

    client = ArableClient()
    device_ids = [s["device_id"] for s in SITE_REGISTRY]

    sync_battery_from_devices(client)
    sync_readings(client, device_ids, backfill_days=args.days)
    print("Ingestion complete.")


if __name__ == "__main__":
    main()
