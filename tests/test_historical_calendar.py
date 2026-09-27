"""Synthetic release values must never enter schedule-only model inputs."""

import copy
import datetime as dt
import json
from pathlib import Path

import pytest

from data_sources.historical_data import midnight
from scripts.enrich_historical_dataset import enrich_snapshots
from scripts.evaluate_direction import adapter
from utils.historical_calendar import EVENT_FIELDS, schedule_only, validated_schedule


@pytest.fixture
def events():
    return [{"event_id": "1", "title": "CPI", "currency": "USD", "impact": "high",
             "event_time": "2022-01-03T13:30:00+00:00", "time_masked": False,
             "source_week": "jan2.2022", "raw_file": "fixture.body",
             "actual": "SECRET_ACTUAL_7.9", "forecast": "SECRET_FORECAST_7.8",
             "previous": "SECRET_PREVIOUS_7.7", "revision": "SECRET_REVISION"}]


def test_only_metadata_survives_and_release_changes_do_not_change_input(events):
    before = schedule_only(events, midnight("2022-01-03"))
    assert set(before["events"][0]) == EVENT_FIELDS
    assert "SECRET" not in json.dumps(before)
    for field in ("actual", "forecast", "previous", "revision"):
        events[0][field] = "totally different value"
    assert before == schedule_only(events, midnight("2022-01-03"))
    assert before["publication_time"] is None
    assert not before["point_in_time_verified"]


def test_no_events_and_no_source_are_distinct(events):
    assert schedule_only([], midnight("2022-01-03")) is None
    after_release = schedule_only(events, midnight("2022-01-04"))
    assert after_release is not None
    assert after_release["events"] == []


def test_masked_times_not_assigned_invented_precise_hours(events):
    events[0]["time_masked"] = True
    result = schedule_only(events, midnight("2022-01-03"))
    assert result["events"] == []
    assert result["uncertain_time_events_excluded_in_source_week"] == 1


def test_all_currencies_and_medium_are_allowed_but_low_is_not(events):
    for index, (currency, impact) in enumerate([("AUD", "medium"), ("EUR", "high"), ("JPY", "low")], 2):
        events.append({**events[0], "event_id": str(index), "currency": currency, "impact": impact})
    got = schedule_only(events, midnight("2022-01-03"))["events"]
    assert {e["country"] for e in got} == {"USD", "AUD", "EUR"}


def test_sorted_limited_and_deduplicated(events):
    many = []
    for i in reversed(range(12)):
        when = midnight("2022-01-03") + dt.timedelta(hours=i)
        many.append({**events[0], "event_id": str(i), "event_time": when.isoformat()})
    many.append(copy.deepcopy(many[0]))
    got = schedule_only(many, midnight("2022-01-03"))["events"]
    assert len(got) == 10
    assert [e["event_id"] for e in got] == [str(i) for i in range(10)]


@pytest.mark.parametrize("field", ["actual", "forecast", "previous", "revision", "actualBetterWorse"])
def test_input_boundary_rejects_injected_release_fields(events, field):
    calendar = schedule_only(events, midnight("2022-01-03"))
    calendar["events"][0][field] = "unexpected result"
    with pytest.raises(ValueError, match="unsupported fields"):
        validated_schedule(calendar, midnight("2022-01-03"))


def test_input_boundary_rejects_past_event(events):
    calendar = schedule_only(events, midnight("2022-01-03"))
    with pytest.raises(ValueError, match="Invalid upcoming"):
        validated_schedule(calendar, midnight("2022-01-04"))


def test_adapter_delivers_calendar_without_results_to_sentiment(events):
    snapshots = [json.loads(line) for line in Path("data/datasets/pilot_2022_01/snapshots.jsonl").read_text().splitlines()]
    snap = next(s for s in snapshots if s["sample_id"] == "2022-01-03")
    enriched = enrich_snapshots([snap], {"funding": [], "long_short": []}, events)[0]
    _, _, sentiment = adapter(enriched)
    assert sentiment["upcoming_events"][0]["title"] == "CPI"
    assert "SECRET" not in sentiment["summary_text"]
    assert "calendar and news unavailable" not in sentiment["summary_text"]
    assert "assumed announced" in sentiment["summary_text"]
    assert enriched["features"]["forex_upcoming_24h_count"] == 1


def test_pre_release_values_preserved_but_results_cannot_change_input(events):
    t = midnight("2022-01-03")
    before = schedule_only(events, t, include_pre_release_values=True)
    event = validated_schedule(before, t)[0]
    assert event["forecast"] == events[0]["forecast"]
    assert event["previous"] == events[0]["previous"]
    for field in ("actual", "revision", "actualBetterWorse", "revisionBetterWorse", "leaked"):
        events[0][field] = "FORBIDDEN_NEW_RESULT"
    assert before == schedule_only(events, t, include_pre_release_values=True)
    assert not before["point_in_time_verified"]


@pytest.mark.parametrize("field", ["actual", "revision", "actualBetterWorse", "revisionBetterWorse", "leaked"])
def test_values_mode_still_rejects_results_injected_at_adapter_boundary(events, field):
    calendar = schedule_only(events, midnight("2022-01-03"), include_pre_release_values=True)
    calendar["events"][0][field] = "hindsight"
    with pytest.raises(ValueError, match="unsupported fields"):
        validated_schedule(calendar, midnight("2022-01-03"))


def test_blank_previous_is_not_backfilled_from_actual_or_revision(events):
    events[0]["forecast"] = ""
    events[0]["previous"] = None
    point = schedule_only(events, midnight("2022-01-03"), include_pre_release_values=True)["events"][0]
    assert point["forecast"] == point["previous"] == ""


def test_values_mode_adapter_exposes_forecast_previous_with_explicit_meaning(events):
    snapshots = [json.loads(line) for line in Path("data/datasets/pilot_2022_01/snapshots.jsonl").read_text().splitlines()]
    snap = next(s for s in snapshots if s["sample_id"] == "2022-01-03")
    enriched = enrich_snapshots([snap], {"funding": [], "long_short": []}, events, calendar_values=True)[0]
    _, _, sentiment = adapter(enriched)
    assert sentiment["calendar_mode"] == "schedule_forecast_previous_assumed"
    assert "SECRET_FORECAST_7.8" in sentiment["summary_text"]
    assert "SECRET_PREVIOUS_7.7" in sentiment["summary_text"]
    assert "SECRET_ACTUAL" not in sentiment["summary_text"]
    assert "SECRET_REVISION" not in sentiment["summary_text"]
    assert "neither is the actual outcome" in sentiment["summary_text"]
    assert enriched["features"]["forex_forecast_nonempty_count"] == 1
    assert enriched["features"]["forex_previous_nonempty_count"] == 1
