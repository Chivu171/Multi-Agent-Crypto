import copy
import datetime as dt
import json

import pytest

from data_sources.historical_data import Archive, CHARTS, DAY, fetch_market, midnight, parse_forex_calendar
from utils.historical_dataset import asof, build, daily_series, market_index, split_for


@pytest.fixture
def historical_source():
    start = midnight("2021-09-01")
    market, points, fear = [], [], []
    for index in range(160):
        t = start + index * DAY
        price = 100 + index
        market.append([int(t.timestamp()*1000), price, price+2, price-2, price+1,
                       1000+index, int((t+DAY).timestamp()*1000)-1])
        points.append({"x": int(t.timestamp()), "y": 1000+index})
        fear.append({"timestamp": str(int(t.timestamp())), "value": "40"})
    return {"market": market, "onchain": {chart: copy.deepcopy(points) for chart in CHARTS}, "fear_greed": fear}


def test_target_candle_never_changes_features_or_snapshot(historical_source):
    t = midnight("2022-01-01")
    before = build(historical_source, t, t)
    changed = copy.deepcopy(historical_source)
    for candle in changed["market"]:
        if candle[0] >= int(t.timestamp()*1000):
            candle[1:5] = [1000, 1100, 900, 1000]
    after = build(changed, t, t)
    assert before["features"] == after["features"]
    assert before["snapshots"] == after["snapshots"]
    assert before["labels"] != after["labels"]


def test_future_source_values_do_not_leak(historical_source):
    t = midnight("2022-01-01")
    before = build(historical_source, t, t)
    for chart in CHARTS:
        for p in historical_source["onchain"][chart]:
            if p["x"] > (t-2*DAY).timestamp():
                p["y"] = 999999
    for p in historical_source["fear_greed"]:
        if int(p["timestamp"]) > (t-DAY).timestamp():
            p["value"] = "100"
    after = build(historical_source, t, t)
    assert before["features"] == after["features"]
    assert before["snapshots"] == after["snapshots"]


def test_snapshot_availability_and_closed_window(historical_source):
    t = midnight("2022-01-01")
    dataset = build(historical_source, t, t)
    snap = dataset["snapshots"][0]
    assert len(snap["market_window"]["candles"]) == 90
    for point in snap["evidence"].values():
        assert dt.datetime.fromisoformat(point["available_at"]) <= t
    for candle in snap["market_window"]["candles"]:
        assert dt.datetime.fromisoformat(candle["open_time"]) + DAY <= t
    serialized = json.dumps(snap)
    for field in ("future_price", "return_24h", "target_end", '"label"'):
        assert field not in serialized


@pytest.mark.parametrize("multiplier,label", [(1.01, "NEUTRAL"), (0.99, "NEUTRAL"), (1.02, "BUY"), (0.98, "SELL")])
def test_exact_label_thresholds(historical_source, multiplier, label):
    t = midnight("2022-01-01")
    price = market_index(historical_source["market"])[t-DAY]["close"]
    for candle in historical_source["market"]:
        if candle[0] == int(t.timestamp()*1000):
            candle[4] = price*multiplier
            candle[2] = max(candle[1], candle[4])+1
            candle[3] = min(candle[1], candle[4])-1
    result = build(historical_source, t, t)["labels"][0]
    assert result["label"] == label
    assert result["return_24h"] == pytest.approx(multiplier-1)


def test_missing_target_drops_sample(historical_source):
    t = midnight("2022-01-01")
    historical_source["market"] = [r for r in historical_source["market"] if r[0] != int(t.timestamp()*1000)]
    result = build(historical_source, t, t)
    assert result["features"] == []
    assert not result["audit"][0]["included"]


def test_missing_day_in_window_drops_sample(historical_source):
    t = midnight("2022-01-01")
    historical_source["market"] = [r for r in historical_source["market"] if r[0] != int((t-20*DAY).timestamp()*1000)]
    assert build(historical_source, t, t)["features"] == []


def test_stale_series_is_missing_without_future_backfill():
    points = daily_series([{"x": midnight("2022-01-01").timestamp(), "y": 4},
                           {"x": midnight("2022-02-01").timestamp(), "y": 8}], "hash-rate", 2)
    assert asof(points, midnight("2022-01-02")) is None
    assert asof(points, midnight("2022-01-06"))["value"] == 4
    assert asof(points, midnight("2022-01-07")) is None


def test_source_missing_preserves_market_sample_but_excludes_core(historical_source):
    t = midnight("2022-01-01")
    historical_source["onchain"]["hash-rate"] = []
    result = build(historical_source, t, t)
    assert len(result["features"]) == 1
    assert result["features"][0]["hash_rate_missing"] == 1
    assert not result["splits"][0]["eligible_core"]
    assert not result["splits"][0]["eligible_full"]


def test_split_purges_boundary_labels():
    assert split_for(midnight("2024-06-29")) == ("train", True)
    assert split_for(midnight("2024-06-30")) == ("train", False)
    assert split_for(midnight("2024-12-31")) == ("validation", False)
    assert split_for(midnight("2025-01-01")) == ("test", True)


def test_duplicate_market_days_rejected(historical_source):
    historical_source["market"].append(historical_source["market"][0])
    with pytest.raises(ValueError, match="Duplicate"):
        market_index(historical_source["market"])


def test_archive_offline_and_tamper_detection(tmp_path):
    with pytest.raises(FileNotFoundError):
        Archive(tmp_path, offline=True).get("https://example.invalid")
    archive = Archive(tmp_path)
    class Response:
        status_code = 200
        content = b'{"value": 1}'
        url = "https://example.invalid/"
    archive.session.get = lambda *a, **kw: Response()
    assert archive.get("https://example.invalid") == {"value": 1}
    assert Archive(tmp_path, offline=True).get("https://example.invalid") == {"value": 1}
    next(tmp_path.glob("*.body")).write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        Archive(tmp_path, offline=True).get("https://example.invalid")


def test_market_pagination_uses_next_open_time(historical_source):
    candles = historical_source["market"][:3]
    calls = []
    class FakeArchive:
        def get(self, url, params):
            calls.append(params)
            return candles[:2] if len(calls) == 1 else candles[2:]
    result = fetch_market(FakeArchive(), midnight("2021-09-01"), midnight("2021-09-04"))
    assert result == candles
    assert calls[1]["startTime"] == candles[2][0]


def test_forex_embedded_json_uses_epoch_and_is_never_point_in_time():
    days = [{"events": [{"id": 1, "name": "CPI", "dateline": 1641308400,
                         "currency": "USD", "impactName": "high", "actual": "7%",
                         "forecast": "6%", "timeLabel": "10:00pm", "timeMasked": False}]}]
    html = 'window.calendarComponentStates[1] = {\ndays: ' + json.dumps(days) + ', other: true};'
    event = parse_forex_calendar(html)[0]
    assert event["event_time"] == "2022-01-04T15:00:00+00:00"
    assert event["available_at"] is None
    assert not event["use_in_primary_features"]
    assert not event["point_in_time_verified"]


def test_forex_challenge_page_not_treated_as_empty_calendar():
    with pytest.raises(ValueError, match="not found"):
        parse_forex_calendar("<html>Just a moment...</html>")
