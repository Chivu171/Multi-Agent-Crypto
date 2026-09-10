import json
from unittest.mock import patch

import scripts.refresh_logs as refresh_logs


def _fake_output(agent_id):
    return {"agent_id": agent_id, "signal": "BUY", "confidence": 0.7}


def test_refresh_logs_writes_cache_when_all_agents_succeed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()

    with patch("scripts.refresh_logs.financial_run", return_value=_fake_output("Financial_Agent")), \
         patch("scripts.refresh_logs.market_run", return_value=_fake_output("Market_Agent")), \
         patch("scripts.refresh_logs.sentiment_run", return_value=_fake_output("Sentiment_Agent")):
        saved = refresh_logs.refresh_logs(str(tmp_path / "outputs" / "logs.json"))

    with open(tmp_path / "outputs" / "logs.json", encoding="utf-8") as f:
        loaded = json.load(f)
    assert len(loaded) == 3
    assert len(saved) == 3


def test_refresh_logs_skips_failing_agent_but_saves_the_rest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()

    with patch("scripts.refresh_logs.financial_run", side_effect=ValueError("LLM returned garbage")), \
         patch("scripts.refresh_logs.market_run", return_value=_fake_output("Market_Agent")), \
         patch("scripts.refresh_logs.sentiment_run", return_value=_fake_output("Sentiment_Agent")):
        saved = refresh_logs.refresh_logs(str(tmp_path / "outputs" / "logs.json"))

    with open(tmp_path / "outputs" / "logs.json", encoding="utf-8") as f:
        loaded = json.load(f)
    assert len(loaded) == 2
    assert {o["agent_id"] for o in loaded} == {"Market_Agent", "Sentiment_Agent"}
    assert len(saved) == 2


def test_refresh_logs_leaves_cache_untouched_when_all_agents_fail(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "outputs").mkdir()
    existing_path = tmp_path / "outputs" / "logs.json"
    existing_path.write_text('[{"agent_id": "stale"}]', encoding="utf-8")

    with patch("scripts.refresh_logs.financial_run", side_effect=ValueError("fail")), \
         patch("scripts.refresh_logs.market_run", side_effect=ValueError("fail")), \
         patch("scripts.refresh_logs.sentiment_run", side_effect=ValueError("fail")):
        saved = refresh_logs.refresh_logs(str(existing_path))

    with open(existing_path, encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == [{"agent_id": "stale"}]
    assert saved == []
