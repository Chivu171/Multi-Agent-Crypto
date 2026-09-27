"""Official Binance archives, with publisher checksums and explicit time semantics."""

import csv
import datetime as dt
import hashlib
import io
import math
from pathlib import PurePosixPath
import zipfile

from data_sources.historical_data import DAY, UTC, iso

BASE = "https://data.binance.vision/data/futures/um"


def checked_csv(archive, url):
    """Never extract ZIP paths; verify Binance's .CHECKSUM before parsing."""
    body = archive.get(url, as_bytes=True)
    checksum = archive.get(url + ".CHECKSUM", as_json=False).split()
    if len(checksum) < 2 or PurePosixPath(checksum[1].lstrip("*")).name != url.rsplit("/", 1)[1]:
        raise ValueError("Unexpected publisher checksum filename")
    if hashlib.sha256(body).hexdigest() != checksum[0]:
        raise ValueError("Binance publisher checksum mismatch")
    with zipfile.ZipFile(io.BytesIO(body)) as bundle:
        expected = url.rsplit("/", 1)[1].removesuffix(".zip") + ".csv"
        if bundle.namelist() != [expected]:
            raise ValueError("Unexpected archive member")
        text = bundle.read(expected).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text)))


def finite_number(value, *, positive=False):
    number = float(value)
    if not math.isfinite(number) or (positive and number <= 0):
        raise ValueError("Invalid numeric observation")
    return number


def funding_point(row, url):
    stamp = dt.datetime.fromtimestamp(int(row["calc_time"]) / 1000, UTC)
    interval = finite_number(row["funding_interval_hours"], positive=True)
    return {"observed_at": iso(stamp), "available_at": iso(stamp),
            "value": finite_number(row["last_funding_rate"]),
            "funding_interval_hours": interval, "source_url": url,
            "availability_assumption": "settlement calc_time; delivery latency not archived",
            "semantics": "last settled funding rate; not an archived premiumIndex snapshot"}


def ratio_point(row, url):
    if row["symbol"] != "BTCUSDT":
        raise ValueError("Unexpected metrics symbol")
    # Empty is unknown, never 0 and never replaced with a top-trader ratio.
    value = row["count_long_short_ratio"].strip()
    if not value:
        return None
    stamp = dt.datetime.strptime(row["create_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
    return {"observed_at": iso(stamp), "available_at": iso(stamp + dt.timedelta(minutes=5)),
            "value": finite_number(value, positive=True), "source_url": url,
            "source_column": "count_long_short_ratio", "period": "5m",
            "availability_assumption": "create_time + 5 minutes; publication vintage unverified",
            "semantics": "global account ratio, 5m archive observation; live query uses period=1d"}


def latest_before(points, prediction_time, max_age_hours):
    """Strict cutoff: no observation at/after the decision instant is consumed."""
    eligible = [p for p in points if dt.datetime.fromisoformat(p["available_at"]) < prediction_time]
    if not eligible:
        return None
    point = max(eligible, key=lambda p: dt.datetime.fromisoformat(p["available_at"]))
    age = (prediction_time - dt.datetime.fromisoformat(point["observed_at"])).total_seconds() / 3600
    if age > max_age_hours:
        return None
    return {**point, "age_hours": age}


def fetch_derivatives(archive, start, end):
    """Fetch funding months plus daily metrics covering the preceding day too."""
    first = start - DAY
    result = {"funding": [], "long_short": [], "files": [], "errors": {}}
    month = first.replace(day=1)
    while month <= end:
        url = f"{BASE}/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-{month:%Y-%m}.zip"
        try:
            rows = checked_csv(archive, url)
            points = [funding_point(row, url) for row in rows]
            result["funding"].extend(points)
            result["files"].append({"kind": "funding", "url": url, "rows": len(rows),
                                    "publisher_checksum_verified": True})
        except (ValueError, RuntimeError, OSError, zipfile.BadZipFile, KeyError) as exc:
            result["errors"][url] = str(exc)
        month = (month.replace(day=28) + 4 * DAY).replace(day=1)
    day = first
    while day < end:  # Last decision only needs observations before its midnight.
        url = f"{BASE}/daily/metrics/BTCUSDT/BTCUSDT-metrics-{day:%Y-%m-%d}.zip"
        try:
            rows = checked_csv(archive, url)
            points = [ratio_point(row, url) for row in rows]
            valid = [p for p in points if p is not None]
            result["long_short"].extend(valid)
            result["files"].append({"kind": "metrics", "date": f"{day:%Y-%m-%d}", "url": url,
                                    "rows": len(rows), "global_ratio_nonempty": len(valid),
                                    "global_ratio_empty": len(rows)-len(valid),
                                    "publisher_checksum_verified": True})
        except (ValueError, RuntimeError, OSError, zipfile.BadZipFile, KeyError) as exc:
            result["errors"][url] = str(exc)
        day += DAY
    for key in ("funding", "long_short"):
        result[key].sort(key=lambda p: p["observed_at"])
        times = [p["observed_at"] for p in result[key]]
        if len(times) != len(set(times)):
            raise ValueError(f"Duplicate {key} timestamps")
    return result


def verify_funding_api(archive, points, start, end):
    """Cross-check actual archive values against the official REST funding history."""
    begin, stop = int((start-DAY).timestamp()*1000), int(end.timestamp()*1000)
    cursor, rows = begin, []
    while cursor < stop:
        page = archive.get("https://fapi.binance.com/fapi/v1/fundingRate", {
            "symbol": "BTCUSDT", "startTime": cursor, "endTime": stop-1, "limit": 1000})
        if not isinstance(page, list):
            raise ValueError("Invalid funding API response")
        if not page:
            break
        rows.extend(page)
        next_cursor = int(page[-1]["fundingTime"]) + 1
        if next_cursor <= cursor:
            raise ValueError("Funding API pagination did not advance")
        cursor = next_cursor
    expected = {p["observed_at"]: p["value"] for p in points
                if start-DAY <= dt.datetime.fromisoformat(p["observed_at"]) < end}
    actual = {}
    for row in rows:
        if row["symbol"] != "BTCUSDT":
            raise ValueError("Unexpected funding symbol")
        stamp = iso(dt.datetime.fromtimestamp(int(row["fundingTime"])/1000, UTC))
        if stamp in actual:
            raise ValueError("Duplicate API funding timestamps")
        actual[stamp] = finite_number(row["fundingRate"])
    mismatches = [t for t in expected.keys() | actual.keys()
                  if t not in expected or t not in actual or abs(expected[t]-actual[t]) > 1e-12]
    return {"archive_rows": len(expected), "api_rows": len(actual),
            "matched": bool(expected) and not mismatches, "mismatch_timestamps": sorted(mismatches)}
