"""Run our multi-agent system inside the CryptoTrade environment.

Same data, timing, trading rules and metrics as the baseline; only the agent
architecture differs. For trading day D (decision at D's open), as in the
CryptoTrade env, the agents see:
- Market: daily opens up to D's open, EMA20/50 and RSI14 of opens, and the
  three CryptoTrade signals (MA crossover, MACD, Bollinger) computed on D;
- Financial: the Dune transaction statistics of D-1 with day-over-day change;
- Sentiment: the news articles of D-1.
Every item is on its own line so Debate/RCA can cite it. Signals map to
actions BUY=+0.5, SELL=-0.5, NEUTRAL=0 (the paper's rule-baseline sizing).
When a Debate/RCA explanation is rejected the rolled-back decision is still
traded and the day is flagged (design decision Q7 = b). A day whose
specialists fail holds (action 0) and keeps its failure status.
Decisions do not depend on the portfolio, so each day is computed once,
saved, and the action series is replayed through TradingEnv at the end.
"""
import concurrent.futures
import copy
import datetime as dt
import json
import os
import re
import time
from pathlib import Path

import numpy as np

from agents import financial_agent, market_agent, sentiment_agent
from agents.conflict_analyzer import ConflictAnalyzer
from agents.mediator_agent import run_mediator
from baselines.cryptotrade.env import (
    DATA_DIR, TradingEnv, bollinger_signal, load_news, load_prices, load_txn_stats, macd_signal, sharpe,
    slma_signal,
)
from data_sources.market_data import _ema, _rsi
from utils import llm
from utils.failures import describe_failure, explanation_status
from utils.thresholds import DEFAULT_CONFLICT_THRESHOLD, SIGNAL_NEUTRAL_BAND

ACTION = {"BUY": 0.5, "SELL": -0.5, "NEUTRAL": 0.0}
AGENTS = (("financial", financial_agent), ("market", market_agent), ("sentiment", sentiment_agent))
SOURCES = {
    "market": "CryptoTrade dataset: CoinMarketCap BTC daily open prices",
    "financial": "CryptoTrade dataset: Dune BTC transaction statistics",
    "sentiment": "CryptoTrade dataset: Google News (Gnews) Bitcoin articles",
}


def _midnight(date):
    return dt.datetime.fromisoformat(date).replace(tzinfo=dt.timezone.utc)


def _one_line(text):
    return re.sub(r"\s+", " ", str(text)).strip()


def signal_of(s_final):
    if s_final > SIGNAL_NEUTRAL_BAND:
        return "BUY"
    if s_final < -SIGNAL_NEUTRAL_BAND:
        return "SELL"
    return "NEUTRAL"


def build_inputs(date, prices=None, txn_stats=None, data_dir=DATA_DIR):
    """Agent inputs for a decision at the open of `date` (YYYY-MM-DD)."""
    prices = prices or load_prices(data_dir)
    txn_stats = txn_stats or load_txn_stats(data_dir)
    index = next(i for i, d in enumerate(prices) if d["date"] == date)
    day = prices[index]
    opens = np.array([d["open"] for d in prices[max(0, index - 59): index + 1]])
    previous = (dt.date.fromisoformat(date) - dt.timedelta(days=1)).isoformat()
    before = (dt.date.fromisoformat(date) - dt.timedelta(days=2)).isoformat()

    signals = {"short_long_ma_signal": slma_signal(day), "macd_signal": macd_signal(day),
               "bollinger_bands_signal": bollinger_signal(day, day["open"])}
    rsi14 = _rsi(opens, 14)
    market_lines = [f"BTC daily open prices up to the decision time ({date} 00:00 UTC); newest last."]
    market_lines += [f"Open {d['date']}: {d['open']:.2f}" for d in prices[max(0, index - 6): index + 1]]
    market_lines += [f"EMA20 of daily opens: {_ema(opens, 20):.2f}", f"EMA50 of daily opens: {_ema(opens, 50):.2f}",
                     f"RSI14 of daily opens: {rsi14:.2f}"]
    market_lines += [f"{k}: {v}" for k, v in signals.items()]
    market = {"summary_text": "\n".join(market_lines), "price": day["open"], "rsi14": rsi14,
              "technical": signals, "fetched_at": _midnight(date).isoformat(), "source": SOURCES["market"]}

    today, prior = txn_stats.get(previous), txn_stats.get(before)
    if not today or not prior:
        raise ValueError(f"Missing transaction statistics for {previous} or {before}")
    metrics = {k: {"value": v, "pct_change_1d": (v / prior[k] - 1) * 100 if prior[k] else 0.0}
               for k, v in today.items()}
    financial_lines = [f"BTC on-chain transaction statistics for {previous} (full UTC day before the decision)."]
    financial_lines += [f"{k}: {m['value']} ({m['pct_change_1d']:+.2f}% vs {before})" for k, m in metrics.items()]
    financial = {"summary_text": "\n".join(financial_lines), "metrics": metrics,
                 "fetched_at": _midnight(previous).isoformat(), "source": SOURCES["financial"]}

    news = load_news(previous, data_dir)
    sentiment_lines = [f"Bitcoin news articles dated {previous} (the day before the decision); a title line per article, then one sentence per line."]
    if news == "N/A":
        sentiment_lines.append(f"No news articles are available for {previous}.")
    else:
        # Citations point at lines, and a 5,000-character article on one line left
        # no valid quote_id for a single sentence: one sentence per line instead.
        # Sentence lines carry no numeric label; models copied "[2.13]" as "L2.13".
        for i, n in enumerate(news, 1):
            sentiment_lines.append(f"Article {i} | {_one_line(n['time'])} | {_one_line(n['title'])}")
            sentences = re.split(r"(?<=[.!?])\s+", _one_line(n["content"]))
            sentiment_lines += [s for s in sentences if s]
    sentiment = {"summary_text": "\n".join(sentiment_lines), "fetched_at": _midnight(previous).isoformat(),
                 "source": SOURCES["sentiment"]}
    return {"financial": financial, "market": market, "sentiment": sentiment}


