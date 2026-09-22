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
import threading
import time
import shutil
from pathlib import Path

import numpy as np
from openai import RateLimitError
from openai.types.chat import ChatCompletion

from agents import financial_agent, market_agent, sentiment_agent
from agents.validator_agent import ValidatorAgent
from agents.mediator_agent import run_mediator
from utils import llm
from utils.config import get_agent_config
from data_sources.market_data import _ema, _rsi
from utils.thresholds import SIGNAL_NEUTRAL_BAND


def save(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False)+"\n")


def adapter(snap):
    """Use only snapshot fields, with explicit unavailable-source markers."""
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
    point = evidence["fear_greed"]
    if point is None:
        raise ValueError("Missing Fear & Greed")
    sentiment = {"fear_greed": {"value": point["value"]}, "fetched_at": point["observed_at"]}
    sentiment["summary_text"] = "Historical Fear & Greed Index (0=extreme fear, 100=extreme greed): " + str(point["value"]) + ". ForexFactory calendar and news unavailable; do not invent events."
    return chain, market, sentiment


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
               "coverage_over_successful": len(directional)/len(successful) if successful else None}
    for signal in ("BUY", "SELL"):
        group = [r for r in directional if r["signal"] == signal]
        summary[signal] = {"count": len(group), "correct": sum(r["correct_direction"] for r in group),
                           "accuracy": sum(r["correct_direction"] for r in group)/len(group) if group else None}
    return summary, rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=Path("data/datasets/pilot_2022_01"))
    parser.add_argument("--output", type=Path, default=Path("outputs/direction_pilot"))
    parser.add_argument("--reuse-calls-from", type=Path, help="Reuse successful responses with exactly matching model, endpoint and request hash")
    args = parser.parse_args()
    root = args.output
    root.mkdir(parents=True, exist_ok=True)
    (root/"days").mkdir(exist_ok=True)
    (root/"calls").mkdir(exist_ok=True)
    if args.reuse_calls_from:
        for cached in args.reuse_calls_from.glob("*.json"):
            record = json.loads(cached.read_text())
            target = root/"calls"/cached.name
            if record.get("status") == "ok" and not target.exists():
                shutil.copyfile(cached, target)
    raw = (args.dataset/"snapshots.jsonl").read_bytes()
    snapshots = [json.loads(line) for line in raw.decode().splitlines()]
    manifest = json.loads((args.dataset/"dataset_manifest.json").read_text())
    assert hashlib.sha256(raw).hexdigest() == manifest["artifacts_sha256"]["snapshots.jsonl"]
    configs = {a: get_agent_config(a) for a in ("financial", "market", "sentiment", "validator", "debate", "grounding")}
    files = [Path(__file__), *Path("agents").glob("*.py"), Path("utils/prompts.py"), Path("utils/thresholds.py"), Path("utils/penalties.py"),
             Path("utils/grounding.py"), Path("utils/specialist_response.py"), Path("utils/llm.py")]
    run_config = {"snapshots_sha256": hashlib.sha256(raw).hexdigest(), "models": configs,
                  "code_sha256": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
                  "limitations": ["30-day train pilot, not held-out test", "Forex, funding and long/short unavailable",
                                  "Historical LLM knowledge contamination possible", "On-chain/F&G publication lags assumed"],
                  "horizon_hours": 24, "signal_threshold": SIGNAL_NEUTRAL_BAND,
                  "market_window": "60 candles as in live fetcher", "weights_reference": "prediction_time; source observation timestamps"}
    if (root/"run_config.json").exists():
        if json.loads((root/"run_config.json").read_text()) != run_config:
            raise ValueError("Different code/config: use a new output directory")
    else:
        save(root/"run_config.json", run_config)
    lock = threading.Lock()
    call_errors = []
    def logged_completion(client, **kwargs):
        digest = hashlib.sha256(json.dumps({"base_url": str(client.base_url), **kwargs}, sort_keys=True).encode()).hexdigest()
        path = root/"calls"/(digest+".json")
        if path.exists():
            cached = json.loads(path.read_text())
            if cached.get("status") == "ok":
                return ChatCompletion.model_validate(cached["response"])
        start = time.monotonic()
        record = {"model": kwargs["model"], "messages": kwargs["messages"], "created_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        try:
            for attempt in range(3):
                try:
                    response = client.with_options(timeout=60, max_retries=0).chat.completions.create(**kwargs)
                    break
                except RateLimitError:
                    if attempt == 2:
                        raise
                    print(f"  Rate limit {kwargs['model']}; retry after {20*(attempt+1)} seconds", flush=True)
                    time.sleep(20*(attempt+1))
            record.update({"response": response.model_dump(), "status": "ok"})
            return response
        except Exception as exc:
            # Persist useful status without exposing credentials or full request headers.
            error = {"type": type(exc).__name__, "status_code": getattr(exc, "status_code", None)}
            body = getattr(exc, "body", None)
            if isinstance(body, dict):
                error["provider_message"] = str(body.get("message", body.get("error", "")))[:500]
            record.update({"status": "error", "error": error})
            with lock:
                call_errors.append(error)
            raise
        finally:
            record["elapsed_seconds"] = time.monotonic()-start
            save(path, record)
    # Retain actual ask_llm routing/prompts, with bounded requests and persisted audit.
    llm._create_completion = logged_completion
    predictions = []
    consecutive_failures = 0
    for index, snap in enumerate(snapshots):
        sample = snap["sample_id"]
        path = root/"days"/(sample+".json")
        if path.exists():
            result = json.loads(path.read_text())
            predictions.append(result)
            continue
        if consecutive_failures >= 2:
            predictions.append({"sample_id": sample, "status": "not_run_provider_failures"})
            continue
        print(f"[{index+1}/{len(snapshots)}] {sample}", flush=True)
        result = {"sample_id": sample, "status": "error"}
        error_start = len(call_errors)
        try:
            data = adapter(snap)
            ref = dt.datetime.fromisoformat(snap["prediction_time"])
            outputs = []
            errors = []
            with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
                futures = [pool.submit(module.run, payload, ref) for module, payload in zip((financial_agent, market_agent, sentiment_agent), data)]
                for future in futures:
                    try:
                        out = future.result()
                        assert out["signal"] in ("BUY", "SELL", "NEUTRAL")
                        assert math.isfinite(out["confidence"]) and 0 <= out["confidence"] <= 1
                        outputs.append(out)
                    except Exception as exc:
                        errors.append(type(exc).__name__)
            result["specialists"] = outputs
            if errors:
                result["agent_errors"] = errors
                raise ValueError("Incomplete specialists; excluded from win rate")
            validation = ValidatorAgent().evaluate_pipeline(outputs)
            result["validation"] = validation
            if not validation.get("explanations_valid", True):
                raise ValueError("RCA/Debate grounding failed; excluded from directional accuracy")
            final = validation.get("debate_updated_outputs") or outputs
            mediated = run_mediator(final, current_time=ref)
            value = mediated["S_final"]
            result.update({"validation": validation, "mediator": mediated, "S_final": value,
                           "signal": "BUY" if value > SIGNAL_NEUTRAL_BAND else "SELL" if value < -SIGNAL_NEUTRAL_BAND else "NEUTRAL",
                           "status": "ok" if len(call_errors) == error_start else "degraded_llm_error"})
        except Exception as exc:
            result["failure"] = type(exc).__name__
        result["llm_errors"] = call_errors[error_start:]
        save(path, result)
        predictions.append(result)
        consecutive_failures = 0 if result["status"] == "ok" else consecutive_failures+1
        print(f"  {result['status']} {result.get('signal','')} {result['llm_errors']}", flush=True)
    # Ground truth opened ONLY AFTER the prediction loop.
    label_bytes = (args.dataset/"labels.csv").read_bytes()
    assert hashlib.sha256(label_bytes).hexdigest() == manifest["artifacts_sha256"]["labels.csv"]
    labels = list(csv.DictReader(label_bytes.decode().splitlines()))
    summary, rows = score(predictions, labels)
    save(root/"summary.json", summary)
    with (root/"predictions.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    report = ["# Kết quả thử hướng giá BTC 24 giờ", "", "Win rate ở đây là directional accuracy, không phải lợi nhuận giao dịch.",
              "", "```json", json.dumps(summary, indent=2), "```", "", "Giới hạn:"]
    report.extend("- "+v for v in run_config["limitations"])
    report.append("- Chỉ chấm ngày đủ 3 specialist và không có lỗi LLM ở validator/debate; NEUTRAL không tính vào mẫu số win rate.")
    (root/"REPORT.md").write_text("\n".join(report)+"\n")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    main()
