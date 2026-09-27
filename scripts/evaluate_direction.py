"""Run real specialist → validator/debate → mediator on historical snapshots.

python -m scripts.evaluate_direction --output outputs/direction_pilot
No labels are loaded until all prediction attempts finish. No live market fetches.
"""
import argparse
import concurrent.futures
import csv
import datetime as dt
import hashlib
import json
import math
import os
import threading
import time
import shutil
from pathlib import Path

import numpy as np
import openai
from openai.types.chat import ChatCompletion

from agents import financial_agent, market_agent, sentiment_agent
from agents.validator_agent import ValidatorAgent
from agents.mediator_agent import run_mediator
from utils import llm
from utils.config import get_agent_config
from data_sources.market_data import _ema, _rsi
from utils.thresholds import DEFAULT_CONFLICT_THRESHOLD, SIGNAL_NEUTRAL_BAND
from utils.historical_calendar import ASSUMPTIONS as CALENDAR_ASSUMPTIONS, validated_schedule
from utils.failures import COMPLETED_STATUSES, describe_failure, explanation_status

DAY_BUDGET_SECONDS = 300


def save(path, data):
    """Write via a temporary file so an interrupted run never leaves half a JSON."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+"\n")
    os.replace(tmp, path)


def load_cached_completion(response):
    """Adapt Groq metadata without changing the archived provider response.

    Groq's on_demand service tier is not an OpenAI tier. Do not relabel it as
    default or skip validation of the actual completion content.
    """
    payload = dict(response)
    if payload.get("service_tier") == "on_demand":
        payload.pop("service_tier")
    return ChatCompletion.model_validate(payload)


def historical_extra(snap, name):
    """Validate supplemental source time/value again at the model-input boundary."""
    point = snap.get("historical_extras", {}).get(name)
    if point is None:
        return None
    value = float(point["value"])
    observed = dt.datetime.fromisoformat(point["observed_at"])
    available = dt.datetime.fromisoformat(point["available_at"])
    prediction = dt.datetime.fromisoformat(snap["prediction_time"])
    max_age = 12 if name == "funding_rate" else 24
    if (not math.isfinite(value) or (name == "long_short_ratio" and value <= 0)
            or not observed <= available < prediction
            or (prediction-observed).total_seconds() > max_age*3600):
        raise ValueError(f"Invalid/future/stale historical {name}")
    return {key: point[key] for key in ("value", "observed_at", "available_at", "source_url",
                                       "semantics", "availability_assumption", "period") if key in point}


def require_full_live(snapshots):
    """Fail before any paid LLM calls; missing sources must not disappear as dropped days."""
    missing = [s["sample_id"] for s in snapshots if not s.get("eligible_full_live", False)]
    if missing:
        raise ValueError(f"Dataset is not full-live equivalent on {len(missing)} days; "
                         "inspect source_coverage.json/VERIFY.md. No evaluation started.")


def adapter(snap):
    """Use only snapshot fields, with explicit unavailable-source markers."""
    validate_snapshot_input(snap)
    evidence, f = snap["evidence"], snap["features"]
    metrics = {}
    for name in ("hash-rate", "miners-revenue", "n-transactions", "estimated-transaction-volume-usd"):
        point = evidence[name]
        change = f[name.replace("-", "_")+"_change_1d"]
        if point is None or change is None:
            raise ValueError("Missing required on-chain observation/change")
        metrics[name] = {"value": point["value"], "pct_change_1d": change*100,
                         "observed_at": point["observed_at"]}
    chain = {"metrics": metrics, "fetched_at": min(evidence[k]["observed_at"] for k in metrics)}
    chain["summary_text"] = "Historical on-chain observations; MVRV, SOPR and whale flows unavailable.\n"+json.dumps(metrics)
    closes = np.array([c["close"] for c in snap["market_window"]["candles"][-60:]])
    market = {"price": float(closes[-1]), "ema20": _ema(closes, 20), "ema50": _ema(closes, 50),
              "rsi14": _rsi(closes, 14), "volume": f["volume"],
              "funding_rate": None, "long_short_ratio": None,
              "fetched_at": snap["prediction_time"]}
    market["summary_text"] = "Historical closed daily candles; funding rate and long/short ratio unavailable.\n"+json.dumps(market)
    if "historical_extras" in snap:
        market.pop("summary_text")
        source_notes = {}
        for name in ("funding_rate", "long_short_ratio"):
            point = historical_extra(snap, name)
            market[name] = point["value"] if point else None
            source_notes[name] = point if point else "Unavailable; do not infer a value."
        market["source_notes"] = source_notes
        market["summary_text"] = ("Historical closed daily candles with partial derivatives data. "
                                  "Read per-source timestamps and semantics; null means unavailable.\n"
                                  + json.dumps(market))
    point = evidence["fear_greed"]
    if point is None:
        raise ValueError("Missing Fear & Greed")
    sentiment = {"fear_greed": {"value": point["value"]}, "fetched_at": point["observed_at"]}
    sentiment["summary_text"] = "Historical Fear & Greed Index (0=extreme fear, 100=extreme greed): " + str(point["value"]) + ". ForexFactory calendar and news unavailable; do not invent events."
    calendar = snap.get("historical_extras", {}).get("forex_calendar")
    if calendar is not None:
        upcoming = validated_schedule(calendar, dt.datetime.fromisoformat(snap["prediction_time"]))
        sentiment["upcoming_events"] = upcoming
        sentiment["calendar_mode"] = calendar["mode"]
        sentiment["summary_text"] = (
            f"Historical Fear & Greed Index: {point['value']}/100.\n"
            f"ForexFactory upcoming events. {CALENDAR_ASSUMPTIONS[calendar['mode']]}\n"
            "Discuss pre-release expectations and uncertainty using supplied fields only; "
            "do not treat forecast/previous as actual results or invent surprises/outcomes.\n"
            + (json.dumps(upcoming, ensure_ascii=False) if upcoming else
               "No upcoming High/Medium events with a known time in the selected UTC week. "
               "This does not mean the calendar source is missing."))
    return chain, market, sentiment


def validate_snapshot_input(snap):
    """Reject corrupt/future core inputs before sending any payload to an LLM."""
    def number(value, name, minimum=None):
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError(f"Nonfinite/non-numeric snapshot {name}")
        if minimum is not None and value < minimum:
            raise ValueError(f"Invalid snapshot {name}")
        return value

    t = dt.datetime.fromisoformat(snap["prediction_time"])
    if t.tzinfo is None or t.utcoffset() != dt.timedelta(0) or any((t.hour, t.minute, t.second, t.microsecond)):
        raise ValueError("Historical prediction must be at UTC midnight")
    if snap["horizon_hours"] != 24:
        raise ValueError("Historical adapter requires 24h horizon")
    candles = snap["market_window"]["candles"]
    if len(candles) < 60:
        raise ValueError("Historical adapter needs at least 60 closed candles")
    previous = None
    for candle in candles:
        opened = dt.datetime.fromisoformat(candle["open_time"])
        if opened.tzinfo is None or opened + dt.timedelta(days=1) > t:
            raise ValueError("Future/unclosed historical candle")
        if previous is not None and opened - previous != dt.timedelta(days=1):
            raise ValueError("Historical candles must be continuous daily observations")
        previous = opened
        for field in ("open", "high", "low", "close"):
            if number(candle[field], field) <= 0:
                raise ValueError("Historical prices must be positive")
        number(candle["volume"], "volume", 0)
        if not candle["low"] <= min(candle["open"], candle["close"]) <= max(candle["open"], candle["close"]) <= candle["high"]:
            raise ValueError("Invalid historical OHLC range")
    if previous + dt.timedelta(days=1) != t:
        raise ValueError("Missing last closed day before prediction")
    f = snap["features"]
    if number(f["close"], "feature close") != candles[-1]["close"]:
        raise ValueError("Feature price differs from last closed candle")
    if number(f["volume"], "feature volume", 0) != candles[-1]["volume"]:
        raise ValueError("Feature volume differs from last closed candle")
    for name in ("hash-rate", "miners-revenue", "n-transactions", "estimated-transaction-volume-usd", "fear_greed"):
        point = snap["evidence"].get(name)
        if point is None:
            raise ValueError(f"Missing required source {name}")
        observed = dt.datetime.fromisoformat(point["observed_at"])
        available = dt.datetime.fromisoformat(point["available_at"])
        if observed.tzinfo is None or available.tzinfo is None or not observed <= available <= t:
            raise ValueError(f"Future/invalid source timestamps: {name}")
        value = number(point["value"], name, 0)
        if name == "fear_greed":
            if value > 100:
                raise ValueError("Fear & Greed must be within 0..100")
        else:
            number(f[name.replace("-", "_") + "_change_1d"], name + " change")


def score(predictions, labels):
    truth = {r["sample_id"]: r for r in labels}
    rows = []
    for p in predictions:
        row = {"sample_id": p["sample_id"], "status": p["status"],
               "signal": p.get("signal", ""), "S_final": p.get("S_final", ""),
               "return_24h": float(truth[p["sample_id"]]["return_24h"]), "correct_direction": ""}
        if row["status"] == "ok" and row["signal"] in ("BUY", "SELL"):
            row["correct_direction"] = (row["return_24h"] > 0 if row["signal"] == "BUY" else row["return_24h"] < 0)
        rows.append(row)
    directional = [r for r in rows if r["correct_direction"] != ""]
    successful = [r for r in rows if r["status"] == "ok"]
    correct = sum(r["correct_direction"] for r in directional)
    summary = {"requested_days": len(rows), "successful_days": len(successful),
               "failed_or_not_run_days": len(rows)-len(successful),
               "directional_predictions": len(directional), "correct": correct,
               "directional_win_rate": correct/len(directional) if directional else None,
               "neutral_days": sum(r["signal"] == "NEUTRAL" for r in successful),
               "coverage_over_requested": len(directional)/len(rows) if rows else None,
               "coverage_over_successful": len(directional)/len(successful) if successful else None,
               "status_counts": {status: sum(r["status"] == status for r in rows)
                                 for status in dict.fromkeys(r["status"] for r in rows)}}
    for signal in ("BUY", "SELL"):
        group = [r for r in directional if r["signal"] == signal]
        summary[signal] = {"count": len(group), "correct": sum(r["correct_direction"] for r in group),
                           "accuracy": sum(r["correct_direction"] for r in group)/len(group) if group else None}
    return summary, rows


def select_snapshots(snapshots, sample_ids=None):
    """Select input-only smoke cases, preserving dataset chronological order."""
    if not snapshots:
        raise ValueError("Dataset has no snapshots")
    if sample_ids is None:
        return snapshots
    requested = set(sample_ids)
    if not requested or len(requested) != len(sample_ids):
        raise ValueError("Sample IDs must be nonempty and unique")
    missing = requested - {s["sample_id"] for s in snapshots}
    if missing:
        raise ValueError(f"Unknown sample IDs: {sorted(missing)}")
    return [s for s in snapshots if s["sample_id"] in requested]


def run_day(snap, day_budget, conflict_threshold=DEFAULT_CONFLICT_THRESHOLD):
    """Predict one day; every failure becomes an explicit status, never a signal."""
    sample = snap["sample_id"]
    result = {"sample_id": sample, "status": "error", "errors": []}
    try:
        data = adapter(snap)
    except (ValueError, KeyError, TypeError) as exc:
        result.update(status="data_error", reason=type(exc).__name__)
        result["errors"].append({"stage": "adapter", "status": "data_error", "message": str(exc)[:500]})
        return result
    result["inputs"] = {name: payload for name, payload in zip(("financial", "market", "sentiment"), data)}
    ref = dt.datetime.fromisoformat(snap["prediction_time"])
    llm.set_deadline(day_budget)
    try:
        outputs = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(module.run, payload, ref) for module, payload in zip((financial_agent, market_agent, sentiment_agent), data)]
            for agent_name, future in zip(("financial", "market", "sentiment"), futures):
                try:
                    outputs.append(future.result())
                except Exception as exc:
                    result["errors"].append(describe_failure(exc, stage="specialist", agent=agent_name))
        result["specialists"] = outputs
        if result["errors"]:
            # Agent order decides which failure blocks the day; all are kept in errors[].
            first = result["errors"][0]
            result.update(status=first["status"], reason=first["reason"])
            return result
        try:
            validation = ValidatorAgent(threshold=conflict_threshold).evaluate_pipeline(outputs)
        except Exception as exc:
            failure = describe_failure(exc, stage="validator")
            result["errors"].append(failure)
            result.update(status=failure["status"], reason=failure["reason"])
            return result
        result["validation"] = validation
        if not validation.get("explanations_valid", True):
            status, reason = explanation_status(validation)
            result["errors"].append({"stage": "validator", "status": status, "reason": reason})
            result.update(status=status, reason=reason)
            return result
        final = validation.get("debate_updated_outputs") or outputs
        mediated = run_mediator(final, current_time=ref)
        value = mediated["S_final"]
        result.update({"mediator": mediated, "S_final": value, "status": "ok", "reason": None,
                       "signal": "BUY" if value > SIGNAL_NEUTRAL_BAND else "SELL" if value < -SIGNAL_NEUTRAL_BAND else "NEUTRAL"})
        return result
    finally:
        llm.set_deadline(None)


def fatal_api_error(result):
    """quota/config failures stop further calls; retrying the next day cannot help."""
    for error in result.get("errors", []):
        if error.get("status") == "api_error" and error.get("reason") in llm.FATAL_API_ERRORS:
            return error["reason"]
    return None


def needs_run(result, retry_rejected):
    if result is None:
        return True
    if result["status"] == "rejected_by_reviewer":
        return retry_rejected
    return result["status"] not in COMPLETED_STATUSES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/datasets/pilot_2022_01"))
    parser.add_argument("--output", type=Path, default=Path("outputs/direction_pilot"))
    parser.add_argument("--require-full-live", action="store_true",
                        help="Reject any dataset day not verified as equivalent to all live inputs")
    parser.add_argument("--sample-ids", nargs="+", help="Run only these dataset dates (YYYY-MM-DD), e.g. a 5-day smoke test")
    parser.add_argument("--reuse-calls-from", type=Path, nargs="+", default=[],
                        help="calls/ directories whose successful responses are reused when model, endpoint and request hash match")
    parser.add_argument("--conflict-threshold", type=float, default=DEFAULT_CONFLICT_THRESHOLD,
                        help="Validator conflict score that triggers RCA/Debate (sensitivity analyses only)")
    parser.add_argument("--day-budget", type=float, default=DAY_BUDGET_SECONDS,
                        help="Wall-clock seconds per day, including retries and Debate")
    parser.add_argument("--retry-rejected", action="store_true",
                        help="Also rerun days rejected by the reviewer, bypassing cached responses")
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    (root/"days").mkdir(exist_ok=True)
    (root/"calls").mkdir(exist_ok=True)
    for source in args.reuse_calls_from:
        for cached in source.glob("*.json"):
            record = json.loads(cached.read_text())
            target = root/"calls"/cached.name
            if record.get("status") == "ok" and not target.exists():
                shutil.copyfile(cached, target)
    raw = (args.dataset/"snapshots.jsonl").read_bytes()
    snapshots = [json.loads(line) for line in raw.decode().splitlines()]
    manifest = json.loads((args.dataset/"dataset_manifest.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == manifest["artifacts_sha256"]["snapshots.jsonl"]
    snapshots = select_snapshots(snapshots, args.sample_ids)
    if args.require_full_live:
        require_full_live(snapshots)
    configs = {a: get_agent_config(a) for a in ("financial", "market", "sentiment", "validator", "debate", "grounding")}
    files = [Path(__file__), *Path("agents").glob("*.py"), Path("utils/prompts.py"), Path("utils/thresholds.py"), Path("utils/penalties.py"),
             Path("utils/grounding.py"), Path("utils/specialist_response.py"), Path("utils/llm.py"), Path("utils/parsing.py"),
             Path("utils/failures.py"), Path("utils/historical_calendar.py"), Path("utils/config.py")]
    run_config = {"snapshots_sha256": hashlib.sha256(raw).hexdigest(), "models": configs,
                  "code_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                  "limitations": manifest.get("limitations", ["30-day train pilot, not held-out test", "Forex, funding and long/short unavailable",
                                  "Historical LLM knowledge contamination possible", "On-chain/F&G publication lags assumed"]),
                  "require_full_live": args.require_full_live,
                  "sample_ids": [s["sample_id"] for s in snapshots],
                  "selection": "explicit input smoke cases; not a contiguous financial backtest" if args.sample_ids else "all dataset dates",
                  "horizon_hours": 24, "signal_threshold": SIGNAL_NEUTRAL_BAND, "day_budget_seconds": args.day_budget,
                  "conflict_threshold": args.conflict_threshold,
                  "market_window": "60 candles as in live fetcher", "weights_reference": "prediction_time; source observation timestamps"}
    if (root/"run_config.json").exists():
        if json.loads((root/"run_config.json").read_text()) != run_config:
            raise ValueError("Different code/config: use a new output directory")
    else:
        save(root/"run_config.json", run_config)
    lock = threading.Lock()
    call_errors = []
    send = llm._send
    state = {"bypass_cache": False}

    def logged_send(client, **kwargs):
        path = root/"calls"/(llm.request_key(client.base_url, kwargs)+".json")
        if path.exists() and not state["bypass_cache"]:
            cached = json.loads(path.read_text())
            if cached.get("status") == "ok":
                return load_cached_completion(cached["response"])
        start = time.monotonic()
        record = {"model": kwargs["model"], "messages": kwargs["messages"], "created_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            response = send(client, **kwargs)
            record.update({"response": response.model_dump(), "status": "ok"})
            return response
        except Exception as exc:
            # Persist useful status without exposing credentials or full request headers.
            error = {"type": type(exc).__name__, "status_code": getattr(exc, "status_code", None),
                     "kind": llm.classify_api_error(exc) if isinstance(exc, openai.APIError) else None,
                     "provider_message": llm.provider_message(exc), "model": kwargs["model"]}
            record.update({"status": "error", "error": error})
            with lock:
                call_errors.append(error)
            raise
        finally:
            record["elapsed_seconds"] = time.monotonic()-start
            save(path, record)

    def mark_rejected(key, reason):
        """Unusable content (empty/truncated/invalid JSON) must never be replayed."""
        path = root/"calls"/(key+".json")
        with lock:
            if path.exists():
                record = json.loads(path.read_text())
                if record.get("status") == "ok":
                    record.update(status="rejected_content", rejected_reason=reason[:500])
                    save(path, record)

    # Retain actual ask_llm routing/prompts and retry policy; only the provider
    # call is audited/cached.
    llm._send = logged_send
    llm._on_rejected = mark_rejected
    predictions = []
    stop_reason = None
    for index, snap in enumerate(snapshots):
        sample = snap["sample_id"]
        path = root/"days"/(sample+".json")
        previous = json.loads(path.read_text()) if path.exists() else None
        if not needs_run(previous, args.retry_rejected):
            predictions.append(previous)
            continue
        if stop_reason:
            result = {"sample_id": sample, "status": f"not_run_{stop_reason}", "reason": stop_reason}
            save(path, result)
            predictions.append(result)
            continue
        print(f"[{index+1}/{len(snapshots)}] {sample}", flush=True)
        state["bypass_cache"] = bool(previous and previous["status"] == "rejected_by_reviewer")
        error_start = len(call_errors)
        started = time.monotonic()
        result = run_day(snap, args.day_budget, args.conflict_threshold)
        result["elapsed_seconds"] = round(time.monotonic()-started, 1)
        result["llm_call_errors"] = call_errors[error_start:]
        if previous:
            result["previous_status"] = previous["status"]
        save(path, result)
        predictions.append(result)
        stop_reason = fatal_api_error(result)
        print(f"  {result['status']} {result.get('reason') or ''} {result.get('signal', '')} "
              f"({result['elapsed_seconds']}s, {len(result['llm_call_errors'])} failed calls)", flush=True)
        if stop_reason:
            print(f"  Stopping LLM calls: {stop_reason}. Rerun the same command later to resume.", flush=True)
    # Ground truth opened ONLY AFTER the prediction loop.
    label_bytes = (args.dataset/"labels.csv").read_bytes()
    assert hashlib.sha256(label_bytes).hexdigest() == manifest["artifacts_sha256"]["labels.csv"]
    labels = list(csv.DictReader(label_bytes.decode().splitlines()))
    summary, rows = score(predictions, labels)
    save(root/"summary.json", summary)
    reasons = {p["sample_id"]: p.get("reason") or "" for p in predictions}
    for row in rows:
        row["reason"] = reasons[row["sample_id"]]
    tmp = root/"predictions.csv.tmp"
    with tmp.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp, root/"predictions.csv")
    report = ["# Kết quả thử hướng giá BTC 24 giờ", "", "Win rate ở đây là directional accuracy, không phải lợi nhuận giao dịch.",
              "", "```json", json.dumps(summary, indent=2), "```", "",
              "| Ngày | Trạng thái | Nguyên nhân | Tín hiệu |", "|---|---|---|---|"]
    report.extend(f"| {r['sample_id']} | {r['status']} | {r['reason']} | {r['signal']} |" for r in rows)
    report.extend(["", "Giới hạn:"])
    report.extend("- "+v for v in run_config["limitations"])
    if args.sample_ids:
        report.append("- Các ngày chọn trước theo đặc điểm đầu vào để kiểm tra pipeline; không phải mẫu ngẫu nhiên hay backtest tài chính liên tục.")
    report.append("- Chỉ chấm ngày có status ok (đủ 3 specialist, RCA/Debate đạt kiểm tra); NEUTRAL không tính vào mẫu số win rate.")
    tmp = root/"REPORT.md.tmp"
    tmp.write_text("\n".join(report)+"\n")
    os.replace(tmp, root/"REPORT.md")
    print(json.dumps(summary, indent=2), flush=True)

if __name__ == "__main__":
    main()
