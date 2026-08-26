"""SQLite storage layer for the Arable dashboard."""

import sqlite3
from contextlib import contextmanager

from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id       TEXT PRIMARY KEY,
    location_id     TEXT,
    location_name   TEXT,
    country         TEXT,
    lat             REAL,
    lon             REAL
);

CREATE TABLE IF NOT EXISTS readings (
    device_id   TEXT NOT NULL,
    timestamp   TEXT NOT NULL,   -- ISO 8601 UTC
    parameter   TEXT NOT NULL,
    value       REAL,
    PRIMARY KEY (device_id, timestamp, parameter)
);

CREATE INDEX IF NOT EXISTS idx_readings_device_time ON readings (device_id, timestamp);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def upsert_device(conn, device_id, location_id, location_name, country, lat, lon):
    conn.execute(
        """INSERT INTO devices (device_id, location_id, location_name, country, lat, lon)
           VALUES (?, ?, ?, ?, ?, ?)
           ON CONFLICT(device_id) DO UPDATE SET
             location_id=excluded.location_id,
             location_name=excluded.location_name,
             country=excluded.country,
             lat=excluded.lat,
             lon=excluded.lon""",
        (device_id, location_id, location_name, country, lat, lon),
    )


def upsert_reading(conn, device_id, timestamp, parameter, value):
    conn.execute(
        """INSERT INTO readings (device_id, timestamp, parameter, value)
           VALUES (?, ?, ?, ?)
           ON CONFLICT(device_id, timestamp, parameter) DO UPDATE SET value=excluded.value""",
        (device_id, timestamp, parameter, value),
    )


def list_devices():
    with get_conn() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM devices ORDER BY country, location_name")]


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
