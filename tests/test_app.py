import json
from unittest.mock import patch

import app


def _fake_output(agent_id):
    return {"agent_id": agent_id, "signal": "BUY", "confidence": 0.7}


def test_main_writes_cache_when_all_agents_succeed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()

    with patch("app.financial_run", return_value=_fake_output("Financial_Agent")), \
         patch("app.market_run", return_value=_fake_output("Market_Agent")), \
         patch("app.sentiment_run", return_value=_fake_output("Sentiment_Agent")):
        app.main()

    with open(tmp_path / "outputs" / "logs.json", encoding="utf-8") as f:
        saved = json.load(f)
    assert len(saved) == 3


def test_main_skips_failing_agent_but_saves_the_rest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()

    with patch("app.financial_run", side_effect=ValueError("LLM returned garbage")), \
         patch("app.market_run", return_value=_fake_output("Market_Agent")), \
         patch("app.sentiment_run", return_value=_fake_output("Sentiment_Agent")):
        app.main()

    with open(tmp_path / "outputs" / "logs.json", encoding="utf-8") as f:
        saved = json.load(f)
    assert len(saved) == 2
    assert {o["agent_id"] for o in saved} == {"Market_Agent", "Sentiment_Agent"}


def test_main_leaves_cache_untouched_when_all_agents_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()
    existing_path = tmp_path / "outputs" / "logs.json"
    existing_path.write_text('[{"agent_id": "stale"}]', encoding="utf-8")

    with patch("app.financial_run", side_effect=ValueError("fail")), \
         patch("app.market_run", side_effect=ValueError("fail")), \
         patch("app.sentiment_run", side_effect=ValueError("fail")):
        app.main()

    with open(existing_path, encoding="utf-8") as f:
        saved = json.load(f)
    assert saved == [{"agent_id": "stale"}]
