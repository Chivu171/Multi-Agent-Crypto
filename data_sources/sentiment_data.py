# data_sources/sentiment_data.py
"""Fetch real crypto sentiment data: the Fear & Greed index (Alternative.me,
free, no key) and upcoming macro calendar events (ForexFactory's public JSON
feed — no official API, but this feed is widely used and freely accessible).

Same cache-first / stale-fallback pattern as data_sources/market_data.py.
"""

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

FEAR_GREED_URL = "https://api.alternative.me/fng/"
FOREXFACTORY_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

CACHE_PATH = Path("outputs/cache/sentiment_data.json")
CACHE_TTL_SECONDS = 3600  # 1 hour — F&G updates ~daily, calendar is weekly
REQUEST_TIMEOUT = 10

RELEVANT_IMPACTS = {"High", "Medium"}


def _fetch_fear_greed() -> Dict[str, Any]:
    resp = requests.get(FEAR_GREED_URL, params={"limit": 1}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    entry = resp.json()["data"][0]
    return {"value": int(entry["value"]), "classification": entry["value_classification"]}


def _fetch_upcoming_events(limit: int = 10) -> List[Dict[str, Any]]:
    """Return upcoming High/Medium-impact macro events from ForexFactory's
    this-week calendar feed, soonest first."""
    resp = requests.get(FOREXFACTORY_CALENDAR_URL, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    raw_events = resp.json()

    now = datetime.datetime.now(datetime.timezone.utc)
    upcoming = []
    for event in raw_events:
        if event.get("impact") not in RELEVANT_IMPACTS:
            continue
        try:
            event_time = datetime.datetime.fromisoformat(event["date"])
        except (KeyError, ValueError):
            continue
        if event_time < now:
            continue
        upcoming.append({
            "title": event.get("title", ""),
            "country": event.get("country", ""),
            "impact": event.get("impact", ""),
            "date": event["date"],
            "forecast": event.get("forecast", ""),
            "previous": event.get("previous", ""),
        })

    upcoming.sort(key=lambda e: e["date"])
    return upcoming[:limit]


def _load_cache() -> Optional[Dict[str, Any]]:
    if not CACHE_PATH.exists():
        return None
    with open(CACHE_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_cache(data: Dict[str, Any]) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _is_fresh(cached: Dict[str, Any], ttl_seconds: int) -> bool:
    fetched_at = datetime.datetime.fromisoformat(cached["fetched_at"])
    age = (datetime.datetime.now(datetime.timezone.utc) - fetched_at).total_seconds()
    return age < ttl_seconds


def _build_summary_text(data: Dict[str, Any]) -> str:
    lines = [
        f"Sentiment snapshot (fetched {data['fetched_at']}):",
        f"- Fear & Greed Index: {data['fear_greed']['value']}/100 ({data['fear_greed']['classification']})",
        "- Upcoming macro events (High/Medium impact):",
    ]
    if data["upcoming_events"]:
        for e in data["upcoming_events"]:
            lines.append(
                f"  * [{e['impact']}] {e['country']} — {e['title']} on {e['date']} "
                f"(forecast: {e['forecast'] or 'n/a'}, previous: {e['previous'] or 'n/a'})"
            )
    else:
        lines.append("  * None in the current week's feed.")
    return "\n".join(lines) + "\n"


def fetch_sentiment_data(cache_ttl_seconds: int = CACHE_TTL_SECONDS) -> Dict[str, Any]:
    """Return a fresh (or cached) sentiment snapshot: Fear & Greed index +
    upcoming High/Medium-impact macro calendar events.

    Same fallback behavior as fetch_market_data: uses stale cache on live
    fetch failure, only raises if there is no cache at all.
    """
    cached = _load_cache()
    if cached and _is_fresh(cached, cache_ttl_seconds):
        return cached

    try:
        data = {
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "fear_greed": _fetch_fear_greed(),
            "upcoming_events": _fetch_upcoming_events(),
        }
        data["summary_text"] = _build_summary_text(data)
        _save_cache(data)
        return data
    except Exception as e:
        if cached:
            print(f"[sentiment_data] Live fetch failed ({e}), using stale cache from {cached['fetched_at']}")
            return cached
        raise
