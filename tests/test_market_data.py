import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from data_sources import market_data


def test_ema_seeds_with_sma_then_smooths():
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    # seed = mean(1,2,3) = 2.0; alpha = 2/(3+1) = 0.5
    # step1: 0.5*4 + 0.5*2.0 = 3.0
    # step2: 0.5*5 + 0.5*3.0 = 4.0
    assert market_data._ema(values, period=3) == pytest.approx(4.0)


def test_ema_raises_if_not_enough_data():
    with pytest.raises(ValueError):
        market_data._ema(np.array([1.0, 2.0]), period=5)


def test_rsi_all_gains_is_100():
    closes = np.array([float(i) for i in range(1, 16)])  # strictly increasing
    assert market_data._rsi(closes, period=14) == 100.0


def test_rsi_all_losses_is_0():
    closes = np.array([float(i) for i in range(15, 0, -1)])  # strictly decreasing
    assert market_data._rsi(closes, period=14) == 0.0


def test_rsi_raises_if_not_enough_data():
    with pytest.raises(ValueError):
        market_data._rsi(np.array([1.0, 2.0]), period=14)


def _make_klines(closes):
    return [[0, "0", "0", "0", str(c), "0", 0, "0", 0, "0", "0", "0"] for c in closes]


def _fake_get(url, params=None, timeout=None):
    response = MagicMock()
    response.raise_for_status.return_value = None
    if "klines" in url:
        response.json.return_value = _make_klines([100 + i for i in range(60)])
    elif "premiumIndex" in url:
        response.json.return_value = {"lastFundingRate": "0.0001"}
    elif "globalLongShortAccountRatio" in url:
        response.json.return_value = [{"longShortRatio": "1.5"}]
    else:
        raise AssertionError(f"Unexpected URL {url}")
    return response


@patch("data_sources.market_data.requests.get", side_effect=_fake_get)
def test_fetch_market_data_live_fetch_builds_full_snapshot(mock_get, tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "CACHE_PATH", tmp_path / "market_data.json")

    data = market_data.fetch_market_data("BTCUSDT")

    assert data["symbol"] == "BTCUSDT"
    assert data["price"] == 159.0
    assert data["funding_rate"] == 0.0001
    assert data["long_short_ratio"] == 1.5
    assert "summary_text" in data and "BTC/USDT" in data["summary_text"]
    assert (tmp_path / "market_data.json").exists()


@patch("data_sources.market_data.requests.get", side_effect=_fake_get)
def test_fetch_market_data_uses_fresh_cache_without_calling_api(mock_get, tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "CACHE_PATH", tmp_path / "market_data.json")

    market_data.fetch_market_data("BTCUSDT")  # populate cache
    mock_get.reset_mock()

    result = market_data.fetch_market_data("BTCUSDT")

    mock_get.assert_not_called()
    assert result["symbol"] == "BTCUSDT"


def test_fetch_market_data_falls_back_to_stale_cache_on_failure(tmp_path, monkeypatch):
    cache_file = tmp_path / "market_data.json"
    stale = {
        "symbol": "BTCUSDT",
        "fetched_at": "2020-01-01T00:00:00+00:00",
        "price": 1.0,
        "ema20": 1.0,
        "ema50": 1.0,
        "rsi14": 50.0,
        "funding_rate": 0.0,
        "long_short_ratio": 1.0,
        "summary_text": "old",
    }
    cache_file.write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setattr(market_data, "CACHE_PATH", cache_file)

    with patch("data_sources.market_data.requests.get", side_effect=RuntimeError("network down")):
        result = market_data.fetch_market_data("BTCUSDT", cache_ttl_seconds=1)

    assert result == stale


def test_fetch_market_data_raises_when_no_cache_and_api_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(market_data, "CACHE_PATH", tmp_path / "market_data.json")

    with patch("data_sources.market_data.requests.get", side_effect=RuntimeError("network down")):
        with pytest.raises(RuntimeError):
            market_data.fetch_market_data("BTCUSDT")
