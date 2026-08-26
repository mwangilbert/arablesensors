"""SQLite storage layer for the Arable dashboard."""

import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id       TEXT PRIMARY KEY,
    site_name       TEXT,
    status          TEXT,          -- e.g. Active, Inactive (Low Battery), Not Installed
    country         TEXT,
    region          TEXT,
    org             TEXT,
    lat             REAL,
    lon             REAL,
    install_date    TEXT,          -- ISO date, may be NULL if unknown
    match_type      TEXT,          -- "id" | "name" | "none" -- how confidently this row is matched
    note            TEXT
);

CREATE TABLE IF NOT EXISTS readings (
    device_id   TEXT NOT NULL,
    timestamp   TEXT NOT NULL,   -- ISO 8601 UTC
    parameter   TEXT NOT NULL,
    value       REAL,
    PRIMARY KEY (device_id, timestamp, parameter)
);

CREATE TABLE IF NOT EXISTS battery_readings (
    device_id   TEXT NOT NULL,
    timestamp   TEXT NOT NULL,   -- ISO 8601 UTC
    battery_pct REAL,            -- 0-100, midpoint if source gave a range like "80-90%"
    source      TEXT,            -- "auto" (from Arable API) or "manual" (logged in-app)
    raw_label   TEXT,            -- original string, e.g. "80-90 %", for reference
    PRIMARY KEY (device_id, timestamp, source)
);

CREATE INDEX IF NOT EXISTS idx_readings_device_time ON readings (device_id, timestamp);
CREATE INDEX IF NOT EXISTS idx_battery_device_time ON battery_readings (device_id, timestamp);
"""


DEVICE_COLUMNS = {
    "site_name": "TEXT",
    "status": "TEXT",
    "country": "TEXT",
    "region": "TEXT",
    "org": "TEXT",
    "lat": "REAL",
    "lon": "REAL",
    "install_date": "TEXT",
    "match_type": "TEXT",
    "note": "TEXT",
}


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate_devices_table(conn):
    # CREATE TABLE IF NOT EXISTS is a no-op on a pre-existing devices table,
    # so an older on-disk db (fewer columns) is patched up to the current
    # schema here instead of failing with "no such column" at query time.
    existing = {row["name"] for row in conn.execute("PRAGMA table_info(devices)")}
    for column, col_type in DEVICE_COLUMNS.items():
        if column not in existing:
            conn.execute(f"ALTER TABLE devices ADD COLUMN {column} {col_type}")


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)
        _migrate_devices_table(conn)


def upsert_device(conn, device_id, site_name, status, country, region, org, lat, lon,
                   install_date=None, match_type=None, note=None):
    conn.execute(
        """INSERT INTO devices (device_id, site_name, status, country, region, org, lat, lon,
                                 install_date, match_type, note)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(device_id) DO UPDATE SET
             site_name=excluded.site_name,
             status=excluded.status,
             country=excluded.country,
             region=excluded.region,
             org=excluded.org,
             lat=excluded.lat,
             lon=excluded.lon,
             install_date=excluded.install_date,
             match_type=excluded.match_type,
             note=excluded.note""",
        (device_id, site_name, status, country, region, org, lat, lon,
         install_date, match_type, note),
    )


def upsert_reading(conn, device_id, timestamp, parameter, value):
    conn.execute(
        """INSERT INTO readings (device_id, timestamp, parameter, value)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(device_id, timestamp, parameter) DO UPDATE SET value=excluded.value""",
        (device_id, timestamp, parameter, value),
    )


def upsert_battery_reading(conn, device_id, timestamp, battery_pct, source, raw_label=None):
    conn.execute(
        """INSERT INTO battery_readings (device_id, timestamp, battery_pct, source, raw_label)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(device_id, timestamp, source) DO UPDATE SET
             battery_pct=excluded.battery_pct, raw_label=excluded.raw_label""",
        (device_id, timestamp, battery_pct, source, raw_label),
    )


def get_battery_readings(device_id, start_time=None, end_time=None):
    q = "SELECT timestamp, battery_pct, source, raw_label FROM battery_readings WHERE device_id=?"
    params = [device_id]
    if start_time:
        q += " AND timestamp >= ?"
        params.append(start_time)
    if end_time:
        q += " AND timestamp <= ?"
        params.append(end_time)
    q += " ORDER BY timestamp"
    with get_conn() as conn:
        return [dict(row) for row in conn.execute(q, params)]


def list_devices():
    with get_conn() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM devices ORDER BY country, site_name")]


def get_readings(device_id, parameter, start_time=None, end_time=None):
    q = "SELECT timestamp, value FROM readings WHERE device_id=? AND parameter=?"
    params = [device_id, parameter]
    if start_time:
        q += " AND timestamp >= ?"
        params.append(start_time)
    if end_time:
        q += " AND timestamp <= ?"
        params.append(end_time)
    q += " ORDER BY timestamp"
    with get_conn() as conn:
        return [dict(row) for row in conn.execute(q, params)]


def get_last_reading_time(device_id):
    with get_conn() as conn:
        row = conn.execute(
            "SELECT MAX(timestamp) as t FROM readings WHERE device_id=?", (device_id,)
        ).fetchone()
        return row["t"] if row else None
