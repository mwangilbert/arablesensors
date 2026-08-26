"""
Arable Sensor Network Dashboard

Two views:
  1. Fleet Overview  - every site, its online/offline/gap status, a map
  2. Site Detail      - click a site, see trend charts per parameter with
                         missing-data windows shaded so gaps are obvious

Run:
    streamlit run app.py
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import TRACKED_PARAMETERS, GAP_THRESHOLD_HOURS, ARABLE_API_KEY, ARABLE_API_KEY_DEBUG
from db import init_db, list_devices, get_readings
from gap_analysis import device_status, find_gaps

st.set_page_config(page_title="Arable Network Dashboard", layout="wide")

STATUS_COLORS = {
    "Online": "#2ecc71",
    "Data Gaps": "#f39c12",
    "Offline": "#e74c3c",
    "No Data": "#95a5a6",
}

WINDOW_OPTIONS = {
    "Last 24 hours": 1,
    "Last 7 days": 7,
    "Last 14 days": 14,
}


@st.cache_data(ttl=60)
def load_devices():
    return list_devices()


@st.cache_data(ttl=3600, show_spinner="Syncing latest data from Arable...")
def sync_from_arable():
    """Pull the newest readings from the real Arable API, at most once per
    hour (shared across every visitor while this cache entry is valid).
    No-ops quietly if no API key is configured, so the mock-data demo
    still works untouched. Never raises -- returns a status string so the
    dashboard can show what happened instead of crashing."""
    if not ARABLE_API_KEY:
        return "no_key"
    from arable_client import ArableClient
    from ingest import sync_devices, sync_readings

    try:
        client = ArableClient()
        device_ids = sync_devices(client)
        sync_readings(client, device_ids)
        return "synced"
    except Exception as e:
        # Includes HTTP errors from Arable (401 bad key, 403 forbidden, etc.)
        # str(e) for requests' HTTPError includes the status code + reason,
        # and never includes the API key itself (it's sent as a header, not
        # in the URL), so it's safe to show directly.
        return f"error: {type(e).__name__}: {e}"


def compute_fleet_status(devices):
    rows = []
    for d in devices:
        s = device_status(d["device_id"])
        rows.append({**d, **s})
    return pd.DataFrame(rows)


def render_fleet_overview(devices_df: pd.DataFrame):
    st.subheader("Fleet Overview")
    st.caption("Every Arable site, at a glance. Red/orange rows are where to look first.")

    counts = devices_df["status"].value_counts()
    cols = st.columns(4)
    for col, status in zip(cols, ["Online", "Data Gaps", "Offline", "No Data"]):
        col.metric(status, int(counts.get(status, 0)))

    if devices_df["lat"].notna().any():
        map_df = devices_df.dropna(subset=["lat", "lon"]).copy()
        map_df["color"] = map_df["status"].map(STATUS_COLORS)
        st.map(map_df.rename(columns={"lat": "latitude", "lon": "longitude"}), size=20)

    display_df = devices_df[["device_id", "location_name", "country", "status", "last_seen", "hours_since"]].copy()
    display_df = display_df.rename(columns={
        "device_id": "Device", "location_name": "Site", "country": "Country",
        "status": "Status", "last_seen": "Last Reading (UTC)", "hours_since": "Hours Since",
    }).sort_values(["Status", "Site"])

    def highlight(row):
        color = STATUS_COLORS.get(row["Status"], "white")
        return [f"background-color: {color}22"] * len(row)

    st.dataframe(display_df.style.apply(highlight, axis=1), use_container_width=True, hide_index=True)


def render_site_detail(devices_df: pd.DataFrame):
    st.subheader("Site Detail")

    site_labels = {
        row["device_id"]: f"{row['location_name']} ({row['device_id']}) - {row['country']}"
        for _, row in devices_df.iterrows()
    }
    device_id = st.selectbox("Choose a site", options=list(site_labels.keys()), format_func=lambda x: site_labels[x])
    window_label = st.radio("Time window", list(WINDOW_OPTIONS.keys()), horizontal=True, index=1)
    days = WINDOW_OPTIONS[window_label]

    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    start = now - timedelta(days=days)

    status_row = devices_df[devices_df["device_id"] == device_id].iloc[0]
    badge_color = STATUS_COLORS.get(status_row["status"], "gray")
    st.markdown(
        f"**Status:** <span style='color:{badge_color}; font-weight:700'>{status_row['status']}</span>"
        f" &nbsp;|&nbsp; Last reading: {status_row['last_seen'] or 'never'}",
        unsafe_allow_html=True,
    )

    for param, (label, unit) in TRACKED_PARAMETERS.items():
        rows = get_readings(device_id, param, start.isoformat(), now.isoformat())
        completeness, gaps = find_gaps(device_id, param, start, now)

        with st.expander(f"{label} ({unit}) — {completeness}% complete, {len(gaps)} gap(s)", expanded=(param == "tair")):
            if not rows:
                st.info("No data in this window.")
                continue

            df = pd.DataFrame(rows)
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["timestamp"], y=df["value"], mode="lines", name=label, line=dict(width=2)))

            for gap in gaps:
                fig.add_vrect(
                    x0=gap["start"], x1=gap["end"] + timedelta(minutes=59),
                    fillcolor="red", opacity=0.15, line_width=0,
                    annotation_text=f"{gap['hours']}h gap", annotation_position="top left",
                )

            fig.update_layout(
                margin=dict(l=10, r=10, t=30, b=10), height=280,
                yaxis_title=unit, xaxis_title=None, showlegend=False,
            )
            st.plotly_chart(fig, use_container_width=True)

            if gaps:
                gap_df = pd.DataFrame(gaps)
                st.caption("Detected gaps in this window:")
                st.dataframe(gap_df, hide_index=True, use_container_width=True)


def main():
    init_db()  # make sure devices/readings tables exist before anything queries them

    st.title("🌍 Arable Sensor Network Dashboard")
    st.caption(f"Gap threshold: {GAP_THRESHOLD_HOURS}h missing = flagged gap. Data source: local SQLite (synced from Arable API).")

    col1, col2 = st.columns([1, 5])
    with col1:
        if st.button("🔄 Sync now"):
            sync_from_arable.clear()
            load_devices.clear()
            st.rerun()

    sync_result = sync_from_arable()
    if sync_result == "no_key":
        st.info("No ARABLE_API_KEY configured — showing whatever is already in the local database "
                "(e.g. mock data). Add the secret to pull live data.", icon="ℹ️")
    elif sync_result and sync_result.startswith("error"):
        st.error(f"Sync from Arable failed: {sync_result}", icon="🚫")

    with st.expander("🔧 Debug: API key detection", expanded=(sync_result != "synced")):
        st.json(ARABLE_API_KEY_DEBUG)
    load_devices.clear()  # pick up anything sync_from_arable just wrote

    devices = load_devices()
    if not devices:
        st.warning("No devices found. Run `python mock_data.py` for a demo, or `python ingest.py` to pull real data.")
        return

    devices_df = compute_fleet_status(devices)

    tab1, tab2 = st.tabs(["📊 Fleet Overview", "🔍 Site Detail"])
    with tab1:
        render_fleet_overview(devices_df)
    with tab2:
        render_site_detail(devices_df)


if __name__ == "__main__":
    main()
