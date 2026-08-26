"""
Arable Sensor Network Dashboard

Views:
  1. Overview     - map of every site (click to select), fleet health summary
  2. Site Detail  - selected site's trends, every parameter on one combined
                     chart, with a flexible time window and % reporting per
                     parameter
  3. Compare      - cross-site data-availability comparison

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

st.set_page_config(page_title="Arable Network Dashboard", layout="wide", page_icon="🛰️")

# ---------------------------------------------------------------------------
# Design tokens -- a deliberate, deliberately colorful palette built around
# one signature accent per page (Overview=teal, Site Detail=blue,
# Compare=purple), status colors reserved strictly for health (green/amber/
# red/gray), and a five-color parameter palette for the trend chart.
# ---------------------------------------------------------------------------
INK = "#152521"
MUTED = "#5B6B66"
PANEL_BG = "#F6F8F6"
CARD_BG = "#FFFFFF"
HAIRLINE = "#E1E7E3"
ACCENT = "#1F6F6F"        # deep teal -- brand accent
ACCENT_DARK = "#123F3F"

PAGE_ACCENTS = {
    "overview": "#1F6F6F",      # teal
    "site_detail": "#3B6FB6",   # blue
    "compare": "#7A4FB5",       # purple
}

STATUS_COLORS = {
    "Online": "#2E8B57",
    "Data Gaps": "#D9A21B",
    "Offline": "#C1443C",
    "No Data": "#9AA5A0",
}
# One distinct color per tracked parameter, deliberately clear of the status
# palette above (no red/green/amber) so a parameter's color is never mistaken
# for a health signal.
PARAM_COLORS = {
    "tair": "#1F6F6F",     # teal
    "rh": "#3B6FB6",       # blue
    "precip": "#7A4FB5",   # purple
    "slp": "#B5651D",      # rust
    "pardw": "#C2568B",    # magenta
}
_PARAM_COLOR_FALLBACKS = ["#1F6F6F", "#3B6FB6", "#7A4FB5", "#B5651D", "#C2568B", "#4C7A3D", "#8A8A3C"]


def param_color(param: str, index: int) -> str:
    return PARAM_COLORS.get(param, _PARAM_COLOR_FALLBACKS[index % len(_PARAM_COLOR_FALLBACKS)])


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

/* Slim header -- one line, icon + title + subtitle, minimal vertical space
   so the page gets straight to data. */
.app-header {{
    display: flex;
    align-items: baseline;
    gap: 10px;
    padding: 6px 2px 14px 2px;
    border-bottom: 2px solid {HAIRLINE};
    margin-bottom: 16px;
}}
.app-header-icon {{ font-size: 1.25rem; }}
.app-header-title {{
    font-size: 1.15rem;
    font-weight: 700;
    color: {INK};
    letter-spacing: -0.01em;
}}
.app-header-sub {{
    font-size: 0.85rem;
    color: {MUTED};
}}

/* Section titles -- a colored left rule per page accent, used instead of
   plain st.subheader so every page reads as deliberately colorful. */
.section-title {{
    font-size: 1.05rem;
    font-weight: 700;
    color: {INK};
    border-left: 4px solid var(--accent, {ACCENT});
    padding: 2px 0 2px 10px;
    margin: 20px 0 10px 0;
}}

/* Colored stat cards -- replace plain st.metric so counts/percentages carry
   color meaning at a glance. */
.metric-card {{
    background: {CARD_BG};
    border: 1px solid {HAIRLINE};
    border-left: 4px solid var(--c, {ACCENT});
    border-radius: 8px;
    padding: 10px 14px 12px 14px;
    box-shadow: 0 1px 2px rgba(21, 37, 33, 0.04);
}}
.metric-card .mc-label {{
    font-size: 0.72rem;
    font-weight: 600;
    color: {MUTED};
    text-transform: uppercase;
    letter-spacing: 0.04em;
}}
.metric-card .mc-value {{
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.55rem;
    font-weight: 700;
    color: var(--c, {ACCENT});
    line-height: 1.3;
}}
.metric-card .mc-sub {{
    font-size: 0.74rem;
    color: {MUTED};
}}

/* Status pill badges */
.status-pill {{
    display: inline-block;
    padding: 2px 11px;
    border-radius: 999px;
    font-size: 0.78rem;
    font-weight: 700;
    white-space: nowrap;
}}

/* Compare-tab color legend */
.legend-row {{
    display: flex;
    gap: 20px;
    flex-wrap: wrap;
    align-items: center;
    margin: 4px 0 16px 0;
}}
.legend-chip {{
    display: flex;
    align-items: center;
    gap: 7px;
    font-size: 0.86rem;
    color: {INK};
}}
.legend-dot {{
    width: 11px;
    height: 11px;
    border-radius: 50%;
    display: inline-block;
    flex-shrink: 0;
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
.stTabs [data-baseweb="tab-list"] button:nth-child(1)[aria-selected="true"] {{
    border-bottom-color: {PAGE_ACCENTS['overview']} !important;
    color: {PAGE_ACCENTS['overview']} !important;
}}
.stTabs [data-baseweb="tab-list"] button:nth-child(2)[aria-selected="true"] {{
    border-bottom-color: {PAGE_ACCENTS['site_detail']} !important;
    color: {PAGE_ACCENTS['site_detail']} !important;
}}
.stTabs [data-baseweb="tab-list"] button:nth-child(3)[aria-selected="true"] {{
    border-bottom-color: {PAGE_ACCENTS['compare']} !important;
    color: {PAGE_ACCENTS['compare']} !important;
}}
div[data-testid="stExpander"] {{
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
}}

/* Wide HTML tables (Overview) scroll horizontally inside their own box
   instead of forcing the whole page to scroll sideways on a phone. */
.table-scroll {{
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    border: 1px solid {HAIRLINE};
    border-radius: 8px;
}}
.table-scroll table {{
    border-collapse: collapse;
    width: 100%;
}}
.table-scroll th, .table-scroll td {{
    padding: 6px 12px;
    white-space: nowrap;
}}

/* Phone-width tightening -- smaller header/cards/legend so the layout
   doesn't feel oversized on a narrow screen. */
@media (max-width: 640px) {{
    .app-header {{ flex-wrap: wrap; padding: 4px 0 10px 0; }}
    .app-header-title {{ font-size: 1.02rem; }}
    .app-header-sub {{ font-size: 0.78rem; }}
    .section-title {{ font-size: 0.95rem; margin: 14px 0 8px 0; }}
    .metric-card {{ padding: 8px 10px 10px 10px; }}
    .metric-card .mc-value {{ font-size: 1.25rem; }}
    .legend-row {{ gap: 12px; }}
    .legend-chip {{ font-size: 0.78rem; }}
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


def completeness_color(pct: float | None) -> str:
    if pct is None:
        return STATUS_COLORS["No Data"]
    return STATUS_COLORS["Online"] if pct >= 90 else STATUS_COLORS["Data Gaps"] if pct >= 50 else STATUS_COLORS["Offline"]


def site_tag(site_name: str, device_id: str) -> str:
    """'Moi University [D006023]' -- the standard way a site is named
    anywhere in the app, so its device ID is always visible alongside it."""
    return f"{site_name} [{device_id}]"


def signal_bars_html(pct: float | None, n=5) -> str:
    """Signature element: a signal-strength style indicator for % reporting.
    Reused across the map table, site detail, and comparison view."""
    if pct is None:
        return "<span class='signal-row'><em>no data</em></span>"
    lit = round((pct / 100) * n)
    color = completeness_color(pct)
    bars = "".join(
        f"<div class='bar {'on' if i < lit else ''}' style='height:{6 + i * 2}px; --bar-color:{color}'></div>"
        for i in range(n)
    )
    return f"<div class='signal-row'><div class='signal-bars'>{bars}</div><span>{pct:.0f}%</span></div>"


def status_pill_html(status: str) -> str:
    color = STATUS_COLORS.get(status, STATUS_COLORS["No Data"])
    return (f"<span class='status-pill' style='color:{color}; background:{color}1F; "
            f"border:1px solid {color}55'>{status}</span>")


def metric_card_html(label: str, value: str, color: str, sub: str | None = None) -> str:
    sub_html = f"<div class='mc-sub'>{sub}</div>" if sub else ""
    return (f"<div class='metric-card' style='--c:{color}'>"
            f"<div class='mc-label'>{label}</div>"
            f"<div class='mc-value'>{value}</div>{sub_html}</div>")


def section_title(text: str, color: str):
    st.markdown(f"<div class='section-title' style='--accent:{color}'>{text}</div>", unsafe_allow_html=True)


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
    accent = PAGE_ACCENTS["overview"]
    section_title("Network Overview", accent)

    counts = devices_df["status"].value_counts()
    no_location = devices_df["lat"].isna().sum()
    cards = [
        ("Total sites", str(len(devices_df)), accent),
        ("Online", str(int(counts.get("Online", 0))), STATUS_COLORS["Online"]),
        ("Data Gaps", str(int(counts.get("Data Gaps", 0))), STATUS_COLORS["Data Gaps"]),
        ("Offline", str(int(counts.get("Offline", 0))), STATUS_COLORS["Offline"]),
        ("No current site", str(int(no_location)), STATUS_COLORS["No Data"]),
    ]
    for col, (label, value, color) in zip(st.columns(5), cards):
        col.markdown(metric_card_html(label, value, color), unsafe_allow_html=True)

    st.write("")
    mappable = devices_df.dropna(subset=["lat", "lon"]).copy()
    if not mappable.empty:
        mappable["marker_color"] = mappable["status"].map(STATUS_COLORS).fillna(STATUS_COLORS["No Data"])
        mappable["label"] = [site_tag(n, i) for n, i in zip(mappable["site_name"], mappable["device_id"])]
        fig = go.Figure(go.Scattermap(
            lat=mappable["lat"], lon=mappable["lon"],
            mode="markers",
            marker=dict(size=14, color=mappable["marker_color"]),
            text=mappable["label"],
            customdata=mappable["device_id"],
            hovertemplate="<b>%{text}</b><extra></extra>",
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

    section_title("Fleet reporting (last 24h)", accent)
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
            "Site": site_tag(d["site_name"], d["device_id"]), "Country": d["country"],
            "Status": d["status"], "Reporting (24h)": avg_pct,
        })
    table_df = pd.DataFrame(rows).sort_values("Reporting (24h)", na_position="first")
    table_df["Status"] = table_df["Status"].apply(status_pill_html)
    table_df["Reporting (24h)"] = table_df["Reporting (24h)"].apply(signal_bars_html)
    st.markdown(
        f"<div class='table-scroll'>{table_df.to_html(escape=False, index=False)}</div>",
        unsafe_allow_html=True,
    )


def _stacked_axis_layout(n: int, step: float = 0.07):
    """Positions for n y-axes sharing one x-axis, alternating left/right and
    stepping further out for each extra axis on the same side. Returns
    (per-axis kwargs list, xaxis domain) -- the domain is narrowed so the
    outer axes have room to sit outside the plot area instead of overlapping it."""
    sides = ["left" if i % 2 == 0 else "right" for i in range(n)]
    extra_left = max(0, sides.count("left") - 1)
    extra_right = max(0, sides.count("right") - 1)
    domain_left = extra_left * step
    domain_right = 1 - extra_right * step

    layout = []
    for i, side in enumerate(sides):
        before = sides[:i].count(side)
        if before == 0:
            layout.append({"side": side, "anchor": "x", "position": None})
        else:
            position = (domain_left - before * step) if side == "left" else (domain_right + before * step)
            layout.append({"side": side, "anchor": "free", "position": position})
    return layout, (domain_left, domain_right)


def render_parameter_trends(device_id: str, start, end, param_data: list[dict]):
    """One chart, every tracked parameter as its own trace on its own
    color-matched axis -- so a healthy station shows every line moving, and a
    flat or absent line points straight at what stopped reporting."""
    n = len(param_data)
    axis_layout, (domain_left, domain_right) = _stacked_axis_layout(n)

    fig = go.Figure()
    layout_kwargs = {"xaxis": dict(domain=[domain_left, domain_right])}
    any_reading = False

    for i, item in enumerate(param_data):
        color = param_color(item["param"], i)
        axis_key = "yaxis" if i == 0 else f"yaxis{i + 1}"
        trace_axis = "y" if i == 0 else f"y{i + 1}"
        al = axis_layout[i]

        axis_kwargs = dict(
            title=dict(text=f"{item['label']} ({item['unit']})", font=dict(color=color, size=11)),
            tickfont=dict(color=color, size=10),
            linecolor=color, tickcolor=color, ticks="outside",
            showgrid=(i == 0), zeroline=False, side=al["side"],
        )
        if i > 0:
            axis_kwargs["overlaying"] = "y"
        if al["anchor"] == "free":
            axis_kwargs["anchor"] = "free"
            axis_kwargs["position"] = al["position"]
        layout_kwargs[axis_key] = axis_kwargs

        if item["rows"]:
            any_reading = True
            df = pd.DataFrame(item["rows"])
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            fig.add_trace(go.Scatter(
                x=df["timestamp"], y=df["value"], mode="lines",
                name=f"{item['label']} ({item['unit']})",
                line=dict(width=2, color=color), yaxis=trace_axis,
            ))

    fig.update_layout(
        **layout_kwargs,
        margin=dict(l=10, r=10, t=10, b=10), height=440,
        plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG,
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    )
    st.plotly_chart(fig, width='stretch')
    if not any_reading:
        st.info("No data in this window for any tracked parameter.")


# ---------------------------------------------------------------------------
def render_site_detail(devices_df: pd.DataFrame):
    accent = PAGE_ACCENTS["site_detail"]
    section_title("Site Detail", accent)

    site_labels = {
        row["device_id"]: f"{site_tag(row['site_name'], row['device_id'])} — {row['country']}"
        for _, row in devices_df.iterrows()
    }
    device_ids = list(site_labels.keys())
    default_idx = device_ids.index(st.session_state["selected_device"]) if st.session_state.get("selected_device") in device_ids else 0
    device_id = st.selectbox("Site", options=device_ids, index=default_idx, format_func=lambda x: site_labels[x])
    st.session_state["selected_device"] = device_id

    window = st.selectbox("Time window", WINDOW_OPTIONS, index=2, key="site_detail_window")

    row = devices_df[devices_df["device_id"] == device_id].iloc[0]
    start, end = resolve_window(window, row.get("install_date"))

    st.markdown(
        f"**Live status:** {status_pill_html(row['status'])}"
        f" &nbsp;|&nbsp; Last reading: {row['last_seen'] or 'never'}"
        f" &nbsp;|&nbsp; Region: {row.get('region') or '—'} &nbsp;|&nbsp; Org: {row.get('org') or '—'}",
        unsafe_allow_html=True,
    )
    if row.get("note"):
        st.caption(f"ℹ️ {row['note']}")
    if window == "Since installation" and not row.get("install_date"):
        st.caption("No confirmed install date on file for this device — defaulted to the last 365 days.")

    param_data = []
    for param, (label, unit) in TRACKED_PARAMETERS.items():
        rows = get_readings(device_id, param, start.isoformat(), end.isoformat())
        completeness, gaps = find_gaps(device_id, param, start, end)
        param_data.append({
            "param": param, "label": label, "unit": unit,
            "rows": rows, "completeness": completeness, "gaps": gaps,
        })

    section_title("Reporting completeness this window", accent)
    param_cols = st.columns(len(param_data))
    for col, item in zip(param_cols, param_data):
        color = completeness_color(item["completeness"])
        gap_note = f"{len(item['gaps'])} gap(s)" if item["gaps"] else "no gaps"
        col.markdown(metric_card_html(item["label"], f"{item['completeness']:.0f}%", color, gap_note),
                     unsafe_allow_html=True)

    section_title("All parameters, one timeline", accent)
    st.caption("Every tracked parameter plotted together, each on its own color-matched scale — "
               "a working station shows every line moving; a flat or missing line points straight "
               "at what stopped reporting.")
    render_parameter_trends(device_id, start, end, param_data)

    gap_rows = [
        {"Parameter": item["label"], "Gap start": g["start"], "Gap end": g["end"], "Hours": g["hours"]}
        for item in param_data for g in item["gaps"]
    ]
    if gap_rows:
        with st.expander(f"Gap details ({len(gap_rows)})"):
            st.dataframe(pd.DataFrame(gap_rows), hide_index=True, width='stretch')


# ---------------------------------------------------------------------------
def render_compare(devices_df: pd.DataFrame):
    accent = PAGE_ACCENTS["compare"]
    section_title("Compare Sites", accent)

    c1, c2 = st.columns(2)
    param = c1.selectbox("Parameter", options=list(TRACKED_PARAMETERS.keys()),
                          format_func=lambda p: TRACKED_PARAMETERS[p][0])
    window = c2.selectbox("Time window", options=WINDOW_OPTIONS, index=2, key="compare_window")

    rows = []
    for _, d in devices_df.iterrows():
        if pd.isna(d["lat"]):
            continue
        start, end = resolve_window(window, d.get("install_date"))
        completeness, _ = find_gaps(d["device_id"], param, start, end)
        rows.append({
            "Site": site_tag(d["site_name"], d["device_id"]),
            "Completeness": completeness,
        })

    if not rows:
        st.info("No installed sites to compare.")
        return

    cmp_df = pd.DataFrame(rows).sort_values("Completeness")

    st.markdown(
        "<div class='legend-row'>"
        f"<span class='legend-chip'><span class='legend-dot' style='background:{STATUS_COLORS['Online']}'></span>"
        "&ge; 90% reporting (Online)</span>"
        f"<span class='legend-chip'><span class='legend-dot' style='background:{STATUS_COLORS['Data Gaps']}'></span>"
        "50&ndash;89% reporting (Data Gaps)</span>"
        f"<span class='legend-chip'><span class='legend-dot' style='background:{STATUS_COLORS['Offline']}'></span>"
        "&lt; 50% reporting (Offline)</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    avg_pct = cmp_df["Completeness"].mean()
    n_online = int((cmp_df["Completeness"] >= 90).sum())
    n_gaps = int(((cmp_df["Completeness"] >= 50) & (cmp_df["Completeness"] < 90)).sum())
    n_offline = int((cmp_df["Completeness"] < 50).sum())
    summary_cards = [
        ("Average reporting", f"{avg_pct:.0f}%", accent),
        ("Sites ≥ 90%", str(n_online), STATUS_COLORS["Online"]),
        ("Sites 50–89%", str(n_gaps), STATUS_COLORS["Data Gaps"]),
        ("Sites < 50%", str(n_offline), STATUS_COLORS["Offline"]),
    ]
    for col, (label, value, color) in zip(st.columns(4), summary_cards):
        col.markdown(metric_card_html(label, value, color), unsafe_allow_html=True)
    st.write("")

    fig = go.Figure(go.Bar(
        x=cmp_df["Completeness"], y=cmp_df["Site"], orientation="h",
        marker_color=[completeness_color(v) for v in cmp_df["Completeness"]],
        text=[f"{v:.0f}%" for v in cmp_df["Completeness"]],
        textposition="outside",
    ))
    fig.update_layout(height=max(300, 30 * len(cmp_df)), margin=dict(l=10, r=40, t=10, b=10),
                       xaxis_title="% reporting", xaxis_range=[0, 105],
                       plot_bgcolor=CARD_BG, paper_bgcolor=CARD_BG)
    st.plotly_chart(fig, width='stretch')


# ---------------------------------------------------------------------------
def main():
    init_db()
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)
    st.markdown(
        "<div class='app-header'>"
        "<span class='app-header-icon'>🛰️</span>"
        "<span class='app-header-title'>Arable Sensor Network</span>"
        "<span class='app-header-sub'>Live status &amp; data completeness across every installed site</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    sync_result = sync_from_arable()
    load_devices.clear()
    devices = load_devices()

    with st.sidebar:
        st.markdown("#### ⚙️ Controls")
        if st.button("🔄 Sync now", width='stretch'):
            sync_from_arable.clear()
            load_devices.clear()
            st.rerun()

        st.markdown("**Data source**")
        if sync_result == "no_key":
            st.info("No `ARABLE_API_KEY` configured — showing local/mock data.", icon="ℹ️")
        elif sync_result and sync_result.startswith("error"):
            st.error(f"Sync failed: {sync_result}", icon="🚫")
        elif sync_result == "synced":
            st.success("Synced with Arable.", icon="✅")

        with st.expander("🔧 Debug: API key detection", expanded=False):
            st.json(ARABLE_API_KEY_DEBUG)

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
