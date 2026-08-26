"""
Pulls devices, locations, and recent time-series data from the Arable API
into the local SQLite database. Run this on a schedule (cron, Task
Scheduler, GitHub Actions, etc.) to keep the dashboard current.

Usage:
    export ARABLE_API_KEY="your-key-here"
    python ingest.py                 # incremental: since last stored reading
    python ingest.py --days 14       # force a 14-day backfill for all devices
"""

import argparse
from datetime import datetime, timedelta, timezone

from arable_client import ArableClient
from config import DATA_TABLE, TRACKED_PARAMETERS
from db import init_db, get_conn, upsert_device, upsert_reading, get_last_reading_time


def sync_devices(client: ArableClient):
    devices = client.get_devices()
    locations = {loc["id"]: loc for loc in client.get_locations()}

    with get_conn() as conn:
        for d in devices:
            loc = locations.get(d.get("location"), {})
            upsert_device(
                conn,
                device_id=d.get("name"),
                location_id=d.get("location"),
                location_name=loc.get("name", d.get("location", "Unknown")),
                country=loc.get("country", ""),
                lat=loc.get("centroid", {}).get("lat") if loc.get("centroid") else loc.get("lat"),
                lon=loc.get("centroid", {}).get("long") if loc.get("centroid") else loc.get("long"),
            )
    print(f"Synced {len(devices)} devices / {len(locations)} locations.")
    return [d.get("name") for d in devices]


def sync_readings(client: ArableClient, device_ids, backfill_days=None):
    select_cols = ["time"] + list(TRACKED_PARAMETERS.keys())
    now = datetime.now(timezone.utc)

    for device_id in device_ids:
        if backfill_days:
            start_time = (now - timedelta(days=backfill_days)).isoformat()
        else:
            last = get_last_reading_time(device_id)
            start_time = last if last else (now - timedelta(days=7)).isoformat()

        rows = client.get_data(
            DATA_TABLE,
            device=device_id,
            start_time=start_time,
            end_time=now.isoformat(),
            select=select_cols,
        )

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
    client = ArableClient()
    device_ids = sync_devices(client)
    sync_readings(client, device_ids, backfill_days=args.days)
    print("Ingestion complete.")


if __name__ == "__main__":
    main()