def decide_day(date, inputs, threshold=DEFAULT_CONFLICT_THRESHOLD, day_budget=900):
    """Run specialists -> Conflict Analyzer/Debate -> Mediator for one day."""
    ref = _midnight(date)
    result = {"date": date, "status": "error", "action": 0.0, "errors": [], "explanations_valid": True}
    llm.set_deadline(day_budget)
    try:
        outputs = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
            futures = [(name, pool.submit(module.run, inputs[name], ref)) for name, module in AGENTS]
            for name, future in futures:
                try:
                    outputs.append(future.result())
                except Exception as exc:
                    result["errors"].append(describe_failure(exc, stage="specialist", agent=name))
        result["specialists"] = outputs
        if result["errors"]:
            first = result["errors"][0]
            result.update(status=first["status"], reason=first["reason"])
            return result
        try:
            validation = ConflictAnalyzer(threshold=threshold).evaluate_pipeline(outputs)
        except Exception as exc:
            failure = describe_failure(exc, stage="conflict_analyzer")
            result["errors"].append(failure)
            result.update(status=failure["status"], reason=failure["reason"])
            return result
        result["validation"] = validation
        if not validation.get("explanations_valid", True):
            # Q7 (b): rejected updates were already rolled back; trade and flag.
            status, reason = explanation_status(validation)
            result.update(explanations_valid=False, explanation_status=status, explanation_reason=reason)
        final = validation.get("debate_updated_outputs") or outputs
        mediated = run_mediator(final, current_time=ref)
        signal = signal_of(mediated["S_final"])
        result.update(status="ok", reason=None, mediator=mediated, S_final=mediated["S_final"],
                      signal=signal, action=ACTION[signal])
        return result
    finally:
        llm.set_deadline(None)


def install_call_cache(calls_dir):
    """Cache every provider response on disk; unusable content is never replayed."""
    calls_dir = Path(calls_dir)
    calls_dir.mkdir(parents=True, exist_ok=True)
    send = llm._send
    stats = {"new": 0, "cached": 0, "failed": 0}

    def _save(path, data):
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False))
        os.replace(tmp, path)

    def cached_send(client, **kwargs):
        from openai.types.chat import ChatCompletion
        path = calls_dir / f"{llm.request_key(client.base_url, kwargs)}.json"
        if path.exists():
            record = json.loads(path.read_text())
            if record.get("status") == "ok":
                stats["cached"] += 1
                return ChatCompletion.model_validate(record["response"])
        started = time.monotonic()
        try:
            response = send(client, **kwargs)
        except Exception:
            stats["failed"] += 1
            raise
        stats["new"] += 1
        _save(path, {"status": "ok", "model": kwargs.get("model"), "messages": kwargs.get("messages"),
                     "response": response.model_dump(), "elapsed_seconds": time.monotonic() - started})
        return response

    def on_rejected(key, reason):
        path = calls_dir / f"{key}.json"
        if path.exists():
            record = json.loads(path.read_text())
            record.update(status="rejected_content", rejected_reason=str(reason)[:500])
            _save(path, record)

    llm._send, llm._on_rejected = cached_send, on_rejected
    return stats


