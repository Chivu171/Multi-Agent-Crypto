import json
from unittest.mock import MagicMock, patch

import pytest

from data_sources import sentiment_data


def _fg_response(value="69", classification="Greed"):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"data": [{"value": value, "classification": classification, "value_classification": classification}]}
    return response


def _calendar_response(events):
    response = MagicMock()
    response.raise_for_status.return_value = None
    response.json.return_value = events
    return response


def _event(title, impact, days_from_now, country="USD"):
    import datetime
    dt = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days_from_now)
    return {
        "title": title,
        "country": country,
        "impact": impact,
        "date": dt.isoformat(),
        "forecast": "1.0%",
        "previous": "0.9%",
    }


def _fake_get(url, params=None, timeout=None):
    if "alternative.me" in url:
        return _fg_response()
    if "faireconomy" in url:
        events = [
            _event("Fed Interest Rate Decision", "High", days_from_now=1),
            _event("Low impact noise event", "Low", days_from_now=1),
            _event("Already happened", "High", days_from_now=-1),
            _event("Medium impact CPI", "Medium", days_from_now=2),
        ]
        return _calendar_response(events)
    raise AssertionError(f"Unexpected URL {url}")


@patch("data_sources.sentiment_data.requests.get", side_effect=_fake_get)
def test_fetch_sentiment_data_builds_snapshot(mock_get, tmp_path, monkeypatch):
    monkeypatch.setattr(sentiment_data, "CACHE_PATH", tmp_path / "sentiment_data.json")

    data = sentiment_data.fetch_sentiment_data()

    assert data["fear_greed"] == {"value": 69, "classification": "Greed"}
    titles = [e["title"] for e in data["upcoming_events"]]
    assert "Fed Interest Rate Decision" in titles
    assert "Medium impact CPI" in titles
    assert "Low impact noise event" not in titles  # filtered: Low impact
    assert "Already happened" not in titles  # filtered: in the past
    assert "Fear & Greed Index: 69/100" in data["summary_text"]


@patch("data_sources.sentiment_data.requests.get", side_effect=_fake_get)
def test_fetch_sentiment_data_events_sorted_soonest_first(mock_get, tmp_path, monkeypatch):
    monkeypatch.setattr(sentiment_data, "CACHE_PATH", tmp_path / "sentiment_data.json")

    data = sentiment_data.fetch_sentiment_data()

    dates = [e["date"] for e in data["upcoming_events"]]
    assert dates == sorted(dates)


@patch("data_sources.sentiment_data.requests.get", side_effect=_fake_get)
def test_fetch_sentiment_data_uses_fresh_cache_without_calling_api(mock_get, tmp_path, monkeypatch):
    monkeypatch.setattr(sentiment_data, "CACHE_PATH", tmp_path / "sentiment_data.json")

    sentiment_data.fetch_sentiment_data()
    mock_get.reset_mock()

    result = sentiment_data.fetch_sentiment_data()

    mock_get.assert_not_called()
    assert "fear_greed" in result


def test_fetch_sentiment_data_falls_back_to_stale_cache_on_failure(tmp_path, monkeypatch):
    cache_file = tmp_path / "sentiment_data.json"
    stale = {
        "fetched_at": "2020-01-01T00:00:00+00:00",
        "fear_greed": {"value": 50, "classification": "Neutral"},
        "upcoming_events": [],
        "summary_text": "old",
    }
    cache_file.write_text(json.dumps(stale), encoding="utf-8")
    monkeypatch.setattr(sentiment_data, "CACHE_PATH", cache_file)

    with patch("data_sources.sentiment_data.requests.get", side_effect=RuntimeError("network down")):
        result = sentiment_data.fetch_sentiment_data(cache_ttl_seconds=1)

    assert result == stale


def test_fetch_sentiment_data_raises_when_no_cache_and_api_fails(tmp_path, monkeypatch):
    monkeypatch.setattr(sentiment_data, "CACHE_PATH", tmp_path / "sentiment_data.json")

    with patch("data_sources.sentiment_data.requests.get", side_effect=RuntimeError("network down")):
        with pytest.raises(RuntimeError):
            sentiment_data.fetch_sentiment_data()


def test_fetch_sentiment_data_no_upcoming_events_message():
    text = sentiment_data._build_summary_text({
        "fetched_at": "now",
        "fear_greed": {"value": 40, "classification": "Fear"},
        "upcoming_events": [],
    })
    assert "None in the current week's feed." in text
