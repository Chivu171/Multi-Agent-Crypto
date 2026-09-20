"""Audit existing dataset against raw archives and optional fresh provider responses.

Does not rewrite dataset files. New live responses are archived under audit/.
"""
import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import statistics
from pathlib import Path

from data_sources.historical_data import Archive, parse_forex_calendar


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


def check_number(actual, expected):
    if expected is None:
        assert actual == "", (actual, expected)
    else:
        assert math.isclose(float(actual), expected, rel_tol=1e-10, abs_tol=1e-10), (actual, expected)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/datasets/pilot_2022_01"))
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    root = args.dataset
    manifest = json.loads((root / "dataset_manifest.json").read_text())
    config = manifest["config"]
    checked_at = dt.datetime.now(dt.timezone.utc)
    audit = root / "audit" / checked_at.strftime("%Y%m%dT%H%M%S%fZ")
    audit.mkdir(parents=True)
    report = {"checked_at": checked_at.isoformat(), "live_requested": args.live,
              "checks": [], "live_comparisons": []}
    for name, digest in manifest["artifacts_sha256"].items():
        assert hashlib.sha256((root / name).read_bytes()).hexdigest() == digest, name
    report["checks"].append("All manifest artifact checksums match")
    source = json.loads((root / "source_data.json").read_text())
    raw_sources = {}
    records = manifest["raw_responses"]
    for record in records:
        body = (root / "raw" / record["body_file"]).read_bytes()
        assert hashlib.sha256(body).hexdigest() == record["sha256"], record["body_file"]
        url = record["url"]
        if "forexfactory" in url:
            continue
        parsed = json.loads(body)
        if "klines" in url:
            assert parsed == source["market"]
            raw_sources["market"] = parsed
        elif "/charts/" in url:
            name = url.rsplit("/", 1)[-1]
            assert parsed["values"] == source["onchain"][name]
            raw_sources[name] = {int(p["x"]): float(p["y"]) for p in parsed["values"]}
        else:
            assert parsed["data"] == source["fear_greed"]
            raw_sources["fear_greed"] = {int(p["timestamp"]): float(p["value"]) for p in parsed["data"]}
    report["checks"].append(f"All {len(records)} raw response hashes checked; normalized API data equals raw JSON")
    market = {int(r[0]) // 1000: r for r in raw_sources["market"]}
    features = read_csv(root / "features.csv")
    labels = read_csv(root / "labels.csv")
    snapshots = [json.loads(line) for line in (root / "snapshots.jsonl").read_text().splitlines()]
    assert len(features) == len(labels) == len(snapshots)
    missing = []
    for row, label, snap in zip(features, labels, snapshots):
        assert row["sample_id"] == label["sample_id"] == snap["sample_id"]
        t = int(dt.datetime.fromisoformat(row["prediction_time"]).timestamp())
        candles = [market[t - n*86400] for n in range(90, 0, -1)]
        closes = [float(c[4]) for c in candles]
        volumes = [float(c[5]) for c in candles]
        p, future = closes[-1], float(market[t][4])
        check_number(label["reference_price"], p)
        check_number(label["future_price"], future)
        check_number(label["return_24h"], future/p-1)
        threshold = config["threshold"]
        assert label["label"] == ("BUY" if future > p*(1+threshold) else "SELL" if future < p*(1-threshold) else "NEUTRAL")
        expected = {"close": p, "volume": volumes[-1],
                    "volume_change_1d": volumes[-1]/volumes[-2]-1 if volumes[-2] else None}
        for n in (1, 7, 30):
            expected[f"return_{n}d"] = p/closes[-n-1]-1
        returns = [b/a-1 for a, b in zip(closes, closes[1:])]
        for n in (7, 30):
            expected[f"volatility_{n}d"] = statistics.pstdev(returns[-n:])
        for n in (20, 50):
            ema = statistics.mean(closes[:n])
            for c in closes[n:]:
                ema += 2/(n+1)*(c-ema)
            expected[f"ema{n}_gap"] = p/ema-1
        deltas = [b-a for a, b in zip(closes[-15:], closes[-14:])]
        gain = sum(max(d, 0) for d in deltas)/14
        loss = sum(max(-d, 0) for d in deltas)/14
        expected["rsi14"] = 100 if loss == 0 else 100-100/(1+gain/loss)
        for name, values in raw_sources.items():
            if name == "market":
                continue
            prefix = name.replace("-", "_")
            lag = (config["fear_greed_lag_days"] if name == "fear_greed" else config["onchain_lag_days"])*86400
            candidates = [epoch for epoch in values if epoch+lag <= t]
            epoch = max(candidates) if candidates else None
            valid = epoch is not None and t-epoch-lag <= 72*3600
            point = snap["evidence"][name]
            assert (point is not None) == valid
            expected[f"{prefix}_missing"] = 0 if valid else 1
            if valid:
                assert point["value"] == values[epoch]
                assert dt.datetime.fromisoformat(point["observed_at"]).timestamp() == epoch
                assert dt.datetime.fromisoformat(point["available_at"]).timestamp() == epoch+lag
                expected[f"{prefix}_value"] = values[epoch]
                expected[f"{prefix}_age_hours"] = (t-epoch-lag)/3600
                for n in (1, 7):
                    prev = values.get(epoch-n*86400)
                    change = None if prev is None else values[epoch]-prev if name == "fear_greed" else values[epoch]/prev-1 if prev else None
                    expected[f"{prefix}_change_{n}d"] = change
                window = [values.get(epoch-n*86400) for n in range(7)]
                expected[f"{prefix}_mean_7d"] = statistics.mean(window) if all(v is not None for v in window) else None
            else:
                expected.update({f"{prefix}_{suffix}": None for suffix in ("value", "age_hours", "change_1d", "change_7d", "mean_7d")})
        assert set(row) == set(expected) | {"sample_id", "prediction_time"}
        for key, value in expected.items():
            check_number(row[key], value)
            assert snap["features"][key] == (None if row[key] == "" else float(row[key]))
            if value is None:
                missing.append({"sample_id": row["sample_id"], "feature": key})
        for candle, actual in zip(candles, snap["market_window"]["candles"]):
            assert dt.datetime.fromisoformat(actual["open_time"]).timestamp() == int(candle[0])/1000
            assert int(candle[6])/1000 < t
            for i, key in enumerate(("open", "high", "low", "close", "volume"), 1):
                assert actual[key] == float(candle[i])
    report["checks"].append(f"Independently recomputed every numeric feature and all {len(labels)} labels from archived raw data")
    report["missing_cells"] = missing
    report["label_counts"] = {x: sum(r["label"] == x for r in labels) for x in ("BUY", "SELL", "NEUTRAL")}
    events = json.loads((root / "forex_events_RETROSPECTIVE_ONLY.json").read_text())
    for record in records:
        if "forexfactory" not in record["url"]:
            continue
        parsed = parse_forex_calendar((root / "raw" / record["body_file"]).read_text())
        exported = [e for e in events if e["raw_file"] == record["body_file"]]
        assert len(parsed) == len(exported)
        by_id = {e["event_id"]: e for e in exported}
        for e in parsed:
            assert all(by_id[e["event_id"]][k] == v for k, v in e.items())
    report["checks"].append(f"All {len(events)} exported Forex events trace to archived HTML; availability remains unverified")
    if args.live:
        fresh = Archive(audit / "raw")
        for record in records:
            url = record["url"]
            print(f"Re-fetching {url} {record['params']}", flush=True)
            result = {"url": url, "params": record["params"]}
            try:
                current = fresh.get(url, record["params"], as_json="forexfactory" not in url)
                if "forexfactory" in url:
                    old = parse_forex_calendar((root / "raw" / record["body_file"]).read_text())
                    new = parse_forex_calendar(current)
                    key = lambda e: e["event_id"]
                    old, new = {key(e): e for e in old}, {key(e): e for e in new}
                elif "klines" in url:
                    old, new = {int(r[0]): r for r in raw_sources["market"]}, {int(r[0]): r for r in current}
                elif "/charts/" in url:
                    old = raw_sources[url.rsplit("/", 1)[-1]]
                    new = {int(p["x"]): float(p["y"]) for p in current["values"]}
                else:
                    old = raw_sources["fear_greed"]
                    new = {int(p["timestamp"]): float(p["value"]) for p in current["data"]}
                differences = [str(k) for k in old if k not in new or old[k] != new[k]]
                result.update({"archived_records": len(old), "matching_records": len(old)-len(differences),
                               "differences": differences, "status": "match" if not differences else "DIFFERENCE"})
            except Exception as exc:
                result.update({"status": "FAILED", "error": str(exc)})
            report["live_comparisons"].append(result)
        report["fresh_raw_responses"] = fresh.records
    report["passed"] = all(r["status"] == "match" for r in report["live_comparisons"])
    report["scope"] = "Provider provenance and arithmetic; not proof of point-in-time availability or investment validity"
    (audit / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n")
    print(json.dumps({"report": str(audit / "report.json"), "passed": report["passed"], "checks": report["checks"], "live": report["live_comparisons"]}, indent=2))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
