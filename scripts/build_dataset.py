"""Download and build a daily historical dataset, or rebuild from archived data.

Run: python -m scripts.build_dataset --start 2022-01-01 --end 2022-01-30 --forex
"""

import argparse
import json
from pathlib import Path

from data_sources.historical_data import Archive, CHARTS, DAY, fetch_fear_greed, fetch_market, fetch_onchain, midnight, parse_forex_calendar, probe_forex
from utils.historical_dataset import build, write_dataset, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2022-01-01")
    parser.add_argument("--end", default="2022-01-30")
    parser.add_argument("--output", type=Path, default=Path("data/datasets/pilot_2022_01"))
    parser.add_argument("--threshold", type=float, default=0.01)
    parser.add_argument("--onchain-lag-days", type=int, default=2)
    parser.add_argument("--fear-greed-lag-days", type=int, default=1)
    parser.add_argument("--forex", action="store_true", help="Archive weekly historical HTML for manual verification; excluded from features")
    parser.add_argument("--offline", action="store_true", help="Rebuild from source_data.json; no network")
    args = parser.parse_args()
    start, end = midnight(args.start), midnight(args.end)
    if start > end or start < midnight("2022-01-01") or end > midnight("2025-12-31"):
        parser.error("Use a nonempty date range within the fixed 2022–2025 study")
    if not 0 < args.threshold < 1:
        parser.error("threshold must be between 0 and 1")
    if args.onchain_lag_days < 2 or args.fear_greed_lag_days < 1:
        parser.error("Use on-chain lag >=2 days and Fear & Greed lag >=1 day")
    config = {"start": args.start, "end": args.end, "horizon_hours": 24, "timezone": "UTC",
              "threshold": args.threshold, "onchain_lag_days": args.onchain_lag_days,
              "fear_greed_lag_days": args.fear_greed_lag_days, "max_source_age_hours": 72,
              "market_window_days": 90, "forex_requested": args.forex,
              "train_end": "2024-06-30", "validation_end": "2024-12-31", "test_end": "2025-12-31"}
    root = args.output
    source_path = root / "source_data.json"
    if source_path.exists():
        manifest_path = root / "dataset_manifest.json"
        if manifest_path.exists():
            import hashlib
            manifest = json.loads(manifest_path.read_text())
            expected = manifest["artifacts_sha256"]["source_data.json"]
            if hashlib.sha256(source_path.read_bytes()).hexdigest() != expected:
                raise ValueError("source_data.json checksum mismatch")
        source = json.loads(source_path.read_text())
        if source["request"] != {"start": args.start, "end": args.end, "forex": args.forex}:
            parser.error("Existing output has a different request; choose a new --output directory")
        records = source["raw_responses"]
        # Validate raw integrity even during offline rebuild.
        import hashlib
        for record in records:
            body = (root / "raw" / record["body_file"]).read_bytes()
            if hashlib.sha256(body).hexdigest() != record["sha256"]:
                raise ValueError(f"Raw checksum mismatch: {record['body_file']}")
    else:
        archive = Archive(root / "raw", offline=args.offline)
        source = {"request": {"start": args.start, "end": args.end, "forex": args.forex},
                  "onchain": {}, "errors": {}}
        print("Fetching Binance daily candles...", flush=True)
        source["market"] = fetch_market(archive, start-100*DAY, end+DAY)
        for chart in CHARTS:
            print(f"Fetching on-chain: {chart}...", flush=True)
            try:
                source["onchain"][chart] = fetch_onchain(archive, chart, start-100*DAY, end+DAY)
            except Exception as exc:
                source["errors"][chart] = str(exc)
                source["onchain"][chart] = []
        print("Fetching Fear & Greed history...", flush=True)
        try:
            source["fear_greed"] = fetch_fear_greed(archive)
        except Exception as exc:
            source["errors"]["fear_greed"] = str(exc)
            source["fear_greed"] = []
        source["forex"] = probe_forex(archive, start, end+DAY) if args.forex else []
        records = archive.records
        source["raw_responses"] = records
        write_json(source_path, source)
    # Parse calendars from the raw archive on every build, including offline.
    events = {}
    for record in records:
        if record["url"] != "https://www.forexfactory.com/calendar" or record["status"] != 200:
            continue
        try:
            html = (root / "raw" / record["body_file"]).read_text(encoding="utf-8")
            parsed = parse_forex_calendar(html)
            for event in parsed:
                event.update({"retrieved_at": record["retrieved_at"], "raw_file": record["body_file"],
                              "source_week": record["params"]["week"]})
                # Same event on different downloaded pages is kept as separate provenance.
                events[(event["event_id"], event["source_week"])] = event
        except (ValueError, KeyError, TypeError) as exc:
            source["errors"][f"forex_parse_{record['params']['week']}"] = str(exc)
    source["forex_events"] = sorted(events.values(), key=lambda e: (e["event_time"] or "", e["event_id"]))
    dataset = build(source, start, end, args.threshold, args.onchain_lag_days, args.fear_greed_lag_days)
    quality = write_dataset(root, dataset, config, source, records)
    print(json.dumps({key: quality[key] for key in ("requested_days", "rows", "eligible_core_rows", "eligible_full_rows", "label_counts", "source_errors")}, indent=2))
    print(f"Review: {root / 'VERIFY.md'}")
    if not quality["rows"]:
        raise SystemExit("No labelled samples produced; inspect source_data.json")


if __name__ == "__main__":
    main()
