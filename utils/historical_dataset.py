"""Deterministic daily BTC dataset builder. Targets never enter snapshots."""

import bisect
import csv
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from data_sources.historical_data import CHARTS, DAY, UTC, iso, midnight
from data_sources.market_data import _ema, _rsi


def _number(value, *, minimum=0):
    result = float(value)
    if not math.isfinite(result) or result < minimum:
        raise ValueError(f"Invalid numeric value: {value!r}")
    return result


def market_index(raw):
    result = {}
    for row in raw:
        opened = dt.datetime.fromtimestamp(int(row[0]) / 1000, UTC)
        if opened != midnight(opened.date().isoformat()):
            raise ValueError("Expected UTC daily candle")
        if int(row[6]) != int((opened + DAY).timestamp() * 1000) - 1:
            raise ValueError("Unexpected candle close time")
        values = [_number(row[i]) for i in range(1, 6)]
        o, h, low, close, volume = values
        if min(o, h, low, close) <= 0 or not low <= min(o, close) <= max(o, close) <= h:
            raise ValueError("Invalid OHLC relationship")
        if opened in result:
            raise ValueError(f"Duplicate candle: {iso(opened)}")
        result[opened] = {"open": o, "high": h, "low": low, "close": close, "volume": volume}
    return result


def daily_series(raw, kind, lag_days):
    """Keep original timestamp; an assumed availability is explicitly labelled."""
    result = []
    seen = set()
    for point in raw:
        timestamp = float(point["timestamp"] if kind == "fear_greed" else point["x"])
        observed = dt.datetime.fromtimestamp(timestamp, UTC)
        value = _number(point["value"] if kind == "fear_greed" else point["y"])
        if kind == "fear_greed" and value > 100:
            raise ValueError("Fear & Greed outside [0, 100]")
        if observed.date() in seen:
            raise ValueError(f"Multiple observations on one day: {kind} {observed.date()}")
        seen.add(observed.date())
        available = observed + dt.timedelta(days=lag_days)
        result.append({"observed_at": iso(observed), "available_at": iso(available),
                       "value": value, "availability_assumption": f"source timestamp + {lag_days} days; publication vintage unverified"})
    return sorted(result, key=lambda p: p["available_at"])


def asof(series, t, max_age_hours=72):
    index = bisect.bisect_right([p["available_at"] for p in series], iso(t)) - 1
    if index < 0:
        return None
    point = series[index]
    age = (t - dt.datetime.fromisoformat(point["available_at"])).total_seconds() / 3600
    if age > max_age_hours:
        return None
    return {**point, "age_hours": age}


def series_features(series, point, prefix):
    if point is None:
        return {f"{prefix}_{name}": None for name in ("value", "change_1d", "change_7d", "mean_7d", "age_hours")}
    by_time = {p["observed_at"]: p["value"] for p in series}
    observed = dt.datetime.fromisoformat(point["observed_at"])
    def change(days):
        previous = by_time.get(iso(observed - days * DAY))
        if previous is None:
            return None
        if prefix == "fear_greed":
            return point["value"] - previous
        return point["value"] / previous - 1 if previous else None
    window = [by_time.get(iso(observed - n * DAY)) for n in range(7)]
    return {f"{prefix}_value": point["value"], f"{prefix}_change_1d": change(1),
            f"{prefix}_change_7d": change(7),
            f"{prefix}_mean_7d": sum(window) / 7 if all(v is not None for v in window) else None,
            f"{prefix}_age_hours": point["age_hours"]}


def split_for(t):
    if t < midnight("2024-07-01"):
        return "train", t + DAY < midnight("2024-07-01")
    if t < midnight("2025-01-01"):
        return "validation", t + DAY < midnight("2025-01-01")
    return "test", True


