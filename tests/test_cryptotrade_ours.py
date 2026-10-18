"""Our system inside the CryptoTrade environment: same information and timing
as the baseline, signal-to-action mapping, the Q7 flag policy and resume.
No real LLM calls."""
import json
import re
import pytest
from openai.types.chat import ChatCompletion

from baselines.cryptotrade import ours
from baselines.cryptotrade.env import WINDOWS, TradingEnv
from utils import llm
from utils.grounding import GROUNDING_SYSTEM_PROMPT, REVIEW_SYSTEM_PROMPT
from utils.specialist_response import SPECIALIST_REVIEW_PROMPT


def test_agents_see_exactly_what_the_baseline_agent_sees_each_day():
    env = TradingEnv(*WINDOWS["bull"])
    state = env.reset()
    prices, txn = ours.load_prices(), ours.load_txn_stats()
    while not env.done:
        date = env.data[env.current_step]["date"]
        inputs = ours.build_inputs(date, prices, txn)
        assert inputs["market"]["price"] == state["open"]
        assert inputs["market"]["technical"] == state["technical"]
        assert {k: m["value"] for k, m in inputs["financial"]["metrics"].items()} == state["txnstat"]
        titles = [n["title"] for n in state["news"]] if state["news"] != "N/A" else []
        assert all(t.split()[0] in inputs["sentiment"]["summary_text"] for t in titles)
        state, _ = env.step(0)


def test_no_information_after_the_decision_time():
    inputs = ours.build_inputs("2023-10-10")
    market_dates = [l.split()[1].rstrip(":") for l in inputs["market"]["summary_text"].splitlines() if l.startswith("Open ")]
    assert max(market_dates) == "2023-10-10"
    assert inputs["financial"]["fetched_at"].startswith("2023-10-09")
    assert inputs["sentiment"]["fetched_at"].startswith("2023-10-09")
    assert "2023-10-10" not in inputs["financial"]["summary_text"]


def test_each_evidence_item_is_its_own_line():
    inputs = ours.build_inputs("2023-10-02")
    assert len(inputs["financial"]["summary_text"].splitlines()) == 1 + 6
    lines = inputs["sentiment"]["summary_text"].splitlines()
    titles = [l for l in lines if re.match(r"Article \d+ \| ", l)]
    assert 1 <= len(titles) <= 5 and len(lines) > len(titles) + 1
    assert not any(re.match(r"\[\d+\.\d+\]", l) for l in lines)  # no labels that look like quote ids
    assert max(len(l) for l in lines) < 2000  # no article squeezed onto one line


SIGNALS = {"financial": ("BUY", 0.8), "market": ("SELL", 0.8), "sentiment": ("SELL", 0.7)}


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setattr(llm, "get_agent_config", lambda name: {
        "provider": "openrouter", "model": name, "temperature": 0, "max_tokens": 100})

    class FakeClient:
        base_url = "https://fake"

        def with_options(self, **kwargs):
            return self

    monkeypatch.setattr(llm, "_get_openrouter_client", lambda name: FakeClient())

    def install(debate_review=None):
        calls = {"n": 0}
        current = {"task": ""}

        def complete(client, **kwargs):
            calls["n"] += 1
            system, user = kwargs["messages"][0]["content"], kwargs["messages"][1]["content"]
            if system == SPECIALIST_REVIEW_PROMPT:
                content = json.dumps({"checks": [{"claim_index": 0, "verdict": "supported", "reason": "ok"}]})
            elif system == REVIEW_SYSTEM_PROMPT:
                n = len(json.loads(user)["claims"])
                content = (debate_review if debate_review and "Vòng" in current["task"] else
                           json.dumps({"checks": [{"claim_index": i, "verdict": "supported", "reason": "ok"}
                                                  for i in range(n)]}))
            elif system == GROUNDING_SYSTEM_PROMPT:
                current["task"] = json.loads(user)["task"]
                content = json.dumps({"claims": [{"type": "fact", "text": "Nguồn có dữ liệu",
                                                  "citations": [{"evidence_id": "E001", "quote_id": "L2"}]}]})
            else:
                signal, conf = SIGNALS[kwargs["model"]]
                content = json.dumps({"signal": signal, "confidence": conf, "logic_path": "Theo dữ liệu."})
            return ChatCompletion.model_validate({
                "id": "fake", "object": "chat.completion", "created": 0, "model": kwargs["model"],
                "choices": [{"index": 0, "finish_reason": "stop",
                             "message": {"role": "assistant", "content": content}}]})
        monkeypatch.setattr(llm, "_send", complete)
        return calls
    return install


def test_decision_maps_to_action_with_debate(provider):
    provider()
    day = ours.decide_day("2023-10-02", ours.build_inputs("2023-10-02"))
    assert day["status"] == "ok" and day["explanations_valid"]
    assert day["validation"]["conflict_detected"]
    assert day["action"] == ours.ACTION[day["signal"]]


def test_rejected_debate_still_trades_and_is_flagged(provider):
    provider(debate_review="not json")
    day = ours.decide_day("2023-10-02", ours.build_inputs("2023-10-02"))
    assert day["status"] == "ok" and day["explanations_valid"] is False
    assert day["explanation_status"] == "json_invalid" and "debate_round_1" in day["explanation_reason"]
    assert day["action"] == ours.ACTION[day["signal"]]


