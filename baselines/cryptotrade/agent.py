"""CryptoTrade LLM agent loop (eth_trial.py upstream), with a paid-call cache.

Per day: on-chain analyst, news analyst, reflection analyst, then trader, all
single user messages at temperature 0 and seed 6216 as upstream. Every
completion is cached by request hash, so rerunning a window after an
interruption replays finished days for free and continues where it stopped.
Retries/timeouts use the project's shared policy in utils/llm.py.
"""
import datetime as dt
import json
import os
from pathlib import Path

from openai import OpenAI

from baselines.cryptotrade.env import TradingEnv, sharpe
from baselines.cryptotrade.prompts import History
from utils import llm as llm_utils
from utils.config import OPENROUTER_API_KEY, OPENROUTER_BASE_URL

SEED = 6216
VARIANTS = {  # upstream ablation flags: tech, txnstat, news, reflection
    "full": dict(use_tech=True, use_txnstat=True, use_news=True, use_reflection=True),
    "wo_news": dict(use_tech=True, use_txnstat=True, use_news=False, use_reflection=True),
    "wo_txnstat": dict(use_tech=True, use_txnstat=False, use_news=True, use_reflection=True),
    "wo_reflection": dict(use_tech=True, use_txnstat=True, use_news=True, use_reflection=False),
    # Market data only (price + technical signal): the baseline the advisor asked for.
    "market_only": dict(use_tech=True, use_txnstat=False, use_news=False, use_reflection=False),
    "price_only": dict(use_tech=False, use_txnstat=False, use_news=False, use_reflection=False),
}


def _save(path, data):
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
    os.replace(tmp, path)


class CachedLLM:
    def __init__(self, cache_dir, model=None, base_url=None, api_key=None, client=None):
        self.model = model or os.getenv("CRYPTOTRADE_MODEL", "openai/gpt-4o")
        self.base_url = base_url or os.getenv("CRYPTOTRADE_BASE_URL", OPENROUTER_BASE_URL)
        self.client = client or OpenAI(base_url=self.base_url,
                                       api_key=api_key or os.getenv("CRYPTOTRADE_API_KEY", OPENROUTER_API_KEY))
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.new_calls = self.cached_calls = 0
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0}

    def __call__(self, prompt):
        request = {"model": self.model, "messages": [{"role": "user", "content": prompt}],
                   "seed": SEED, "temperature": 0.0}
        path = self.cache_dir / f"{llm_utils.request_key(self.base_url, request)}.json"
        if path.exists():
            self.cached_calls += 1
            return json.loads(path.read_text())["content"]
        response = llm_utils._create_completion(self.client, **request)
        content = response.choices[0].message.content or ""
        usage = getattr(response, "usage", None)
        record = {"request": request, "content": content,
                  "finish_reason": response.choices[0].finish_reason,
                  "usage": usage.model_dump() if hasattr(usage, "model_dump") else None,
                  "created_at": dt.datetime.now(dt.timezone.utc).isoformat()}
        if record["usage"]:
            for k in self.usage:
                self.usage[k] += record["usage"].get(k) or 0
        _save(path, record)
        self.new_calls += 1
        return content


def run_agent(starting_date, ending_date, ask, variant="full", out_dir=None):
    flags = VARIANTS[variant]
    env = TradingEnv(starting_date, ending_date)
    state = env.reset()
    history = History(state, use_tech=flags["use_tech"], use_txnstat=flags["use_txnstat"])
    returns, steps, correct, directional = [], [], 0, 0
    while not env.done:
        price_s, news_s, reflection_s, trader_s = history.prompts()
        onchain = ask(price_s).strip()
        news = ask(news_s).strip() if flags["use_news"] else "N/A"
        reflection = ask(reflection_s).strip() if flags["use_reflection"] else "N/A"
        trader = ask(trader_s.format(onchain, news, reflection)).strip()
        open_today = env.data[env.current_step]["open"]
        state, info = env.step(trader)
        action = info["actual_action"]
        history.add("trader_response", trader)
        history.add("action", f"{action:.1f}")
        history.add("state", state)
        returns.append(state["today_roi"])
        # Extra metric for comparison with our system: direction of non-zero actions
        # against the next open (the paper reports returns only).
        went_up = state["open"] > open_today
        if action != 0:
            directional += 1
            correct += (action > 0) == went_up
        steps.append({"date": info["today"], "action": action, "net_worth": state["net_worth"],
                      "today_roi": state["today_roi"], "trader": trader})
    result = {"variant": variant, "starting_date": starting_date, "ending_date": ending_date,
              "total_return": state["roi"], "sharpe": sharpe(returns), "days": len(returns),
              "direction_accuracy": correct / directional if directional else None,
              "directional_days": directional}
    if out_dir:
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        _save(out / "steps.json", steps)
        _save(out / "result.json", result)
    return result
