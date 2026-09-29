"""CryptoTrade baseline reimplementation. Reference numbers come from running the
original code (baselines/cryptotrade/verify_against_upstream.py); no LLM calls."""
import json
from types import SimpleNamespace

import pytest

from baselines.cryptotrade import env as ct_env
from baselines.cryptotrade.agent import VARIANTS, CachedLLM, run_agent
from baselines.cryptotrade.env import WINDOWS, TradingEnv, parse_action
from baselines.cryptotrade.rules import run_rule

# Upstream run_strategy() outputs (total return %, Sharpe) on the paper's BTC windows.
UPSTREAM = {
    ("bear", "buy_and_hold"): (-15.607, -0.114), ("bear", "MACD"): (-9.511, -0.089),
    ("sideways", "buy_and_hold"): (-0.831, 0.002), ("sideways", "SMA"): (3.646, 0.048),
    ("bull", "buy_and_hold"): (39.661, 0.253), ("bull", "SLMA"): (38.528, 0.250),
    ("bull", "BollingerBands"): (2.968, 0.148), ("bull", "optimal"): (64.798, 0.456),
}


@pytest.mark.parametrize("window, strategy", sorted(UPSTREAM))
def test_rule_baselines_match_original_code(window, strategy):
    result = run_rule(strategy, *WINDOWS[window])
    ret, sharpe = UPSTREAM[(window, strategy)]
    assert result["total_return"] * 100 == pytest.approx(ret, abs=5e-4)
    assert result["sharpe"] == pytest.approx(sharpe, abs=5e-4)


def test_windows_have_paper_lengths():
    assert [TradingEnv(*WINDOWS[w]).total_steps for w in ("bear", "sideways", "bull")] == [66, 70, 62]


@pytest.mark.parametrize("text, action", [
    ("I recommend buying. Action: 0.5", 0.5), ("sell everything: -1.0", -1.0),
    ("trend up 0.3 ... final 0.7", 0.7), ("no number here", 0.0), ("action 1.5", 0.0), (-2, 0.0),
])
def test_action_parsing_follows_upstream(text, action):
    assert parse_action(text) == action


def test_trade_fees_hand_computed():
    env = TradingEnv(*WINDOWS["bull"])
    env.reset()
    price = env.data[0]["open"]
    cash, coins = env.cash, env.coin_held
    env.step(0.5)
    spent = 0.5 * cash
    assert env.coin_held == pytest.approx(coins + spent / price)
    assert env.cash == pytest.approx(cash - spent - ct_env.GAS_FEE * price - spent * ct_env.EX_RATE)


def fake_ask(log):
    def ask(prompt):
        log.append(prompt)
        return "Trend looks mixed. Action: 0.3" if prompt.startswith("You are an experienced") else "analysis"
    return ask


@pytest.mark.parametrize("variant, per_day", [("full", 4), ("market_only", 2), ("wo_news", 3)])
def test_agent_calls_per_day_follow_ablation_flags(variant, per_day):
    log = []
    result = run_agent("2023-10-01", "2023-10-06", fake_ask(log), variant)
    assert result["days"] == 5 and len(log) == 5 * per_day
    onchain = [p for p in log if "recent price and auxiliary" in p]
    assert all(("unique_addresses" in p) == VARIANTS[variant]["use_txnstat"] for p in onchain)
    assert all("macd_signal" in p for p in onchain)
    assert result["directional_days"] == 5  # every day parsed as 0.3 (buy)


def test_cached_llm_never_pays_twice(tmp_path):
    calls = []

    class FakeClient:
        base_url = "https://fake"

        def with_options(self, **kwargs):
            return self

    def send(client, **request):
        calls.append(request)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop",
                               message=SimpleNamespace(content=f"reply {len(calls)} Action: 0.2"))],
                               usage=None)

    from utils import llm
    original = llm._send
    llm._send = send
    try:
        ask = CachedLLM(tmp_path, model="m", base_url="https://fake", client=FakeClient())
        first = run_agent("2023-10-01", "2023-10-04", ask, "market_only")
        ask2 = CachedLLM(tmp_path, model="m", base_url="https://fake", client=FakeClient())
        second = run_agent("2023-10-01", "2023-10-04", ask2, "market_only")
    finally:
        llm._send = original
    assert ask.new_calls == 6 and ask2.new_calls == 0 and ask2.cached_calls == 6
    assert first == second
    assert all(r["seed"] == 6216 and r["temperature"] == 0.0 for r in calls)
    record = json.loads(next(tmp_path.glob("*.json")).read_text())
    assert record["request"]["model"] == "m"


@pytest.mark.parametrize("profile, signals, asset", [
    ("paper", ("short_long_ma_signal", "macd_signal", "bollinger_bands_signal"), "BTC"),
    ("code", ("macd_signal",), "ETH"),
])
def test_profiles_follow_paper_or_released_code(profile, signals, asset):
    log = []
    run_agent("2023-10-01", "2023-10-12", fake_ask(log), "full", profile=profile)
    onchain = [p for p in log if "recent price and auxiliary" in p]
    assert all(all(f"{s}:" in p for s in signals) for p in onchain)
    assert all(("bollinger_bands_signal" in p) == (profile == "paper") for p in onchain)
    assert all(p.startswith(f"You are a{'n' if asset == 'ETH' else ''} {asset} cryptocurrency") for p in onchain)
    # Reflection looks back 7 trading days in the paper profile, 3 in the code profile.
    reflection = [p for p in log if "Your analysis and action history" in p][-1]
    assert reflection.count("ACTION:") == (7 if profile == "paper" else 3)


def test_asset_wording_never_rewrites_news_content():
    from baselines.cryptotrade.prompts import PROFILES, History
    state = TradingEnv(*WINDOWS["bull"]).reset()
    state["news"] = [{"id": "1", "time": "t", "title": "ETH ETF filing", "content": "ETH rallies"}]
    news_prompt = History(state, **PROFILES["paper"]).prompts()[1]
    assert "ETH ETF filing" in news_prompt and "ETH rallies" in news_prompt
    assert news_prompt.startswith("You are a BTC cryptocurrency")
