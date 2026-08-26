"""
Arable Sensor Network Dashboard

Views:
  1. Overview     - map of every site (click to select), fleet health summary
  2. Site Detail  - selected site's trends per parameter + battery, with a
                     flexible time window and % reporting per parameter
  3. Compare      - cross-site data-availability and battery comparison

Run:
    streamlit run app.py
"""

from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from config import TRACKED_PARAMETERS, GAP_THRESHOLD_HOURS, ARABLE_API_KEY, ARABLE_API_KEY_DEBUG
from db import init_db, list_devices, get_readings, get_battery_readings, get_conn, upsert_battery_reading
from gap_analysis import device_status, find_gaps

st.set_page_config(page_title="Arable Network Dashboard", layout="wide", page_icon="🛰️")

# ---------------------------------------------------------------------------
# Design tokens -- a deliberate palette, not Streamlit defaults.
# Deep slate/teal (instrumentation, water/weather) rather than the usual
# cream+terracotta or near-black+neon AI-dashboard defaults.
# ---------------------------------------------------------------------------
INK = "#152521"
PANEL_BG = "#F6F8F6"
CARD_BG = "#FFFFFF"
HAIRLINE = "#E1E7E3"
ACCENT = "#1F6F6F"        # deep teal -- brand accent, not a status color
ACCENT_DARK = "#123F3F"
STATUS_COLORS = {
    "Online": "#2E8B57",
    "Data Gaps": "#D9A21B",
    "Offline": "#C1443C",
    "No Data": "#9AA5A0",
}

CUSTOM_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500&display=swap');

