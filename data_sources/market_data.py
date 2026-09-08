# data_sources/market_data.py
"""Fetch real BTC market data from Binance's public API (no key needed).

Computes EMA20/EMA50/RSI14 from spot klines, plus futures funding rate and
long/short account ratio. Results are cached to disk so repeated calls within
CACHE_TTL_SECONDS don't hit Binance's rate limits. If a live fetch fails, the
most recent cache is used as a fallback (only raises if there's no cache at all).
"""

import datetime
import json
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import requests

BINANCE_SPOT_KLINES_URL = "https://api.binance.com/api/v3/klines"
BINANCE_FUTURES_PREMIUM_URL = "https://fapi.binance.com/fapi/v1/premiumIndex"
BINANCE_FUTURES_RATIO_URL = "https://fapi.binance.com/futures/data/globalLongShortAccountRatio"

CACHE_PATH = Path("outputs/cache/market_data.json")
CACHE_TTL_SECONDS = 900  # 15 minutes
REQUEST_TIMEOUT = 10


def _ema(values: np.ndarray, period: int) -> float:
    """Standard EMA: seed with the SMA of the first `period` points, then
    apply the exponential smoothing formula (alpha = 2/(period+1)) forward."""
    if len(values) < period:
        raise ValueError(f"Need at least {period} data points, got {len(values)}")
    alpha = 2.0 / (period + 1)
    ema = float(np.mean(values[:period]))
    for price in values[period:]:
        ema = alpha * float(price) + (1 - alpha) * ema
    return ema


def _rsi(closes: np.ndarray, period: int = 14) -> float:
    """RSI via simple moving average of gains/losses over the last `period`
    price changes (Cutler's RSI variant — deterministic, no need for full
    price history like Wilder's smoothed version)."""
    if len(closes) < period + 1:
        raise ValueError(f"Need at least {period + 1} data points, got {len(closes)}")
    deltas = np.diff(closes)
    gains = np.clip(deltas, a_min=0, a_max=None)
    losses = np.clip(-deltas, a_min=0, a_max=None)
    avg_gain = float(np.mean(gains[-period:]))
    avg_loss = float(np.mean(losses[-period:]))
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _fetch_klines(symbol: str, interval: str = "1d", limit: int = 60) -> np.ndarray:
    resp = requests.get(
        BINANCE_SPOT_KLINES_URL,
        params={"symbol": symbol, "interval": interval, "limit": limit},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    raw = resp.json()
    return np.array([float(candle[4]) for candle in raw])  # index 4 = close price


def _fetch_funding_rate(symbol: str) -> float:
    resp = requests.get(BINANCE_FUTURES_PREMIUM_URL, params={"symbol": symbol}, timeout=REQUEST_TIMEOUT)
    resp.raise_for_status()
    return float(resp.json()["lastFundingRate"])


def _fetch_long_short_ratio(symbol: str) -> float:
    resp = requests.get(
        BINANCE_FUTURES_RATIO_URL,
        params={"symbol": symbol, "period": "1d", "limit": 1},
        timeout=REQUEST_TIMEOUT,
    )
    resp.raise_for_status()
    raw = resp.json()
    return float(raw[0]["longShortRatio"])


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
    position = "above" if data["price"] > data["ema20"] else "below"
    return (
        f"BTC/USDT market snapshot (fetched {data['fetched_at']}):\n"
        f"- Price: ${data['price']:,.2f}\n"
        f"- EMA20: ${data['ema20']:,.2f} | EMA50: ${data['ema50']:,.2f} (price is {position} EMA20)\n"
        f"- RSI14: {data['rsi14']:.1f}\n"
        f"- Funding rate: {data['funding_rate']:.4%}\n"
        f"- Long/Short account ratio: {data['long_short_ratio']:.2f}\n"
    )


def fetch_market_data(symbol: str = "BTCUSDT", cache_ttl_seconds: int = CACHE_TTL_SECONDS) -> Dict[str, Any]:
    """Return a fresh (or cached) BTC market data snapshot.

    Uses the cache if it's still within `cache_ttl_seconds`. On a live fetch,
    always refreshes the cache. If the live fetch fails (network error, rate
    limit, Binance down), falls back to the most recent cache regardless of
    age — only raises if there is no cache at all.
    """
    cached = _load_cache()
    if cached and _is_fresh(cached, cache_ttl_seconds):
        return cached

    try:
        closes = _fetch_klines(symbol)
        data = {
            "symbol": symbol,
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "price": float(closes[-1]),
            "ema20": _ema(closes, 20),
            "ema50": _ema(closes, 50),
            "rsi14": _rsi(closes, 14),
            "funding_rate": _fetch_funding_rate(symbol),
            "long_short_ratio": _fetch_long_short_ratio(symbol),
        }
        data["summary_text"] = _build_summary_text(data)
        _save_cache(data)
        return data
    except Exception as e:
        if cached:
            print(f"[market_data] Live fetch failed ({e}), using stale cache from {cached['fetched_at']}")
            return cached
        raise
