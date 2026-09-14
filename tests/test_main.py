"""Integration tests cho main.py — pipeline điều phối chính.

main() chứa các nhánh logic quan trọng (degraded mode, fallback logs.json,
FATAL path, ngưỡng INSUFFICIENT_DATA) nhưng chưa có test tự động nào bảo vệ
khỏi regression. Các test dưới đây mock 3 specialist agent (financial_run,
market_run, sentiment_run) và chạy main() trong một cwd tạm để không đụng
vào file thật của repo.
"""

import json
from unittest.mock import patch

import pytest

import main


def make_agent_output(agent_id, signal="BUY", direction=1, strength=0.7, confidence=0.7):
    """Output giống nhau về belief_vector cho mọi agent -> conflict_score thấp,
    tránh kích hoạt RCA/Debate (vốn có thể gọi LLM thật) trong các test này."""
    return {
        "agent_id": agent_id,
        "signal": signal,
        "confidence": confidence,
        "belief_vector": {"direction": direction, "strength": strength},
        "metadata": {
            "recency_weight": 1.0,
            "redundancy_score": 0.1,
            "entropy": 0.1,
            "timestamp": "2026-09-12T00:00:00+00:00",
        },
        "logic_path": ["step1", "step2"],
        "evidence_chunks": [{"content": "evidence text"}],
    }


@pytest.fixture(autouse=True)
def isolated_cwd(tmp_path, monkeypatch):
    """Chạy mỗi test trong một thư mục tạm để main() không đọc/ghi file thật."""
    monkeypatch.chdir(tmp_path)
    yield tmp_path


def test_all_three_agents_succeed(isolated_cwd):
    financial_out = make_agent_output("Financial_Agent")
    market_out = make_agent_output("Market_Agent")
    sentiment_out = make_agent_output("Sentiment_Agent")

    with patch("main.financial_run", return_value=financial_out), \
         patch("main.market_run", return_value=market_out), \
         patch("main.sentiment_run", return_value=sentiment_out):
        main.main()

    logs = json.loads((isolated_cwd / "outputs" / "logs.json").read_text())
    assert len(logs) == 3

    validation_report = json.loads((isolated_cwd / "outputs" / "validation_report.json").read_text())
    assert validation_report["degraded_mode"] is False
    assert validation_report["missing_agents"] == []

    mediator_result = json.loads((isolated_cwd / "outputs" / "mediator_result.json").read_text())
    assert "S_final" in mediator_result


def test_degraded_mode_when_one_agent_fails(isolated_cwd):
    financial_out = make_agent_output("Financial_Agent")
    market_out = make_agent_output("Market_Agent")

    with patch("main.financial_run", return_value=financial_out), \
         patch("main.market_run", return_value=market_out), \
         patch("main.sentiment_run", side_effect=RuntimeError("LLM down")):
        main.main()

    logs = json.loads((isolated_cwd / "outputs" / "logs.json").read_text())
    assert len(logs) == 2

    validation_report = json.loads((isolated_cwd / "outputs" / "validation_report.json").read_text())
    assert validation_report["degraded_mode"] is True
    assert validation_report["missing_agents"] == ["Sentiment_Agent"]


def test_fallback_to_logs_json_when_all_agents_fail(isolated_cwd):
    outputs_dir = isolated_cwd / "outputs"
    outputs_dir.mkdir()
    fallback_data = [
        make_agent_output("Financial_Agent"),
        make_agent_output("Market_Agent"),
        make_agent_output("Sentiment_Agent"),
    ]
    (outputs_dir / "logs.json").write_text(json.dumps(fallback_data, ensure_ascii=False))

    with patch("main.financial_run", side_effect=RuntimeError("down")), \
         patch("main.market_run", side_effect=RuntimeError("down")), \
         patch("main.sentiment_run", side_effect=RuntimeError("down")):
        main.main()

    validation_report = json.loads((outputs_dir / "validation_report.json").read_text())
    assert validation_report["missing_agents"] == []

    mediator_result = json.loads((outputs_dir / "mediator_result.json").read_text())
    assert "S_final" in mediator_result


def test_fatal_when_all_agents_fail_and_no_fallback(isolated_cwd):
    with patch("main.financial_run", side_effect=RuntimeError("down")), \
         patch("main.market_run", side_effect=RuntimeError("down")), \
         patch("main.sentiment_run", side_effect=RuntimeError("down")):
        result = main.main()

    assert result is None
    assert not (isolated_cwd / "outputs" / "mediator_result.json").exists()
    assert not (isolated_cwd / "outputs" / "validation_report.json").exists()
