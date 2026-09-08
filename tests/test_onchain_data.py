import json
from unittest.mock import MagicMock, patch

import pytest

from data_sources import onchain_data


def _chart_response(values):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"values": values}
    return response


def _fake_get(url, params=None, timeout=None):
    # every chart gets a simple rising two-point series: 100 -> 110 (+10%)
    if url.endswith("/hash-rate"):
        return _chart_response([{"x": 1, "y": 100.0}, {"x": 2, "y": 110.0}])
    if url.endswith("/miners-revenue"):
        return _chart_response([{"x": 1, "y": 200.0}, {"x": 2, "y": 180.0}])  # -10%
    if url.endswith("/n-transactions"):
        return _chart_response([{"x": 1, "y": 500.0}, {"x": 2, "y": 500.0}])  # 0%
    if url.endswith("/estimated-transaction-volume-usd"):
        return _chart_response([{"x": 1, "y": 1000.0}, {"x": 2, "y": 1100.0}])
    raise AssertionError(f"Unexpected URL {url}")


def test_latest_and_change_computes_percentage():
    result = onchain_data._latest_and_change([{"x": 1, "y": 100.0}, {"x": 2, "y": 110.0}])
    assert result == {"value": 110.0, "pct_change_1d": pytest.approx(10.0)}


def test_latest_and_change_single_point_has_zero_change():
    result = onchain_data._latest_and_change([{"x": 1, "y": 100.0}])
    assert result == {"value": 100.0, "pct_change_1d": 0.0}


def test_latest_and_change_raises_on_empty_data():
    with pytest.raises(ValueError):
        onchain_data._latest_and_change([])


@patch("data_sources.onchain_data.requests.get", side_effect=_fake_get)
def test_fetch_onchain_data_builds_all_four_metrics(mock_get, tmp_path, monkeypatch):
    monkeypatch.setattr(onchain_data, "CACHE_PATH", tmp_path / "onchain_data.json")

    data = onchain_data.fetch_onchain_data()

    assert set(data["metrics"]) == {"hash_rate", "miners_revenue_usd", "n_transactions", "tx_volume_usd"}
    assert data["metrics"]["hash_rate"]["value"] == 110.0
    assert data["metrics"]["miners_revenue_usd"]["pct_change_1d"] == pytest.approx(-10.0)
    assert "On-chain network snapshot" in data["summary_text"]
    assert "MVRV" in data["summary_text"]  # honesty disclaimer about missing paid metrics


@patch("data_sources.onchain_data.requests.get", side_effect=_fake_get)
def test_fetch_onchain_data_uses_fresh_cache_without_calling_api(mock_get, tmp_path, monkeypatch):
    monkeypatch.setattr(onchain_data, "CACHE_PATH", tmp_path / "onchain_data.json")

    onchain_data.fetch_onchain_data()
    mock_get.reset_mock()

    result = onchain_data.fetch_onchain_data()

    mock_get.assert_not_called()
    assert "metrics" in result


def test_fetch_onchain_data_falls_back_to_stale_cache_on_failure(tmp_path, monkeypatch):
    cache_file = tmp_path / "onchain_data.json"
    stale = {
        "fetched_at": "2020-01-01T00:00:00+00:00",
        "metrics": {
            "hash_rate": {"value": 1.0, "pct_change_1d": 0.0},
            "miners_revenue_usd": {"value": 1.0, "pct_change_1d": 0.0},
            "n_transactions": {"value": 1.0, "pct_change_1d": 0.0},
            "tx_volume_usd": {"value": 1.0, "pct_change_1d": 0.0},
        },
        "summary_text": "old",
    }
    cache_file.write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setattr(onchain_data, "CACHE_PATH", cache_file)

    with patch("data_sources.onchain_data.requests.get", side_effect=RuntimeError("network down")):
        result = onchain_data.fetch_onchain_data(cache_ttl_seconds=1)

    assert result == stale


def test_fetch_onchain_data_raises_when_no_cache_and_api_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(onchain_data, "CACHE_PATH", tmp_path / "onchain_data.json")

    with patch("data_sources.onchain_data.requests.get", side_effect=RuntimeError("network down")):
        with pytest.raises(RuntimeError):
            onchain_data.fetch_onchain_data()
