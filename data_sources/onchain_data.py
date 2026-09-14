# data_sources/onchain_data.py
"""Fetch real on-chain network data from blockchain.info's free Charts API
(no key needed). This is a lower-fidelity substitute for paid on-chain
providers (Glassnode/CryptoQuant) — it does NOT include MVRV, SOPR, or true
exchange whale-flow, which are paywalled. It gives network-health proxies
(hash rate, miner revenue, transaction activity) instead.

Same cache-first / stale-fallback pattern as market_data.py / sentiment_data.py.
"""

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

from utils.retry import http_retry

BLOCKCHAIN_INFO_CHARTS_URL = "https://api.blockchain.info/charts/{chart}"

# chart slug -> (result key, human label, unit)
CHARTS = {
    "hash-rate": ("hash_rate", "Network hash rate", "TH/s"),
    "miners-revenue": ("miners_revenue_usd", "Miner revenue", "USD/day"),
    "n-transactions": ("n_transactions", "Confirmed transactions", "tx/day"),
    "estimated-transaction-volume-usd": ("tx_volume_usd", "Estimated transaction value", "USD/day"),
}

CACHE_PATH = Path("outputs/cache/onchain_data.json")
CACHE_TTL_SECONDS = 3 * 3600  # 3 hours — these charts update ~daily
REQUEST_TIMEOUT = 10


@http_retry
def _fetch_chart(chart: str, timespan: str = "10days") -> List[Dict[str, float]]:
    resp = requests.get(
        BLOCKCHAIN_INFO_CHARTS_URL.format(chart=chart),
        params={"timespan": timespan, "format": "json"},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()["values"]


def _latest_and_change(values: List[Dict[str, float]]) -> Dict[str, float]:
    """Return the latest value and its % change vs. the previous data point."""
    if not values:
        raise ValueError("Empty chart data from blockchain.info")
    latest = values[-1]["y"]
    if len(values) >= 2 and values[-2]["y"] != 0:
        previous = values[-2]["y"]
        pct_change = (latest - previous) / previous * 100
    else:
        pct_change = 0.0
    return {"value": latest, "pct_change_1d": pct_change}


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
        f"On-chain network snapshot (fetched {data['fetched_at']}):",
        "(free-tier proxies — no MVRV/SOPR/whale-flow; those require a paid provider)",
    ]
    for chart, (key, label, unit) in CHARTS.items():
        metric = data["metrics"][key]
        arrow = "up" if metric["pct_change_1d"] >= 0 else "down"
        lines.append(
            f"- {label}: {metric['value']:,.2f} {unit} ({arrow} {abs(metric['pct_change_1d']):.1f}% vs prior day)"
        )
    return "\n".join(lines) + "\n"


def fetch_onchain_data(cache_ttl_seconds: int = CACHE_TTL_SECONDS) -> Dict[str, Any]:
    """Return a fresh (or cached) on-chain network snapshot from blockchain.info.

    Same fallback behavior as the other data_sources fetchers: uses stale
    cache on live fetch failure, only raises if there is no cache at all.
    """
    cached = _load_cache()
    if cached and _is_fresh(cached, cache_ttl_seconds):
        return cached

    try:
        metrics = {}
        for chart, (key, _label, _unit) in CHARTS.items():
            values = _fetch_chart(chart)
            metrics[key] = _latest_and_change(values)

        data = {
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "metrics": metrics,
        }
        data["summary_text"] = _build_summary_text(data)
        _save_cache(data)
        return data
    except Exception as e:
        if cached:
            print(f"[onchain_data] Live fetch failed ({e}), using stale cache from {cached['fetched_at']}")
            return cached
        raise
