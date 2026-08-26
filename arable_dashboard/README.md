# Arable Sensor Network Dashboard

A Streamlit app that pulls data from Arable sensors into a local database and
shows it as one dashboard: a **fleet overview** (which sites are online,
gappy, or offline) and a **site detail** view (click a site, see its trend
per parameter, with missing-data windows shaded on the chart).

## How it's structured

| File | Purpose |
|---|---|
| `config.py` | API key (from env var), tracked parameters, gap thresholds |
| `arable_client.py` | Talks to the real Arable API (auth, pagination) |
| `db.py` | SQLite storage: `devices` and `readings` tables |
| `gap_analysis.py` | Compares expected vs. actual timestamps -> gaps + status |
| `ingest.py` | Pulls devices + hourly data from Arable into SQLite |
| `mock_data.py` | Generates a realistic fake dataset for demoing without a live key |
| `app.py` | The Streamlit dashboard itself |

## 1. Try it now, with mock data

```bash
pip install -r requirements.txt
python mock_data.py        # creates arable_data.db with 15 fake sites, 14 days of data
streamlit run app.py
```

This includes three sites with deliberately broken data (one offline, one
with scattered gaps, one with a multi-day outage) so you can see exactly what
the gap detection looks like before touching the real API.

## 2. Connect your real Arable account

1. In Arable, go to **Settings > Account** and note (or refresh) your API key.
   **Never paste this key into chat, screenshots, or code.** Set it as an
   environment variable instead:

   ```bash
   export ARABLE_API_KEY="your-key-here"
   ```

2. Pull real data:

   ```bash
   python ingest.py --days 14   # first run: backfill 14 days for every device
   ```

   After that, run `python ingest.py` (no `--days`) on a schedule — it only
   pulls what's new since each device's last stored reading. Good options:
   - a cron job (`0 * * * * cd /path/to/arable_dashboard && python ingest.py`)
   - a scheduled GitHub Action
   - Windows Task Scheduler

3. Launch the dashboard:

   ```bash
   streamlit run app.py
   ```

## 3. Adjusting things

- **Which parameters show up**: edit `TRACKED_PARAMETERS` in `config.py`.
  These must match real Arable column names (see the Arable Data Dictionary
  for the full list — e.g. `moisture_0_mean` for 10cm soil moisture from a
  Sentek probe).
- **What counts as a "gap" or "offline"**: `GAP_THRESHOLD_HOURS` and
  `OFFLINE_AFTER_HOURS` in `config.py`.
- **Which table you pull from**: `DATA_TABLE` in `config.py` (`hourly` is
  recommended for comparing sites; Arable also has `daily`, `local_hourly`,
  `sentek_hourly`, etc. — see their Data Dictionary PDF).

## Notes on the Arable API

- Base URL: `https://api.arable.cloud/api/v2`
- Auth header: `Authorization: Apikey <key>`
- Devices/locations: paginated with `limit`/`page`
- Time series (`/data/<table>`): paginated with `limit`/`cursor`
  (`cursor` comes from the `X-Cursor-Next` response header)
- Default limits: 100 days of hourly data or ~7 days of 5-minute data per call
  — `ingest.py` already handles this via cursor pagination, so backfills of
  any length will work, just slower for very long ranges.

## Deploying for free on GitHub + Streamlit Community Cloud

1. Push this folder to a **new GitHub repo** (`arable_data.db` is gitignored —
   don't commit it; the app regenerates/pulls its own data).
2. Go to https://share.streamlit.io, sign in with GitHub, click **New app**,
   and point it at your repo with main file `app.py`.
3. In that app's **Settings > Secrets**, paste:
   ```
   ARABLE_API_KEY = "your-key-here"
   ```
   (this is the equivalent of the env var, just for the hosted environment —
   `config.py` already checks both).
4. Deploy. The app pulls fresh data from Arable itself once an hour
   (`sync_from_arable()` in `app.py`, cached with `ttl=3600`) — no separate
   cron job needed on the free tier. If you leave the `ARABLE_API_KEY` secret
   out, it just shows whatever's in the local database (e.g. mock data) and
   tells you the key is missing.

**One limitation to know about:** Streamlit Cloud's filesystem (and so the
SQLite file) resets whenever the app restarts — after inactivity, a redeploy,
or a platform update. Since the app re-syncs the last ~7 days on its own each
time it wakes up, this is usually invisible for a "current status" dashboard.
If you later want the *history* to survive restarts too (for long-term trend
analysis, not just live status), move `DB_PATH` to a small free hosted
database instead of local SQLite — e.g. a free Postgres on Supabase, or
Turso's free SQLite-compatible tier — and swap the `sqlite3` calls in `db.py`
for that driver.

## Scaling to dozens of sites

The current design (SQLite + a scheduled `ingest.py`) comfortably handles
dozens of devices at hourly resolution. If TAHMO wants this to grow toward
the AWS network's scale (100+), the two things to revisit first are:
swapping SQLite for Postgres, and running ingestion as smaller
per-country/per-device batches so one slow device doesn't delay the rest.
