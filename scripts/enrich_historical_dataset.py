"""Enrich a verified core dataset without overwriting it or claiming live parity.

python -m scripts.enrich_historical_dataset
python -m scripts.enrich_historical_dataset --offline
"""

import argparse
import copy
import csv
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil

from data_sources.historical_data import Archive, DAY, UTC, iso, midnight
from data_sources.historical_derivatives import fetch_derivatives, latest_before, verify_funding_api
from utils.historical_dataset import write_json
from utils.historical_calendar import schedule_only


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def probe_forex_vintages(archive, start, end):
    """Locate old captures; discovery alone never authorizes a calendar feature.

    A closest capture can be AFTER the requested date. Record that explicitly.
    This is a bounded public archive search, not proof that no other archive exists.
    """
    results = []
    day = start - dt.timedelta(days=(start.weekday()+1) % 7)
    months = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
    while day <= end:
        week = f"{months[day.month-1]}{day.day}.{day.year}"
        query_time = max(day, start)
        for source_url in (f"https://www.forexfactory.com/calendar?week={week}",
                           "https://nfs.faireconomy.media/ff_calendar_thisweek.xml",
                           "https://nfs.faireconomy.media/ff_calendar_thisweek.json"):
            item = {"source_url": source_url, "requested_at": iso(query_time),
                    "use_in_primary_features": False}
            try:
                response = archive.get("https://archive.org/wayback/available", {
                    "url": source_url, "timestamp": query_time.strftime("%Y%m%d%H%M%S")})
                closest = response.get("archived_snapshots", {}).get("closest")
                item["closest"] = closest
                if closest and closest.get("available"):
                    captured = dt.datetime.strptime(closest["timestamp"], "%Y%m%d%H%M%S").replace(tzinfo=UTC)
                    item["captured_at"] = iso(captured)
                    item["status"] = ("capture_after_requested_time" if captured > query_time
                                      else "candidate_requires_content_and_week_verification")
                    item["age_days_at_request"] = (query_time-captured).total_seconds()/86400
                else:
                    item["status"] = "no_capture_returned"
            except (ValueError, RuntimeError, OSError, KeyError, TypeError) as exc:
                item.update(status="lookup_failed", error=str(exc))
            results.append(item)
        day += 7*DAY
    return results


def enrich_snapshots(snapshots, derivatives, calendar_events=None, *, calendar_values=False):
    result = copy.deepcopy(snapshots)
    for snap in result:
        t = dt.datetime.fromisoformat(snap["prediction_time"])
        funding = latest_before(derivatives["funding"], t, 12)
        ratio = latest_before(derivatives["long_short"], t, 24)
        snap["historical_extras"] = {"funding_rate": funding, "long_short_ratio": ratio,
                                     "forex_calendar": None}
        if calendar_events is not None:
            calendar = schedule_only(calendar_events, t, include_pre_release_values=calendar_values)
            snap["historical_extras"]["forex_calendar"] = calendar
            upcoming = calendar["events"] if calendar else []
            snap["features"]["forex_schedule_available"] = int(calendar is not None)
            snap["features"]["forex_upcoming_count"] = len(upcoming) if calendar else None
            snap["features"]["forex_upcoming_24h_count"] = sum(
                dt.datetime.fromisoformat(e["date"]) < t+DAY for e in upcoming) if calendar else None
            if calendar_values:
                for field in ("forecast", "previous"):
                    snap["features"][f"forex_{field}_nonempty_count"] = sum(
                        bool(e[field].strip()) for e in upcoming) if calendar else None
        for name, point in (("funding_rate", funding), ("long_short_ratio", ratio)):
            snap["features"][name] = point["value"] if point else None
            snap["features"][name+"_missing"] = int(point is None)
            snap["features"][name+"_age_hours"] = point["age_hours"] if point else None
        snap["unavailable"] = ["forex_point_in_time"] + [name for name, point in
                               (("funding_rate", funding), ("long_short_ratio", ratio)) if point is None]
        snap["status"] = "historical_enriched_partial_not_live_equivalent"
        snap["eligible_full_live"] = False
    return result