html, body, [class*="css"] {{
    font-family: 'IBM Plex Sans', sans-serif;
    color: {INK};
}}
.stApp {{
    background-color: {PANEL_BG};
}}
[data-testid="stHeader"] {{
    background-color: transparent;
}}
.tahmo-banner {{
    background: linear-gradient(120deg, {ACCENT_DARK} 0%, {ACCENT} 100%);
    color: #F6F8F6;
    padding: 28px 32px;
    border-radius: 10px;
    margin-bottom: 20px;
}}
.tahmo-banner h1 {{
    margin: 0;
    font-size: 1.7rem;
    font-weight: 700;
    letter-spacing: -0.01em;
}}
.tahmo-banner p {{
    margin: 6px 0 0 0;
    opacity: 0.85;
    font-size: 0.92rem;
}}
[data-testid="stMetric"] {{
    background-color: {CARD_BG};
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
    padding: 14px 16px;
}}
[data-testid="stMetricValue"] {{
    font-family: 'IBM Plex Mono', monospace;
}}
.signal-row {{ display: flex; align-items: center; gap: 6px; }}
.signal-bars {{ display: inline-flex; align-items: flex-end; gap: 2px; height: 14px; }}
.signal-bars .bar {{ width: 4px; border-radius: 1px; background: {HAIRLINE}; }}
.signal-bars .bar.on {{ background: var(--bar-color, {ACCENT}); }}
.stTabs [data-baseweb="tab"] {{
    font-weight: 600;
}}
div[data-testid="stExpander"] {{
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
}}
</style>
"""

WINDOW_OPTIONS = ["Now", "Last 24 hours", "Last 1 week", "Last 2 weeks",
                   "Last month", "Last 6 months", "Last 1 year", "Since installation"]
_WINDOW_DAYS = {
    "Last 24 hours": 1, "Last 1 week": 7, "Last 2 weeks": 14,
    "Last month": 30, "Last 6 months": 182, "Last 1 year": 365,
}


def resolve_window(preset: str, install_date: str | None):
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    if preset == "Now":
        return now - timedelta(hours=1), now
    if preset in _WINDOW_DAYS:
        return now - timedelta(days=_WINDOW_DAYS[preset]), now
    if preset == "Since installation":
        if install_date:
            try:
                start = datetime.fromisoformat(install_date).replace(tzinfo=timezone.utc)
                return start, now
            except ValueError:
                pass
        return now - timedelta(days=365), now
    return now - timedelta(days=7), now


def signal_bars_html(pct: float | None, n=5) -> str:
    """Signature element: a signal-strength style indicator for % reporting.
    Reused across the map table, site detail, and comparison view."""
    if pct is None:
        return "<span class='signal-row'><em>no data</em></span>"
    lit = round((pct / 100) * n)
    color = STATUS_COLORS["Online"] if pct >= 90 else STATUS_COLORS["Data Gaps"] if pct >= 50 else STATUS_COLORS["Offline"]
    bars = "".join(
        f"<div class='bar {'on' if i < lit else ''}' style='height:{6 + i * 2}px; --bar-color:{color}'></div>"
        for i in range(n)
    )
    return f"<div class='signal-row'><div class='signal-bars'>{bars}</div><span>{pct:.0f}%</span></div>"


# ---------------------------------------------------------------------------
@st.cache_data(ttl=60)
def load_devices():
    return list_devices()


@st.cache_data(ttl=3600, show_spinner="Syncing latest data from Arable...")
def sync_from_arable():
    """Pull the newest readings + battery from the real Arable API, at most
    once per hour. No-ops quietly if no API key is configured. Never raises
    -- returns a status string so the dashboard can show what happened."""
    if not ARABLE_API_KEY:
        return "no_key"
    from arable_client import ArableClient
    from ingest import seed_site_registry, sync_battery_from_devices, sync_readings
    from sites import SITE_REGISTRY

    try:
        seed_site_registry()
        client = ArableClient()
        device_ids = [s["device_id"] for s in SITE_REGISTRY]
        sync_battery_from_devices(client)
        sync_readings(client, device_ids)
        return "synced"
    except Exception as e:
        return f"error: {type(e).__name__}: {e}"


def compute_fleet_status(devices):
    rows = []
    for d in devices:
        s = device_status(d["device_id"])
        rows.append({**d, **s})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
def render_overview(devices_df: pd.DataFrame):
    st.subheader("Network Overview")

    counts = devices_df["status"].value_counts()
    cols = st.columns(5)
    cols[0].metric("Total sites", len(devices_df))
    cols[1].metric("Online", int(counts.get("Online", 0)))
    cols[2].metric("Data Gaps", int(counts.get("Data Gaps", 0)))
    cols[3].metric("Offline", int(counts.get("Offline", 0)))
    no_location = devices_df["lat"].isna().sum()
    cols[4].metric("No current site", int(no_location))

    mappable = devices_df.dropna(subset=["lat", "lon"]).copy()
    if not mappable.empty:
        mappable["marker_color"] = mappable["status"].map(STATUS_COLORS).fillna(STATUS_COLORS["No Data"])
        fig = go.Figure(go.Scattermap(
            lat=mappable["lat"], lon=mappable["lon"],
            mode="markers",
            marker=dict(size=14, color=mappable["marker_color"]),
            text=mappable["site_name"],
            customdata=mappable["device_id"],
            hovertemplate="<b>%{text}</b><br>%{customdata}<extra></extra>",
        ))
        fig.update_layout(
            map=dict(style="carto-positron", zoom=4.2,
                     center=dict(lat=mappable["lat"].mean(), lon=mappable["lon"].mean())),
            margin=dict(l=0, r=0, t=0, b=0), height=460,
        )
        event = st.plotly_chart(fig, width='stretch', on_select="rerun", key="site_map")
        points = event.get("selection", {}).get("points", []) if event else []
        if points:
            clicked_id = points[0].get("customdata")
            if clicked_id:
                st.session_state["selected_device"] = clicked_id
                st.info(f"Selected **{clicked_id}** — open the **Site Detail** tab to see its data.", icon="📍")
    else:
        st.info("No sites with known coordinates yet.")

    st.caption("Reporting % below reflects the last 24 hours, per site, across all tracked parameters.")
    rows = []
    for _, d in devices_df.iterrows():
        start, end = resolve_window("Last 24 hours", d.get("install_date"))
        pcts = []
        for param in TRACKED_PARAMETERS:
            c, _ = find_gaps(d["device_id"], param, start, end)
            pcts.append(c)
        avg_pct = sum(pcts) / len(pcts) if pcts else None
        rows.append({
            "Device": d["device_id"], "Site": d["site_name"], "Country": d["country"],
            "Status": d["status"], "Reporting (24h)": avg_pct,
        })
    table_df = pd.DataFrame(rows).sort_values("Reporting (24h)", na_position="first")
    table_df["Reporting (24h)"] = table_df["Reporting (24h)"].apply(signal_bars_html)
    st.markdown(table_df.to_html(escape=False, index=False), unsafe_allow_html=True)


# ---------------------------------------------------------------------------
def render_site_detail(devices_df: pd.DataFrame):
    st.subheader("Site Detail")

    site_labels = {
        row["device_id"]: f"{row['site_name']} ({row['device_id']}) — {row['country']}"
        for _, row in devices_df.iterrows()
    }
    device_ids = list(site_labels.keys())
    default_idx = device_ids.index(st.session_state["selected_device"]) if st.session_state.get("selected_device") in device_ids else 0
    device_id = st.selectbox("Site", options=device_ids, index=default_idx, format_func=lambda x: site_labels[x])
    st.session_state["selected_device"] = device_id

    window = st.radio("Time window", WINDOW_OPTIONS, horizontal=True, index=2)

    row = devices_df[devices_df["device_id"] == device_id].iloc[0]
    start, end = resolve_window(window, row.get("install_date"))

    badge_color = STATUS_COLORS.get(row["status"], "#9AA5A0")
    st.markdown(
        f"**Live status:** <span style='color:{badge_color}; font-weight:700'>{row['status']}</span>"
        f" &nbsp;|&nbsp; Last reading: {row['last_seen'] or 'never'}"
        f" &nbsp;|&nbsp; Region: {row.get('region') or '—'} &nbsp;|&nbsp; Org: {row.get('org') or '—'}",
        unsafe_allow_html=True,
    )
    if row.get("note"):
        st.caption(f"ℹ️ {row['note']}")
    if window == "Since installation" and not row.get("install_date"):
        st.caption("No confirmed install date on file for this device — defaulted to the last 365 days.")

    st.markdown("#### Reporting completeness this window")
    param_cols = st.columns(len(TRACKED_PARAMETERS))
    for col, (param, (label, unit)) in zip(param_cols, TRACKED_PARAMETERS.items()):
        completeness, _ = find_gaps(device_id, param, start, end)
        col.metric(label, f"{completeness:.0f}%")

    for param, (label, unit) in TRACKED_PARAMETERS.items():
        rows = get_readings(device_id, param, start.isoformat(), end.isoformat())
        completeness, gaps = find_gaps(device_id, param, start, end)

        with st.expander(f"{label} ({unit}) — {completeness:.0f}% complete, {len(gaps)} gap(s)", expanded=(param == "tair")):
            if not rows:
                st.info("No data in this window.")
                continue
            df = pd.DataFrame(rows)
            df["timestamp"] = pd.to_datetime(df["timestamp"])

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df["timestamp"], y=df["value"], mode="lines",
                                      name=label, line=dict(width=2, color=ACCENT)))
            for gap in gaps:
                fig.add_vrect(x0=gap["start"], x1=gap["end"] + timedelta(minutes=59),
                              fillcolor=STATUS_COLORS["Offline"], opacity=0.12, line_width=0,
                              annotation_text=f"{gap['hours']}h gap", annotation_position="top left")
            fig.update_layout(margin=dict(l=10, r=10, t=30, b=10), height=260,
                               yaxis_title=unit, showlegend=False,
                               plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG)
            st.plotly_chart(fig, width='stretch')
            if gaps:
                st.dataframe(pd.DataFrame(gaps), hide_index=True, width='stretch')

    st.markdown("#### Battery")
    batt_rows = get_battery_readings(device_id, start.isoformat(), end.isoformat())
    if batt_rows:
        bdf = pd.DataFrame(batt_rows)
        bdf["timestamp"] = pd.to_datetime(bdf["timestamp"])
        fig = go.Figure()
        for source, sub in bdf.groupby("source"):
            fig.add_trace(go.Scatter(x=sub["timestamp"], y=sub["battery_pct"], mode="lines+markers",
                                      name=source, line=dict(width=2)))
        fig.update_layout(margin=dict(l=10, r=10, t=20, b=10), height=240,
                           yaxis_title="%", yaxis_range=[0, 100],
                           plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG)
        st.plotly_chart(fig, width='stretch')
    else:
        st.info("No battery data yet for this window. Arable's public API doesn't confirm a battery field, "
                "so log a reading manually below (e.g. after a site visit).")

    with st.form(key=f"battery_log_{device_id}"):
        c1, c2 = st.columns([2, 1])
        pct = c1.slider("Battery level observed (%)", 0, 100, 80)
        submit = c2.form_submit_button("Log reading")
        if submit:
            with get_conn() as conn:
                upsert_battery_reading(conn, device_id, datetime.now(timezone.utc).isoformat(),
                                        float(pct), "manual", f"{pct}%")
            st.success(f"Logged {pct}% for {device_id}.")
            st.rerun()


# ---------------------------------------------------------------------------
def render_compare(devices_df: pd.DataFrame):
    st.subheader("Compare Sites")

    c1, c2 = st.columns(2)
    param = c1.selectbox("Parameter", options=list(TRACKED_PARAMETERS.keys()),
                          format_func=lambda p: TRACKED_PARAMETERS[p][0])
    window = c2.selectbox("Time window", options=WINDOW_OPTIONS, index=2)

    rows = []
    for _, d in devices_df.iterrows():
        if pd.isna(d["lat"]):
            continue
        start, end = resolve_window(window, d.get("install_date"))
        completeness, _ = find_gaps(d["device_id"], param, start, end)
        rows.append({"Site": d["site_name"], "Device": d["device_id"], "Completeness": completeness})

    if not rows:
        st.info("No installed sites to compare.")
        return

    cmp_df = pd.DataFrame(rows).sort_values("Completeness")
    fig = go.Figure(go.Bar(
        x=cmp_df["Completeness"], y=cmp_df["Site"], orientation="h",
        marker_color=[STATUS_COLORS["Online"] if v >= 90 else STATUS_COLORS["Data Gaps"] if v >= 50
                      else STATUS_COLORS["Offline"] for v in cmp_df["Completeness"]],
    ))
    fig.update_layout(height=max(300, 28 * len(cmp_df)), margin=dict(l=10, r=10, t=10, b=10),
                       xaxis_title="% reporting", plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG)
    st.plotly_chart(fig, width='stretch')

    st.markdown("#### Battery snapshot (latest reading per site)")
    batt_rows = []
    for _, d in devices_df.iterrows():
        if pd.isna(d["lat"]):
            continue
        hist = get_battery_readings(d["device_id"])
        latest = hist[-1] if hist else None
        batt_rows.append({
            "Site": d["site_name"], "Device": d["device_id"],
            "Battery %": latest["battery_pct"] if latest else None,
            "As of": latest["timestamp"] if latest else "—",
        })
    st.dataframe(pd.DataFrame(batt_rows).sort_values("Battery %", na_position="first"),
                 hide_index=True, width='stretch')


# ---------------------------------------------------------------------------
def main():
    init_db()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='tahmo-banner'><h1>🛰️ Arable Sensor Network Dashboard</h1>"
        "<p>Live status, data completeness, and battery health across every installed site.</p></div>",
        unsafe_allow_html=True,
    )

    top_col1, top_col2 = st.columns([1, 5])
    with top_col1:
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

    with st.expander("🔧 Debug: API key detection", expanded=(sync_result not in ("synced",))):
        st.json(ARABLE_API_KEY_DEBUG)
    load_devices.clear()

    devices = load_devices()
    if not devices:
        st.warning("No devices found. Run `python mock_data.py` for a demo, or `python ingest.py` to pull real data.")
        return

    devices_df = compute_fleet_status(devices)
    if "selected_device" not in st.session_state:
        st.session_state["selected_device"] = devices_df.iloc[0]["device_id"]

    tab1, tab2, tab3 = st.tabs(["📍 Overview", "🔍 Site Detail", "📊 Compare"])
    with tab1:
        render_overview(devices_df)
    with tab2:
        render_site_detail(devices_df)
    with tab3:
        render_compare(devices_df)


if __name__ == "__main__":
    main()
