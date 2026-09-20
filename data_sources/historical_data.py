"""Historical downloads with immutable, checksummed raw responses; no LLM calls."""

import datetime as dt
import hashlib
import json
import re
import time
from pathlib import Path

import requests

UTC = dt.timezone.utc
DAY = dt.timedelta(days=1)
CHARTS = ("hash-rate", "miners-revenue", "n-transactions", "estimated-transaction-volume-usd")


def midnight(value: str) -> dt.datetime:
    return dt.datetime.combine(dt.date.fromisoformat(value), dt.time(), UTC)


def iso(value: dt.datetime) -> str:
    return value.astimezone(UTC).isoformat()


class Archive:
    """Cache by URL and query, verify before reuse, and permit offline rebuilding."""

    def __init__(self, root: Path, offline: bool = False):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.offline = offline
        self.records = []
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Multi-Agent-Crypto-Research/0.1"

    def get(self, url: str, params: dict | None = None, *, as_json=True):
        query = {"url": url, "params": params or {}}
        key = hashlib.sha256(json.dumps(query, sort_keys=True).encode()).hexdigest()
        body_path = self.root / f"{key}.body"
        meta_path = self.root / f"{key}.json"
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())
            body = body_path.read_bytes()
            if hashlib.sha256(body).hexdigest() != meta["sha256"]:
                raise ValueError(f"Raw checksum mismatch: {body_path}")
        else:
            if self.offline:
                raise FileNotFoundError(f"Not archived: {url} {params}")
            response = None
            for attempt in range(3):
                try:
                    response = self.session.get(url, params=params, timeout=(10, 30))
                    if response.status_code not in (429, 500, 502, 503, 504):
                        break
                except requests.RequestException:
                    if attempt == 2:
                        raise
                if attempt < 2:
                    time.sleep(2 ** attempt)
            if response is None:
                raise RuntimeError(f"No response: {url}")
            body = response.content
            meta = {
                **query, "retrieved_at": iso(dt.datetime.now(UTC)),
                "status": response.status_code, "response_url": response.url,
                "sha256": hashlib.sha256(body).hexdigest(), "body_file": body_path.name,
            }
            body_path.write_bytes(body)
            meta_path.write_text(json.dumps(meta, indent=2))
        self.records.append(meta)
        if meta["status"] != 200:
            raise RuntimeError(f"HTTP {meta['status']}: {url}; raw response archived")
        return json.loads(body) if as_json else body.decode("utf-8", errors="replace")


def fetch_market(archive: Archive, start: dt.datetime, end: dt.datetime) -> list:
    """Daily candles with open time in [start, end), paginated in UTC."""
    cursor = int(start.timestamp() * 1000)
    stop = int(end.timestamp() * 1000)
    rows = []
    while cursor < stop:
        page = archive.get("https://data-api.binance.vision/api/v3/klines", {
            "symbol": "BTCUSDT", "interval": "1d", "startTime": cursor,
            "endTime": stop - 1, "limit": 1000,
        })
        if not isinstance(page, list):
            raise ValueError("Binance response must be a list")
        if not page:
            break
        rows.extend(page)
        next_cursor = int(page[-1][0]) + 86_400_000
        if next_cursor <= cursor:
            raise ValueError("Binance pagination did not advance")
        cursor = next_cursor
    return rows


def fetch_onchain(archive: Archive, chart: str, start: dt.datetime, end: dt.datetime) -> list:
    data = archive.get(f"https://api.blockchain.info/charts/{chart}", {
        "start": start.date().isoformat(), "timespan": f"{(end-start).days}days",
        "format": "json", "sampled": "false",
    })
    if data.get("status") != "ok" or not isinstance(data.get("values"), list):
        raise ValueError(f"Invalid chart response: {chart}")
    return data["values"]


def fetch_fear_greed(archive: Archive) -> list:
    data = archive.get("https://api.alternative.me/fng/", {"limit": 0, "format": "json"})
    if data.get("metadata", {}).get("error") or not isinstance(data.get("data"), list):
        raise ValueError("Invalid Fear & Greed response")
    return data["data"]


def parse_forex_calendar(html: str) -> list:
    """Decode the embedded JSON array (never execute JavaScript).

    Epoch dateline is used instead of rendered local time, so DST/display
    timezone does not silently move events. Masked/tentative times stay flagged.
    These are retrospective records, not historical publication vintages.
    """
    match = re.search(r"window\.calendarComponentStates\[\d+\]\s*=\s*\{\s*days:\s*(\[)", html)
    if not match:
        raise ValueError("ForexFactory embedded calendar JSON not found")
    days, _ = json.JSONDecoder().raw_decode(html[match.start(1):])
    if not isinstance(days, list):
        raise ValueError("Unexpected ForexFactory calendar shape")
    result = []
    for day in days:
        for event in day["events"]:
            epoch = event.get("dateline")
            timestamp = iso(dt.datetime.fromtimestamp(float(epoch), UTC)) if epoch else None
            result.append({"event_id": str(event["id"]), "event_time": timestamp,
                           "title": event["name"], "currency": event.get("currency"),
                           "impact": event.get("impactName"), "actual": event.get("actual"),
                           "forecast": event.get("forecast"), "previous": event.get("previous"),
                           "revision": event.get("revision"), "time_label": event.get("timeLabel"),
                           "time_masked": bool(event.get("timeMasked")),
                           "available_at": None, "point_in_time_verified": False,
                           "use_in_primary_features": False})
    return result


def probe_forex(archive: Archive, start: dt.datetime, end: dt.datetime) -> list:
    """Archive weekly calendars for inspection; NEVER assert historical availability.

    A historical page is not a vintage of what was known before an event.
    Consequently calendar fields do not enter the primary feature dataset.
    """
    results = []
    day = start - dt.timedelta(days=(start.weekday() + 1) % 7)
    months = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
    while day <= end:
        week = f"{months[day.month-1]}{day.day}.{day.year}"
        try:
            html = archive.get("https://www.forexfactory.com/calendar", {"week": week}, as_json=False)
            # Structural marker only: coverage and timestamps still need manual review.
            marker = 'calendar__event-title' in html or 'calendar__event' in html
            results.append({"week": week, "status": "html_with_event_markers" if marker else "unverified_html",
                            "bytes": len(html.encode()), "point_in_time_verified": False})
        except (requests.RequestException, ValueError, RuntimeError, FileNotFoundError) as exc:
            results.append({"week": week, "status": "failed", "error": str(exc),
                            "point_in_time_verified": False})
        day += dt.timedelta(days=7)
        if not archive.offline:
            time.sleep(1)
    return results