def test_simulate_matches_env_and_ablations_use_saved_outputs():
    window = ("2023-10-01", "2023-10-06")
    dates = [d["date"] for d in TradingEnv(*window).data[:-1]]
    result = ours.simulate(window, {d: 0.5 for d in dates})
    env = TradingEnv(*window)
    env.reset()
    while not env.done:
        state, _ = env.step(0.5)
    assert result["total_return"] == pytest.approx(state["roi"])
    assert result["directional_days"] == len(dates)


def test_run_window_resumes_without_new_calls(provider, tmp_path, monkeypatch):
    calls = provider()
    monkeypatch.setattr(llm, "_on_rejected", lambda *a: None)
    summary = ours.run_window(("2023-10-01", "2023-10-06"), tmp_path, limit_days=2, log=lambda m: None)
    first = calls["n"]
    assert summary["decided_days"] == 2 and summary["status_counts"] == {"ok": 2}
    assert set(summary["results"]) == {"market_only", "market_financial", "market_sentiment", "no_debate", "full"}
    ours.run_window(("2023-10-01", "2023-10-06"), tmp_path, limit_days=2, log=lambda m: None)
    assert calls["n"] == first  # finished days are not recomputed


def test_trend_context_adds_only_past_trend_lines_to_market():
    base = ours.build_inputs("2023-10-10")
    trend = ours.build_inputs("2023-10-10", trend_context=True)
    extra = [l for l in trend["market"]["summary_text"].splitlines()
             if l not in base["market"]["summary_text"].splitlines()]
    assert [l.split()[0] for l in extra] == ["Return", "MA50", "Consecutive"]
    assert "2023-10-10" in extra[0] and "2023-10-11" not in trend["market"]["summary_text"]
    for role in ("financial", "sentiment"):
        assert trend[role] == base[role]


def test_trend_lines_use_opens_up_to_the_decision_day():
    prices = ours.load_prices()
    index = next(i for i, d in enumerate(prices) if d["date"] == "2023-10-10")
    changed = [dict(d) for d in prices]
    for d in changed[index + 1:]:
        d["open"] *= 3
    assert ours.trend_lines(changed, index) == ours.trend_lines(prices, index)


def test_debias_adds_earlier_headlines_and_notes_only():
    base = ours.build_inputs("2023-10-10")
    debiased = ours.build_inputs("2023-10-10", debias=True)
    base_lines = base["sentiment"]["summary_text"].splitlines()
    lines = debiased["sentiment"]["summary_text"].splitlines()
    assert lines[: len(base_lines)] == base_lines
    earlier = lines[len(base_lines):]
    assert earlier and all(l.startswith("Earlier | ") for l in earlier)
    assert {l.split(" | ")[1] for l in earlier} <= {"2023-10-06", "2023-10-07", "2023-10-08"}
    assert debiased["sentiment"]["task_note"] and debiased["market"]["task_note"]
    assert "task_note" not in base["sentiment"] and "task_note" not in base["market"]
    assert debiased["financial"] == base["financial"]
    assert {k: v for k, v in debiased["market"].items() if k != "task_note"} == base["market"]


def test_task_note_goes_before_the_quoted_data(monkeypatch):
    from agents import sentiment_agent
    seen = {}

    def fake(prompt, **kwargs):
        seen["prompt"] = prompt
        raise RuntimeError("stop")

    monkeypatch.setattr(sentiment_agent, "request_specialist_response", fake)
    data = ours.build_inputs("2023-10-10", debias=True)["sentiment"]
    with pytest.raises(RuntimeError):
        sentiment_agent.run(data)
    assert seen["prompt"].index(ours.SENTIMENT_DEBIAS_NOTE) < seen["prompt"].index("DỮ LIỆU TRÍCH DẪN")


@pytest.fixture
def eth():
    from baselines.cryptotrade import env
    env.set_asset("eth")
    yield env
    env.set_asset("btc")


def test_eth_agents_see_what_the_eth_baseline_agent_sees(eth):
    env = TradingEnv(*WINDOWS["bull"])
    state = env.reset()
    prices, txn = ours.load_prices(), ours.load_txn_stats()
    assert state["open"] == pytest.approx(1670.998956)  # the ETH bull start in the upstream README
    for _ in range(5):
        inputs = ours.build_inputs(env.data[env.current_step]["date"], prices, txn)
        assert inputs["market"]["price"] == state["open"]
        assert {k: m["value"] for k, m in inputs["financial"]["metrics"].items()} == state["txnstat"]
        assert inputs["market"]["summary_text"].startswith("ETH daily open prices")
        assert inputs["sentiment"]["summary_text"].startswith("Ethereum news articles")
        assert all(inputs[k]["asset"] == "ETH" for k in ("market", "financial", "sentiment"))
        state, _ = env.step(0)


def test_btc_inputs_carry_no_asset_key_so_cached_prompts_still_match():
    inputs = ours.build_inputs("2023-10-10")
    assert all("asset" not in inputs[k] for k in inputs)
    assert inputs["market"]["source"] == "CryptoTrade dataset: CoinMarketCap BTC daily open prices"


def test_specialist_prompt_names_the_traded_asset(eth, monkeypatch):
    import datetime as dt
    from agents import market_agent
    seen = {}

    def fake(prompt, **kwargs):
        seen["prompt"] = prompt
        raise RuntimeError("stop")

    monkeypatch.setattr(market_agent, "request_specialist_response", fake)
    with pytest.raises(RuntimeError):
        market_agent.run(ours.build_inputs("2023-10-10")["market"], dt.datetime(2023, 10, 10, tzinfo=dt.timezone.utc))
    assert seen["prompt"].startswith("Dự báo hướng giá ETH")
