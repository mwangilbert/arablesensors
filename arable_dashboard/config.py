"""
Central configuration for the Arable Sensor Dashboard.

IMPORTANT: never hard-code your Arable API key here or anywhere in this
project. Set it as an environment variable before running ingest.py:

    export ARABLE_API_KEY="your-key-here"      # macOS/Linux
    setx ARABLE_API_KEY "your-key-here"         # Windows (new terminal after)

If you generated/viewed your key on the Arable "Settings > Account" page
in a screenshot or shared it anywhere, regenerate it there first ("Refresh
Key") before wiring it into this app.
"""

import os

# Works two ways: a plain env var (cron/GitHub Actions) or Streamlit Cloud's
# secrets manager (st.secrets), so the same config.py works in both places.
_secret_error = None

def _get_secret(key, default=""):
    global _secret_error
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception as e:
        # No streamlit context, no secrets.toml, or a malformed secrets file.
        # We surface the actual error via ARABLE_API_KEY_DEBUG below instead
        # of silently swallowing it, so a bad secrets file is visible.
        _secret_error = f"{type(e).__name__}: {e}"
        return default

# --- Arable API ---------------------------------------------------------
_env_val = os.environ.get("ARABLE_API_KEY", "")
_secret_val = _get_secret("ARABLE_API_KEY", "")

if _env_val:
    ARABLE_API_KEY = _env_val
    ARABLE_API_KEY_SOURCE = "environment variable"
elif _secret_val:
    ARABLE_API_KEY = _secret_val
    ARABLE_API_KEY_SOURCE = "st.secrets"
else:
    ARABLE_API_KEY = ""
    ARABLE_API_KEY_SOURCE = "none found"

ARABLE_API_KEY_DEBUG = {
    "source": ARABLE_API_KEY_SOURCE,
    "key_length": len(ARABLE_API_KEY) if ARABLE_API_KEY else 0,
    "key_preview": (ARABLE_API_KEY[:4] + "..." + ARABLE_API_KEY[-4:]) if len(ARABLE_API_KEY) > 8 else "",
    "secrets_error": _secret_error,
}

ARABLE_BASE_URL = "https://api.arable.cloud/api/v2"

# Which time-series table to pull trend data from.
# "hourly" is recommended for cross-site comparison (stored/aggregated in UTC).
DATA_TABLE = os.environ.get("ARABLE_DATA_TABLE", "hourly")

# --- Local storage -------------------------------------------------------
DB_PATH = os.environ.get("ARABLE_DB_PATH", os.path.join(os.path.dirname(__file__), "arable_data.db"))

# --- Parameters to track on the dashboard ---------------------------------
# key = Arable column name, value = (human label, display unit)
# These must be real columns on the "hourly" table -- see Arable's Weather
# and Soil Data Dictionary. Soil moisture (Sentek probes) lives on a
# *separate* table, /data/sentek_hourly, not here -- mixing the two in one
# request causes a 400 Bad Request.
TRACKED_PARAMETERS = {
    "tair": ("Air Temperature", "°C"),
    "rh": ("Relative Humidity", "0-1"),       # fraction, not a percentage
    "precip": ("Precipitation", "mm"),
    "slp": ("Sea Level Pressure", "kPa"),
    "pardw": ("PAR (downwelling)", "µE/m²/s"),
}

# Soil moisture, if your devices have a Sentek probe attached, comes from a
# separate table/endpoint (/data/sentek_hourly) and isn't wired into
# ingest.py yet. Ask if you'd like this added as a second sync path.
SENTEK_PARAMETERS = {
    "moisture_0_mean": ("Soil Moisture (10cm)", "%"),
}

# --- Gap / offline detection ----------------------------------------------
EXPECTED_INTERVAL_MINUTES = 60      # "hourly" table -> one row expected per hour
GAP_THRESHOLD_HOURS = 3             # missing >= this many consecutive hours = "a gap"
OFFLINE_AFTER_HOURS = 6             # no data at all for this long = "Offline" status