def simulate(window_dates, actions):
    """Replay a date->action map through the baseline TradingEnv."""
    env = TradingEnv(*window_dates)
    state = env.reset()
    returns, directional, correct = [], 0, 0
    while not env.done:
        today = env.data[env.current_step]
        action = actions.get(today["date"], 0.0)
        state, info = env.step(action)
        returns.append(state["today_roi"])
        if action:
            directional += 1
            correct += (action > 0) == (state["open"] > today["open"])
    return {"total_return": state["roi"], "sharpe": sharpe(returns), "days": len(returns),
            "direction_accuracy": correct / directional if directional else None, "directional_days": directional}


def ablations(days):
    """Offline variants from saved outputs (no LLM calls): subsets of specialists
    through the Mediator, the no-Debate decision, and the full system."""
    variants = {"market_only": ("Market_Agent",), "market_financial": ("Market_Agent", "Financial_Agent"),
                "market_sentiment": ("Market_Agent", "Sentiment_Agent"),
                "no_debate": ("Market_Agent", "Financial_Agent", "Sentiment_Agent")}
    out = {name: {} for name in (*variants, "full")}
    for date, day in days.items():
        ref = _midnight(date)
        specialists = {s["agent_id"]: s for s in day.get("specialists", [])}
        for name, agents in variants.items():
            if all(a in specialists for a in agents):
                s_final = run_mediator([copy.deepcopy(specialists[a]) for a in agents], current_time=ref)["S_final"]
                out[name][date] = ACTION[signal_of(s_final)]
        out["full"][date] = day.get("action", 0.0)
    return out


def run_window(window_dates, out_dir, threshold=DEFAULT_CONFLICT_THRESHOLD, day_budget=900, limit_days=None,
               log=print):
    out_dir = Path(out_dir)
    (out_dir / "days").mkdir(parents=True, exist_ok=True)
    stats = install_call_cache(out_dir / "calls")
    prices, txn_stats = load_prices(), load_txn_stats()
    trading_days = [d["date"] for d in TradingEnv(*window_dates).data[:-1]]
    for i, date in enumerate(trading_days[:limit_days] if limit_days else trading_days, 1):
        path = out_dir / "days" / f"{date}.json"
        if path.exists() and json.loads(path.read_text()).get("status") == "ok":
            continue
        started = time.monotonic()
        try:
            day = decide_day(date, build_inputs(date, prices, txn_stats), threshold, day_budget)
        except ValueError as exc:
            day = {"date": date, "status": "data_error", "reason": str(exc), "action": 0.0}
        day["elapsed_seconds"] = round(time.monotonic() - started, 1)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(day, indent=2, ensure_ascii=False, default=str))
        os.replace(tmp, path)
        flag = "" if day.get("explanations_valid", True) else f" [explanation {day.get('explanation_reason')}]"
        log(f"[{i}/{len(trading_days)}] {date} {day['status']} {day.get('signal', '')} "
            f"{day['action']:+.1f} ({day['elapsed_seconds']}s){flag}")
        if day["status"] == "api_error" and day.get("reason") in llm.FATAL_API_ERRORS:
            log("Stopping: fatal provider error; rerun the same command to resume.")
            break
    days = {p.stem: json.loads(p.read_text()) for p in sorted((out_dir / "days").glob("*.json"))}
    variants = ablations(days)
    result = {name: simulate(window_dates, actions) for name, actions in variants.items()}
    statuses = {}
    for day in days.values():
        statuses[day["status"]] = statuses.get(day["status"], 0) + 1
    summary = {"window": list(window_dates), "threshold": threshold, "trading_days": len(trading_days),
               "decided_days": len(days), "status_counts": statuses,
               "debate_days": sum(bool((d.get("validation") or {}).get("conflict_detected")) for d in days.values()),
               "explanation_rejected_days": sum(not d.get("explanations_valid", True) for d in days.values()),
               "models": {role: llm.get_agent_config(role)["model"]
                          for role in ("financial", "market", "sentiment", "conflict_analyzer", "debate", "grounding")},
               "calls": stats, "results": result}
    tmp = out_dir / "result.json.tmp"
    tmp.write_text(json.dumps(summary, indent=2))
    os.replace(tmp, out_dir / "result.json")
    return summary
