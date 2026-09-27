"""ForexFactory reconstruction: explicitly assumed, not a verified vintage.

Event metadata and optionally forecast/previous can cross into model inputs.
Actual, revision and result annotations never can. Publication time is not inferred.
"""

import datetime as dt

from data_sources.historical_data import DAY, UTC, iso

ASSUMPTION = ("Reconstructed historical schedule assumed announced before prediction; "
              "historical changes to event time/title/impact are not verified. "
              "No actual, forecast, previous, revision or release result is supplied.")
EVENT_FIELDS = {"event_id", "title", "country", "impact", "date", "source_url", "raw_file"}
PRE_RELEASE_FIELDS = {"forecast", "previous"}
ASSUMPTIONS = {
    "schedule_only_assumed": ASSUMPTION,
    "schedule_forecast_previous_assumed": (
        "Historical schedule, forecast and previous values are reconstructed from retrospective pages "
        "and assumed available before prediction; historical changes are not verified. "
        "Forecast is an expectation, previous refers to the preceding release period, "
        "and neither is the actual outcome of the upcoming event. Empty values are unavailable. "
        "No actual, revision or release-result annotation is supplied."
    ),
}


def schedule_only(events, prediction_time, limit=10, *, include_pre_release_values=False):
    t = prediction_time.astimezone(UTC)
    week_start = t.replace(hour=0, minute=0, second=0, microsecond=0) - dt.timedelta(days=(t.weekday()+1) % 7)
    week_end = week_start+7*DAY
    month = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")[week_start.month-1]
    week = f"{month}{week_start.day}.{week_start.year}"
    source = [e for e in events if e.get("source_week") == week]
    if not source:  # No verified parsed page; absence of a source is not an empty calendar.
        return None
    selected, skipped = {}, 0
    for event in source:
        impact = str(event.get("impact", "")).lower()
        if impact not in ("high", "medium"):
            continue
        if event.get("time_masked") or not event.get("event_time"):
            skipped += 1
            continue
        when = dt.datetime.fromisoformat(event["event_time"])
        if when.tzinfo is None:
            raise ValueError("Calendar event requires timezone")
        if not t <= when < week_end:
            continue
        # Whitelist: never copy the upcoming release's actual or hindsight annotations.
        item = {"event_id": str(event["event_id"]), "title": event["title"],
                "country": event["currency"], "impact": impact.title(), "date": iso(when),
                "source_url": f"https://www.forexfactory.com/calendar?week={week}",
                "raw_file": event["raw_file"]}
        if include_pre_release_values:
            for field in sorted(PRE_RELEASE_FIELDS):
                value = event.get(field)
                if value is not None and not isinstance(value, str):
                    raise ValueError(f"Calendar {field} must be source text or null")
                item[field] = value if value is not None else ""
        old = selected.get(item["event_id"])
        if old and old != item:
            raise ValueError("Conflicting schedule entries for the same event")
        selected[item["event_id"]] = item
    ordered = sorted(selected.values(), key=lambda e: (e["date"], e["event_id"]))
    mode = "schedule_forecast_previous_assumed" if include_pre_release_values else "schedule_only_assumed"
    return {"mode": mode, "point_in_time_verified": False,
            "publication_time": None, "availability_assumption": ASSUMPTIONS[mode],
            "selection": "next High/Medium events, all currencies, current UTC Sunday-to-Saturday week",
            "window_end_exclusive": iso(week_end), "limit": limit,
            "uncertain_time_events_excluded_in_source_week": skipped,
            "events": ordered[:limit]}


def validated_schedule(calendar, prediction_time):
    """Validate the chosen input mode; no actual/revision/result fields are allowed."""
    mode = calendar.get("mode")
    if mode not in ASSUMPTIONS:
        raise ValueError("Unsupported calendar input mode")
    if calendar.get("point_in_time_verified") is not False or calendar.get("publication_time") is not None:
        raise ValueError("A reconstructed schedule must not claim verified publication")
    end = dt.datetime.fromisoformat(calendar["window_end_exclusive"])
    if not prediction_time < end <= prediction_time+7*DAY:
        raise ValueError("Invalid calendar window")
    events = calendar["events"]
    if len(events) > 10:
        raise ValueError("Too many upcoming events")
    seen, result = set(), []
    allowed_fields = EVENT_FIELDS | (PRE_RELEASE_FIELDS if mode == "schedule_forecast_previous_assumed" else set())
    for event in events:
        if set(event) != allowed_fields:
            raise ValueError("Calendar event contains unsupported fields or missing metadata")
        for field in PRE_RELEASE_FIELDS & event.keys():
            if not isinstance(event[field], str):
                raise ValueError(f"Calendar {field} must be source text")
        stamp = dt.datetime.fromisoformat(event["date"])
        if not prediction_time <= stamp < end or event["impact"] not in ("High", "Medium"):
            raise ValueError("Invalid upcoming event")
        if event["event_id"] in seen:
            raise ValueError("Duplicate calendar event")
        seen.add(event["event_id"])
        result.append(dict(event))
    return sorted(result, key=lambda e: (e["date"], e["event_id"]))
