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
def _get_secret(key, default=""):
    try:
        import streamlit as st
        return st.secrets.get(key, default)
    except Exception:
        # No streamlit context, or no secrets.toml present at all -> fine,
        # just fall back to the default (env var already checked below).
        return default

# --- Arable API ---------------------------------------------------------
ARABLE_API_KEY = os.environ.get("ARABLE_API_KEY") or _get_secret("ARABLE_API_KEY", "")
ARABLE_BASE_URL = "https://api.arable.cloud/api/v2"

# Which time-series table to pull trend data from.
# "hourly" is recommended for cross-site comparison (stored/aggregated in UTC).
DATA_TABLE = os.environ.get("ARABLE_DATA_TABLE", "hourly")

# --- Local storage -------------------------------------------------------
DB_PATH = os.environ.get("ARABLE_DB_PATH", os.path.join(os.path.dirname(__file__), "arable_data.db"))

# --- Parameters to track on the dashboard ---------------------------------
# key = Arable column name, value = (human label, display unit)
TRACKED_PARAMETERS = {
    "tair": ("Air Temperature", "°C"),
    "rh": ("Relative Humidity", "%"),
    "precip": ("Precipitation", "mm"),
    "slp": ("Sea Level Pressure", "kPa"),
    "par": ("PAR (light)", "µmol/m²/s"),
    "moisture_0_mean": ("Soil Moisture (10cm)", "%"),
}

# --- Gap / offline detection ----------------------------------------------
EXPECTED_INTERVAL_MINUTES = 60      # "hourly" table -> one row expected per hour
GAP_THRESHOLD_HOURS = 3             # missing >= this many consecutive hours = "a gap"
OFFLINE_AFTER_HOURS = 6             # no data at all for this long = "Offline" status
