"""Synthetic fixtures test cutoffs/errors; real source verification runs separately."""

import copy
import hashlib
import io
import json
from pathlib import Path
import zipfile

import pytest

from data_sources.historical_data import Archive, midnight
from data_sources.historical_derivatives import checked_csv, funding_point, latest_before, ratio_point, verify_funding_api
from scripts.enrich_historical_dataset import enrich_snapshots
from scripts.evaluate_direction import adapter, require_full_live


def test_publisher_checksum_required_before_csv_parse():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("sample.csv", "x,y\n1,2\n")
    body = buffer.getvalue()
    class Fake:
        checksum = hashlib.sha256(body).hexdigest()
        def get(self, url, **kwargs):
            return self.checksum+"  sample.zip\n" if url.endswith("CHECKSUM") else body
    fake = Fake()
    assert checked_csv(fake, "https://example.test/sample.zip") == [{"x": "1", "y": "2"}]
    fake.checksum = "0"*64
    with pytest.raises(ValueError, match="checksum mismatch"):
        checked_csv(fake, "https://example.test/sample.zip")


def test_binary_archive_roundtrip_and_tampering(tmp_path):
    archive = Archive(tmp_path)
    class Response:
        content = b"PK\x00\xff"
        status_code = 200
        url = "https://example.test/archive.zip"
    archive.session.get = lambda *a, **k: Response()
    assert archive.get(Response.url, as_bytes=True) == Response.content
    assert Archive(tmp_path, offline=True).get(Response.url, as_bytes=True) == Response.content
    next(tmp_path.glob("*.body")).write_bytes(b"changed")
    with pytest.raises(ValueError, match="checksum"):
        Archive(tmp_path, offline=True).get(Response.url, as_bytes=True)


def test_funding_milliseconds_and_negative_values_preserved():
    row = {"calc_time": "1640995200006", "funding_interval_hours": "8", "last_funding_rate": "-0.00003102"}
    point = funding_point(row, "https://example.test")
    assert point["observed_at"] == "2022-01-01T00:00:00.006000+00:00"
    assert point["value"] == -0.00003102
    assert latest_before([point], midnight("2022-01-01"), 12) is None


def test_blank_global_ratio_is_not_top_trader_ratio():
    row = {"symbol": "BTCUSDT", "count_long_short_ratio": "",
           "count_toptrader_long_short_ratio": "2", "create_time": "2022-01-01 00:00:00"}
    assert ratio_point(row, "source") is None
    row["count_long_short_ratio"] = "0.9"
    point = ratio_point(row, "source")
    assert point["value"] == 0.9
    assert point["available_at"] == "2022-01-01T00:05:00+00:00"


@pytest.mark.parametrize("value", ["nan", "inf", "-1", "0"])
def test_invalid_global_ratios_rejected(value):
    with pytest.raises(ValueError):
        ratio_point({"symbol": "BTCUSDT", "count_long_short_ratio": value,
                     "create_time": "2022-01-01 00:00:00"}, "source")


def test_latest_observation_does_not_backfill_from_future_or_stale_data():
    old = {"observed_at": "2021-12-31T16:00:00+00:00", "available_at": "2021-12-31T16:00:00+00:00", "value": .0001}
    boundary = {"observed_at": "2022-01-01T00:00:00+00:00", "available_at": "2022-01-01T00:00:00+00:00", "value": 999}
    assert latest_before([old, boundary], midnight("2022-01-01"), 12)["value"] == .0001
    assert latest_before([old], midnight("2022-01-02"), 12) is None


def test_funding_crosscheck_detects_wrong_value():
    point = {"observed_at": "2021-12-31T16:00:00+00:00", "value": .0001}
    class API:
        calls = 0
        def get(self, *args, **kwargs):
            self.calls += 1
            return [{"symbol": "BTCUSDT", "fundingTime": 1640966400000, "fundingRate": "0.002"}] if self.calls == 1 else []
    result = verify_funding_api(API(), [point], midnight("2022-01-01"), midnight("2022-01-02"))
    assert not result["matched"]
    assert result["mismatch_timestamps"] == [point["observed_at"]]


@pytest.fixture
def base_snapshot():
    return json.loads(Path("data/datasets/pilot_2022_01/snapshots.jsonl").read_text().splitlines()[0])


def test_enrichment_does_not_mutate_base_and_adapter_consumes_real_values(base_snapshot):
    before = copy.deepcopy(base_snapshot)
    funding = {"observed_at": "2021-12-31T16:00:00+00:00", "available_at": "2021-12-31T16:00:00+00:00",
               "value": -.0001, "source_url": "test fixture", "semantics": "last settled funding"}
    snap = enrich_snapshots([base_snapshot], {"funding": [funding], "long_short": []})[0]
    assert before == base_snapshot
    _, market, sentiment = adapter(snap)
    assert market["funding_rate"] == -.0001
    assert market["long_short_ratio"] is None
    assert "last settled funding" in market["summary_text"]
    assert "funding rate and long/short ratio unavailable" not in market["summary_text"]
    assert "ForexFactory calendar and news unavailable" in sentiment["summary_text"]
    assert not snap["eligible_full_live"]
    for field in ("return_24h", "future_price", "actual", "forecast"):
        assert field not in market["summary_text"]


@pytest.mark.parametrize("stamp", ["2022-01-01T00:00:00+00:00", "2022-01-02T00:00:00+00:00", "2021-12-29T00:00:00+00:00"])
def test_adapter_rejects_future_boundary_and_stale_injected_values(base_snapshot, stamp):
    base_snapshot["historical_extras"] = {"funding_rate": {"value": .1, "observed_at": stamp, "available_at": stamp}}
    with pytest.raises(ValueError, match="historical funding_rate"):
        adapter(base_snapshot)


def test_full_live_gate_rejects_partial_dataset(base_snapshot):
    with pytest.raises(ValueError, match="not full-live"):
        require_full_live([base_snapshot])
    snap = enrich_snapshots([base_snapshot], {"funding": [], "long_short": []})[0]
    with pytest.raises(ValueError, match="not full-live"):
        require_full_live([snap])
