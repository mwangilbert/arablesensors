"""
Thin wrapper around the Arable Developer API (https://developer.arable.com).

Auth: header "Authorization: Apikey <key>"
Devices/Locations: limit + page pagination -> {"items": [...], "pages": N, ...}
Time series data (/data/<table>): limit + cursor pagination via X-Cursor-Next header
"""

import requests

from config import ARABLE_API_KEY, ARABLE_BASE_URL


class ArableClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or ARABLE_API_KEY
        if not self.api_key:
            raise ValueError(
                "No Arable API key found. Set the ARABLE_API_KEY environment "
                "variable before running ingestion."
            )
        self.session = requests.Session()
        self.session.headers.update({"Authorization": f"Apikey {self.api_key}"})

    # -- model resources (paginated by page number) ------------------------
    def _get_all_pages(self, path: str, extra_params: dict | None = None):
        items = []
        page = 1
        while True:
            params = {"limit": 500, "page": page, **(extra_params or {})}
            r = self.session.get(f"{ARABLE_BASE_URL}/{path}", params=params, timeout=30)
            r.raise_for_status()
            data = r.json()
            items.extend(data.get("items", []))
            if page >= data.get("pages", 1):
                break
            page += 1
        return items

    def get_devices(self):
        return self._get_all_pages("devices")

    def get_locations(self):
        return self._get_all_pages("locations")

    # -- time series data (paginated by cursor) -----------------------------
    def get_data(
        self,
        table: str,
        device: str | None = None,
        location: str | None = None,
        start_time: str | None = None,
        end_time: str | None = None,
        select: list[str] | None = None,
        limit: int = 2000,
    ):
        """Fetch all rows for a table/device/date-range, following cursor pagination."""
        url = f"{ARABLE_BASE_URL}/data/{table}"
        params = {"limit": limit}
        if device:
            params["device"] = device
        if location:
            params["location"] = location
        if start_time:
            params["start_time"] = start_time
        if end_time:
            params["end_time"] = end_time
        if select:
            params["select"] = ",".join(select)

        all_rows = []
        cursor = None
        while True:
            req_params = dict(params)
            if cursor:
                req_params["cursor"] = cursor
            r = self.session.get(url, params=req_params, timeout=60)
            r.raise_for_status()
            rows = r.json()
            if isinstance(rows, dict) and "message" in rows:
                # API returned an error/message body instead of a row list
                break
            all_rows.extend(rows)
            cursor = r.headers.get("X-Cursor-Next")
            if not cursor:
                break
        return all_rows