def build(source, start, end, threshold=0.01, onchain_lag_days=2, fear_greed_lag_days=1):
    if start > end or threshold <= 0 or not math.isfinite(threshold):
        raise ValueError("Invalid dates or label threshold")
    if onchain_lag_days < 2 or fear_greed_lag_days < 1:
        raise ValueError("Default dataset requires on-chain lag >=2 days and Fear & Greed lag >=1 day")
    market = market_index(source["market"])
    series = {chart: daily_series(source["onchain"].get(chart, []), chart, onchain_lag_days) for chart in CHARTS}
    series["fear_greed"] = daily_series(source["fear_greed"], "fear_greed", fear_greed_lag_days)
    features, labels, snapshots, splits, audit = [], [], [], [], []
    t = start
    while t <= end:
        row_id = t.date().isoformat()
        # Exactly 90 contiguous closed daily candles. Never include candle opening at t.
        history = [market.get(t - n * DAY) for n in range(90, 0, -1)]
        if any(c is None for c in history) or t not in market:
            audit.append({"sample_id": row_id, "included": False, "reason": "missing_90_day_market_window_or_target"})
            t += DAY
            continue
        closes = np.array([c["close"] for c in history])
        volumes = np.array([c["volume"] for c in history])
        price = float(closes[-1])
        returns = np.diff(closes) / closes[:-1]
        row = {"sample_id": row_id, "prediction_time": iso(t), "close": price,
               "return_1d": float(closes[-1] / closes[-2] - 1),
               "return_7d": float(closes[-1] / closes[-8] - 1),
               "return_30d": float(closes[-1] / closes[-31] - 1),
               "ema20_gap": price / _ema(closes, 20) - 1,
               "ema50_gap": price / _ema(closes, 50) - 1,
               "rsi14": _rsi(closes, 14), "volatility_7d": float(np.std(returns[-7:], ddof=0)),
               "volatility_30d": float(np.std(returns[-30:], ddof=0)),
               "volume": float(volumes[-1]),
               "volume_change_1d": float(volumes[-1] / volumes[-2] - 1) if volumes[-2] else None}
        evidence = {}
        for name, points in series.items():
            point = asof(points, t)
            evidence[name] = point
            prefix = name.replace("-", "_")
            row.update(series_features(points, point, prefix))
            row[f"{prefix}_missing"] = int(point is None)
        eligible_core = all(p is not None for p in evidence.values())
        target_price = market[t]["close"]
        ret = target_price / price - 1
        # Compare prices at thresholds to avoid classifying equality as a breakout.
        label = "BUY" if target_price > price * (1 + threshold) else "SELL" if target_price < price * (1 - threshold) else "NEUTRAL"
        features.append(row)
        labels.append({"sample_id": row_id, "target_end": iso(t + DAY), "reference_price": price,
                       "future_price": target_price, "return_24h": ret, "label": label})
        split, eligible_split = split_for(t)
        splits.append({"sample_id": row_id, "split": split, "eligible_split": eligible_split,
                       "eligible_core": eligible_core, "eligible_full": False})
        snapshots.append({"sample_id": row_id, "prediction_time": iso(t), "horizon_hours": 24,
                          "features": row, "evidence": evidence,
                          "market_window": {"start": iso(t-90*DAY), "end_exclusive": iso(t),
                                            "candles": [{"open_time": iso(t-(90-i)*DAY), **c} for i, c in enumerate(history)]},
                          "unavailable": ["forex_point_in_time", "funding_rate", "long_short_ratio"],
                          "status": "historical_core_with_assumed_availability"})
        audit.append({"sample_id": row_id, "included": True, "eligible_core": eligible_core,
                      "missing_sources": [k for k, v in evidence.items() if v is None]})
        t += DAY
    return {"features": features, "labels": labels, "snapshots": snapshots, "splits": splits, "audit": audit}


