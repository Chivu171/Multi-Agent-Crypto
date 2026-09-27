"""Offline contract/provenance audit against the current historical adapter.

Does not call models, fetch live data, edit the dataset, or certify vintages.
Use --require-full-live for the same strict rejection as the evaluation runner.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

from scripts.evaluate_direction import adapter, require_full_live


def audit(root):
    manifest = json.loads((root / "dataset_manifest.json").read_text())
    snapshots = [json.loads(s) for s in (root / "snapshots.jsonl").read_text().splitlines()]
    base = Path(manifest.get("base_dataset", root))
    base_manifest = json.loads((base / "dataset_manifest.json").read_text())
    artifacts = raw_records = 0
    for directory, config in [(root, manifest), (base, base_manifest)]:
        for name, digest in config["artifacts_sha256"].items():
            assert hashlib.sha256((directory / name).read_bytes()).hexdigest() == digest, name
            artifacts += 1
        for record in config["raw_responses"]:
            assert hashlib.sha256((directory / "raw" / record["body_file"]).read_bytes()).hexdigest() == record["sha256"]
            raw_records += 1
    if "base_manifest_sha256" in manifest:
        assert hashlib.sha256((base / "dataset_manifest.json").read_bytes()).hexdigest() == manifest["base_manifest_sha256"]
    # Prices directly from the saved Binance API body, not regenerated labels.
    market_record = next(r for r in base_manifest["raw_responses"] if "klines" in r["url"])
    market_rows = json.loads((base / "raw" / market_record["body_file"]).read_bytes())
    market = {int(row[0]) // 1000: row for row in market_rows}
    labels = {r["sample_id"]: r for r in csv.DictReader((root / "labels.csv").open())}
    splits = Counter(r["split"] for r in csv.DictReader((root / "splits.csv").open()))
    assert len(snapshots) == len(labels) == len({s["sample_id"] for s in snapshots})
    counts = Counter()
    rows = []
    previous_time = None
    for snap in snapshots:
        t = dt.datetime.fromisoformat(snap["prediction_time"])
        assert t.utcoffset() == dt.timedelta(0) and t.hour == t.minute == t.second == 0
        assert previous_time is None or t - previous_time == dt.timedelta(days=1)
        previous_time = t
        assert snap["horizon_hours"] == 24
        chain, technical, sentiment = adapter(snap)
        assert len(chain["metrics"]) == 4
        for field in ("price", "ema20", "ema50", "rsi14"):
            assert math.isfinite(technical[field])
        assert technical["price"] > 0 and 0 <= technical["rsi14"] <= 100
        assert 0 <= sentiment["fear_greed"]["value"] <= 100
        for point in snap["evidence"].values():
            if isinstance(point, dict) and "available_at" in point:
                assert dt.datetime.fromisoformat(point["available_at"]) <= t
        for candle in snap["market_window"]["candles"]:
            when = dt.datetime.fromisoformat(candle["open_time"])
            assert when + dt.timedelta(days=1) <= t
            raw = market[int(when.timestamp())]
            for index, field in enumerate(("open", "high", "low", "close", "volume"), 1):
                assert candle[field] == float(raw[index])
        label = labels[snap["sample_id"]]
        reference = float(market[int(t.timestamp()) - 86400][4])
        future = float(market[int(t.timestamp())][4])
        assert technical["price"] == reference == float(label["reference_price"])
        assert future == float(label["future_price"])
        assert math.isclose(future / reference - 1, float(label["return_24h"]), abs_tol=1e-12)
        assert dt.datetime.fromisoformat(label["target_end"]) == t + dt.timedelta(days=1)
        events = sentiment.get("upcoming_events", [])
        for event in events:
            assert not ({"actual", "revision", "label", "return_24h"} & event.keys())
            assert dt.datetime.fromisoformat(event["date"]) >= t
        calendar = snap.get("historical_extras", {}).get("forex_calendar")
        counts.update({"adapter_days": 1, "onchain_days": 1, "market_days": 1,
                       "fear_greed_days": 1, "funding_days": technical["funding_rate"] is not None,
                       "long_short_days": technical["long_short_ratio"] is not None,
                       "calendar_days": calendar is not None, "nonempty_calendar_days": bool(events),
                       "verified_calendar_days": bool(calendar and calendar["point_in_time_verified"]),
                       "event_entries": len(events),
                       "forecast_entries": sum(bool(e.get("forecast", "").strip()) for e in events),
                       "previous_entries": sum(bool(e.get("previous", "").strip()) for e in events)})
        differences = {}
        for n in (20, 50):
            csv_ema = snap["features"]["close"] / (1 + snap["features"][f"ema{n}_gap"])
            difference = technical[f"ema{n}"] - csv_ema
            differences[f"ema{n}_adapter_minus_feature"] = difference
            counts[f"ema{n}_different_days"] += not math.isclose(csv_ema, technical[f"ema{n}"], rel_tol=1e-10)
        rows.append({"sample_id": snap["sample_id"], "ratio_present": technical["long_short_ratio"] is not None,
                     "calendar_events": len(events), **differences})
    try:
        require_full_live(snapshots)
        rejection = None
    except ValueError as exc:
        rejection = str(exc)
    report = {"dataset": str(root), "snapshot_sha256": hashlib.sha256((root / "snapshots.jsonl").read_bytes()).hexdigest(),
              "requested_days": len(snapshots), "artifact_hash_checks": artifacts,
              "raw_hash_checks": raw_records, "counts": dict(counts), "splits": dict(splits),
              "adapter_contract_passed": True, "price_labels_match_archived_binance": True,
              "timestamps_pass_under_recorded_assumptions": True, "full_live_guard_rejection": rejection,
              "scope": "Offline input compatibility, saved provenance, and arithmetic; not certification of historical publication times or model accuracy.",
              "days": rows}
    return report, snapshots


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/datasets/pilot_2022_01_forecast_previous"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-full-live", action="store_true")
    args = parser.parse_args()
    report, snapshots = audit(args.dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "days"}, ensure_ascii=False, indent=2))
    if args.require_full_live:
        require_full_live(snapshots)


if __name__ == "__main__":
    main()