def write_csv(path, rows):
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=Path("data/datasets/pilot_2022_01"))
    parser.add_argument("--output", type=Path, default=Path("data/datasets/pilot_2022_01_enriched"))
    parser.add_argument("--offline", action="store_true", help="Rebuild using checked raw cache; no network")
    parser.add_argument("--calendar-schedule", action="store_true",
                        help="Use event metadata only, with explicit historical-schedule availability assumption")
    parser.add_argument("--calendar-values", action="store_true",
                        help="Include archived forecast/previous with unverified pre-release availability; implies --calendar-schedule")
    args = parser.parse_args()
    if args.calendar_values:
        args.calendar_schedule = True
    if args.base.resolve() == args.output.resolve():
        parser.error("Use a separate output directory; the baseline dataset stays immutable")
    manifest_bytes = (args.base/"dataset_manifest.json").read_bytes()
    base_manifest = json.loads(manifest_bytes)
    for name, expected in base_manifest["artifacts_sha256"].items():
        if digest(args.base/name) != expected:
            raise ValueError(f"Base artifact checksum mismatch: {name}")
    for record in base_manifest["raw_responses"]:
        if digest(args.base/"raw"/record["body_file"]) != record["sha256"]:
            raise ValueError(f"Base raw checksum mismatch: {record['body_file']}")
    snapshots = [json.loads(line) for line in (args.base/"snapshots.jsonl").read_text().splitlines()]
    if not snapshots:
        raise ValueError("Empty base dataset")
    config = base_manifest["config"]
    start, end = midnight(config["start"]), midnight(config["end"])
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    request = {"base_manifest_sha256": hashlib.sha256(manifest_bytes).hexdigest(),
               "start": config["start"], "end": config["end"], "version": 1}
    if args.calendar_schedule:
        request["calendar_mode"] = ("schedule_forecast_previous_assumed" if args.calendar_values else "schedule_only_assumed")
    request_path = root/"enrichment_request.json"
    if request_path.exists() and json.loads(request_path.read_text()) != request:
        raise ValueError("Different enrichment request: use a new output directory")
    write_json(request_path, request)
    archive = Archive(root/"raw", offline=args.offline)
    print("Downloading/verifying official funding and daily metrics archives...", flush=True)
    derivatives = fetch_derivatives(archive, start, end)
    print("Cross-checking funding with Binance REST history...", flush=True)
    try:
        funding_check = verify_funding_api(archive, derivatives["funding"], start, end)
    except (ValueError, RuntimeError, OSError, KeyError) as exc:
        funding_check = {"matched": False, "error": str(exc)}
    # A contradictory independent response must not silently enter the dataset.
    if funding_check.get("mismatch_timestamps"):
        write_json(root/"funding_crosscheck.json", funding_check)
        raise ValueError("Funding API/archive mismatch; inspect funding_crosscheck.json")
    print("Looking for dated ForexFactory archive captures...", flush=True)
    forex_probe = probe_forex_vintages(archive, start, end)
    events = json.loads((args.base/"forex_events_RETROSPECTIVE_ONLY.json").read_text())
    enriched = enrich_snapshots(snapshots, derivatives, events if args.calendar_schedule else None,
                               calendar_values=args.calendar_values)
    with (root/"snapshots.jsonl").open("w") as stream:
        for snap in enriched:
            stream.write(json.dumps(snap, ensure_ascii=False, allow_nan=False)+"\n")
    write_csv(root/"features.csv", [s["features"] for s in enriched])
    if args.calendar_schedule:
        with (root/"forex_schedule.jsonl").open("w") as stream:
            for snap in enriched:
                stream.write(json.dumps({"sample_id": snap["sample_id"], "prediction_time": snap["prediction_time"],
                    "calendar": snap["historical_extras"]["forex_calendar"]}, ensure_ascii=False)+"\n")
    # Labels and split assignments are unchanged; never feed labels to an agent.
    for name in ("labels.csv", "splits.csv", "forex_events_RETROSPECTIVE_ONLY.json"):
        shutil.copyfile(args.base/name, root/name)
    relevant = [e for e in events if e["impact"] in ("high", "medium") and e["event_time"]
                and config["start"] <= e["event_time"][:10] <= config["end"]]
    coverage = [{"sample_id": s["sample_id"],
                 "funding_present": s["historical_extras"]["funding_rate"] is not None,
                 "global_ratio_5m_present": s["historical_extras"]["long_short_ratio"] is not None,
                 "forex_schedule_present": s["historical_extras"]["forex_calendar"] is not None,
                 "forex_point_in_time_present": False, "eligible_full_live": False,
                 "missing": s["unavailable"]} for s in enriched]
    limitations = [
        "ForexFactory forecast/previous/calendar vintages not verified; retrospective records excluded from prompts.",
        "Global long/short uses the 5m archive column, not live period=1d; empty source cells remain missing.",
        "Funding is last settled rate, not a historical premiumIndex snapshot of lastFundingRate.",
        "On-chain and Fear & Greed publication times remain assumed; source vintages are unverified.",
        "Daily closed-candle evaluation differs from live intraday/current-candle fetching.",
        "This remains the base pilot's time split, not an independent held-out evaluation.",
        "Historical LLM knowledge contamination possible.",
    ]
    if args.calendar_schedule:
        limitations[0] = ("ForexFactory event metadata only; assumes the historical schedule was announced before prediction. "
                          "Schedule revisions unverified. Actual/forecast/previous/revision excluded.")
    if args.calendar_values:
        limitations[0] = ("ForexFactory schedule, forecast and previous are retrospective source values assumed known before prediction; "
                          "historical vintages/revisions unverified. Actual/revision/result annotations excluded.")
    report = {"status": "PARTIAL_NOT_FULL_LIVE", "requested_days": len(enriched),
              "funding_days": sum(r["funding_present"] for r in coverage),
              "global_ratio_5m_days": sum(r["global_ratio_5m_present"] for r in coverage),
              "forex_point_in_time_days": 0, "eligible_full_live_days": 0,
              "forex_schedule_days": sum(r["forex_schedule_present"] for r in coverage),
              "forex_schedule_nonempty_days": sum(bool(s["historical_extras"]["forex_calendar"]
                  and s["historical_extras"]["forex_calendar"]["events"]) for s in enriched),
              "retrospective_high_medium_all_currencies": len(relevant),
              "retrospective_high_medium_usd": sum(e["currency"] == "USD" for e in relevant),
              "forex_archive_lookup_attempts": len(forex_probe),
              "forex_archive_lookup_failures": sum(p["status"] == "lookup_failed" for p in forex_probe),
              "funding_api_crosscheck": funding_check, "download_errors": derivatives["errors"],
              "limitations": limitations}
    if args.calendar_schedule:
        selected_events = [e for s in enriched for e in
                           (s["historical_extras"]["forex_calendar"] or {}).get("events", [])]
        report.update({"calendar_mode": request["calendar_mode"], "calendar_event_entries": len(selected_events)})
        if args.calendar_values:
            report.update({f"{field}_nonempty_entries": sum(bool(e[field].strip()) for e in selected_events)
                           for field in ("forecast", "previous")})
    write_json(root/"derivatives_source.json", derivatives)
    write_json(root/"forex_vintage_probe.json", forex_probe)
    write_json(root/"source_coverage.json", coverage)
    write_json(root/"quality_report.json", report)
    lines = ["# Kiểm tra bổ sung nguồn lịch sử", "", "**Trạng thái: CHƯA ĐỦ BẢN LIVE.**", "",
             f"Khoảng dự báo: {config['start']} → {config['end']}; {len(enriched)} ngày.", "",
             "| Nguồn bổ sung | Số ngày có dữ liệu |", "| --- | ---: |",
             f"| Funding đã chốt | {report['funding_days']} |",
             f"| Global long/short từ kho 5 phút | {report['global_ratio_5m_days']} |",
             f"| Lịch sự kiện ForexFactory, theo giả định đã thông báo trước | {report['forex_schedule_days']} |",
             "| ForexFactory có vintage được xác minh | 0 |", "| Đủ tương đương live | 0 |", "",
             "Không thay ô thiếu bằng 0, không dùng top-trader ratio thay global ratio.",
             ("Có Forecast/Previous nguyên văn từ nguồn (giả định đã biết trước dự báo); "
              "không đưa Actual, Revision hoặc cờ kết quả công bố vào prompt." if args.calendar_values else
              "Không đưa Actual/Forecast/Previous từ lịch tải hồi cứu vào prompt."),
             "Chế độ lịch lấy tên, giờ, đồng tiền, mức ảnh hưởng, thêm Forecast/Previous nếu bật --calendar-values; "
             "chọn tối đa 10 sự kiện sắp tới trong tuần UTC. Ngày không có sự kiện khác với nguồn bị thiếu.",
             f"Trong {report['forex_schedule_days']} ngày có lịch, {report['forex_schedule_nonempty_days']} ngày "
             "có ít nhất một sự kiện sắp tới được chọn. Các feature đếm sự kiện tính trong tối đa 10 sự kiện đưa vào prompt.",
             "Lịch live lấy High/Medium của mọi đồng tiền, tối đa 10 sự kiện sắp tới; không chỉ USD.", "",
             f"ForexFactory hồi cứu: {len(relevant)} sự kiện High/Medium mọi đồng tiền; "
             f"{report['retrospective_high_medium_usd']} sự kiện USD trong khoảng dự báo.",
             f"Tìm vintage: {len(forex_probe)} truy vấn; {report['forex_archive_lookup_failures']} truy vấn lỗi. "
             "Đây là tìm kiếm giới hạn, không chứng minh mọi kho lưu trữ đều không có dữ liệu.", "",
             "## Kiểm tra nguồn", "",
             "- File ZIP đối chiếu SHA-256 với .CHECKSUM của Binance trước khi đọc CSV.",
             f"- Funding đối chiếu API: {json.dumps(funding_check, ensure_ascii=False)}.",
             "- Chỉ chọn available_at < prediction_time; không làm tròn timestamp funding về 00:00.",
             "- Ratio trễ giả định 5 phút, tối đa 24 giờ tuổi; funding tối đa 12 giờ tuổi.",
             "- Bộ gốc, nhãn và phân chia tập được giữ nguyên; bộ bổ sung có manifest riêng.", "",
             "## Giới hạn còn lại", "", *["- "+item for item in limitations], "",
             "## Dựng lại offline", "", "```sh",
             f".venv/bin/python -m scripts.enrich_historical_dataset --base {args.base} --output {root} --offline"
             + (" --calendar-values" if args.calendar_values else " --calendar-schedule" if args.calendar_schedule else ""), "```", "",
             "`source_coverage.json`: thiếu gì theo ngày; `derivatives_source.json`: giá trị và nguồn từng điểm;",
             "`forex_vintage_probe.json`: kết quả tìm bản lưu, không phải dữ liệu được duyệt vào prompt."]
    (root/"VERIFY.md").write_text("\n".join(lines)+"\n")
    artifacts = ["enrichment_request.json", "features.csv", "labels.csv", "splits.csv", "snapshots.jsonl",
                 "forex_events_RETROSPECTIVE_ONLY.json", "derivatives_source.json", "forex_vintage_probe.json",
                 "source_coverage.json", "quality_report.json", "VERIFY.md"]
    if args.calendar_schedule:
        artifacts.append("forex_schedule.jsonl")
    code_paths = ["data_sources/historical_data.py", "data_sources/historical_derivatives.py",
                  "scripts/enrich_historical_dataset.py", "utils/historical_calendar.py"]
    write_json(root/"dataset_manifest.json", {"version": 2, "config": config,
               "base_dataset": str(args.base), "base_manifest_sha256": request["base_manifest_sha256"],
               "artifacts_sha256": {name: digest(root/name) for name in artifacts},
               "raw_responses": archive.records, "limitations": limitations,
               "code_sha256": {name: digest(Path(name)) for name in code_paths}})
    print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