def write_json(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def write_dataset(root, dataset, config, source, raw_records):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    for name in ("features", "labels", "splits"):
        rows = dataset[name]
        with (root / f"{name}.csv").open("w", newline="", encoding="utf-8") as stream:
            if rows:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
    with (root / "snapshots.jsonl").open("w", encoding="utf-8") as stream:
        for row in dataset["snapshots"]:
            stream.write(json.dumps(row, ensure_ascii=False, allow_nan=False) + "\n")
    write_json(root / "sample_audit.json", dataset["audit"])
    write_json(root / "forex_events_RETROSPECTIVE_ONLY.json", source.get("forex_events", []))
    # Explicitly separate review artifact WITH labels from agent inputs.
    review = [{"snapshot": snap, "ground_truth_FOR_REVIEW_ONLY": label}
              for snap, label in zip(dataset["snapshots"][:10], dataset["labels"][:10])]
    write_json(root / "review_10_samples_WITH_LABELS.json", review)
    eligible = {r["sample_id"] for r in dataset["splits"] if r["eligible_core"] and r["eligible_split"]}
    counts = {label: sum(r["label"] == label for r in dataset["labels"]) for label in ("BUY", "SELL", "NEUTRAL")}
    quality = {"requested_days": len(dataset["audit"]), "rows": len(dataset["features"]),
               "eligible_core_rows": len(eligible), "eligible_full_rows": 0,
               "complete_feature_rows": sum(all(v is not None for v in r.values()) for r in dataset["features"]),
               "forex_events_parsed": len(source.get("forex_events", [])),
               "forex_usd_high_medium_in_requested_range": sum(
                   e["currency"] == "USD" and e["impact"] in ("high", "medium")
                   and bool(e["event_time"]) and config["start"] <= e["event_time"][:10] <= config["end"]
                   for e in source.get("forex_events", [])),
               "label_counts": counts,
               "missing_cells": {key: sum(r[key] is None for r in dataset["features"]) for key in dataset["features"][0]} if dataset["features"] else {},
               "source_errors": source.get("errors", {}), "forex_audit": source.get("forex", []),
               "limitations": ["On-chain and Fear & Greed publication times are assumed, not verified historical vintages.",
                               "Forex fields excluded; this is NOT the full live pipeline dataset.",
                               "Funding and long/short ratio not included.",
                               "Historical LLM evaluation may contain knowledge from model pretraining.",
                               "Close-to-close prediction labels do not imply executable trading returns."]}
    write_json(root / "quality_report.json", quality)
    artifact_names = ("features.csv", "labels.csv", "splits.csv", "snapshots.jsonl", "sample_audit.json",
                      "review_10_samples_WITH_LABELS.json", "quality_report.json", "source_data.json",
                      "forex_events_RETROSPECTIVE_ONLY.json")
    checksums = {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in artifact_names if (root / name).exists()}
    code_root = Path(__file__).resolve().parents[1]
    code_names = ("utils/historical_dataset.py", "data_sources/historical_data.py", "scripts/build_dataset.py", "data_sources/market_data.py")
    manifest = {"version": 1, "config": config, "artifacts_sha256": checksums,
                "code_sha256": {name: hashlib.sha256((code_root / name).read_bytes()).hexdigest() for name in code_names},
                "raw_responses": raw_records, "sources": {
                    "market": "https://github.com/binance/binance-spot-api-docs/blob/master/rest-api.md",
                    "onchain": "https://www.blockchain.com/en/explorer/api/charts_api",
                    "fear_greed": "https://alternative.me/crypto/fear-and-greed-index/",
                    "forex": "https://www.forexfactory.com/calendar"}}
    write_json(root / "dataset_manifest.json", manifest)
    lines = ["# Kiểm tra dataset BTC lịch sử", "", f"Khoảng dự báo: {config['start']} → {config['end']} (00:00 UTC, 24 giờ).",
             f"Số ngày yêu cầu: {quality['requested_days']}; có nhãn: {quality['rows']}; đủ nguồn core và split hợp lệ: {len(eligible)}.",
             "", "**Chưa có mẫu đủ toàn bộ nguồn của live pipeline. ForexFactory bị loại khỏi features.**", "",
             f"Lịch ForexFactory: trích {quality['forex_events_parsed']} bản ghi; {quality['forex_usd_high_medium_in_requested_range']} sự kiện USD High/Medium trong khoảng yêu cầu.",
             "Xem `forex_events_RETROSPECTIVE_ONLY.json`: có Actual/Forecast/Previous, chỉ dùng kiểm tra lịch sử, không đưa vào prompt.",
             f"Số mẫu không thiếu bất kỳ feature nào: {quality['complete_feature_rows']}. Ô trống được giữ nguyên, không tự nội suy.", "",
             f"Phân bố nhãn: {counts}", "", "## Kiểm tra thủ công", "",
             "1. Mở `review_10_samples_WITH_LABELS.json`; đối chiếu 10 mẫu đầu với source_data.json và raw/.",
             "2. Kiểm tra available_at ≤ prediction_time; nến market đều đã đóng, không có nến mục tiêu trong snapshot.",
             "3. Tính lại future_price / reference_price - 1 và nhãn ±1% (hoặc ngưỡng trong manifest).",
             "4. Xem sample_audit.json, missing_cells và forex_audit trong quality_report.json.",
             "5. Không đưa file review hay labels vào prompt hoặc feature matrix.", "", "## Giới hạn", ""]
    lines.extend(f"- {item}" for item in quality["limitations"])
    lines.extend(["", "## 10 mẫu đầu để đối chiếu", "",
                  "| Ngày dự báo (00:00 UTC) | Giá tham chiếu | Giá sau 24h | Lợi suất | Nhãn | On-chain quan sát lúc | F&G quan sát lúc |",
                  "|---|---:|---:|---:|---|---|---|"])
    for snap, label in zip(dataset["snapshots"][:10], dataset["labels"][:10]):
        chain = snap["evidence"].get("hash-rate") or {}
        fear = snap["evidence"].get("fear_greed") or {}
        lines.append(f"| {snap['sample_id']} | {label['reference_price']:.2f} | {label['future_price']:.2f} | {label['return_24h']:.4%} | {label['label']} | {chain.get('observed_at', 'missing')} | {fear.get('observed_at', 'missing')} |")
    lines.extend(["", "## Lỗi nguồn", "", json.dumps(quality["source_errors"], ensure_ascii=False, indent=2), ""])
    (root / "VERIFY.md").write_text("\n".join(lines), encoding="utf-8")
    return quality
