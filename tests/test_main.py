"""Integration tests cho main.py — pipeline điều phối chính.

main() chứa các nhánh logic quan trọng (degraded mode, không dùng lại logs cũ,
run_status.json, ngưỡng INSUFFICIENT_DATA) nhưng chưa có test tự động nào bảo vệ
khỏi regression. Các test dưới đây mock 3 specialist agent (financial_run,
market_run, sentiment_run) và chạy main() trong một cwd tạm để không đụng
vào file thật của repo.
"""

import json
from unittest.mock import patch

import pytest

import main
from utils.grounding import GroundingError
from utils.llm import DeadlineExceeded, LLMAPIError


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


def test_all_agents_failing_never_reuses_old_logs(isolated_cwd):
    outputs_dir = isolated_cwd / "outputs"
    outputs_dir.mkdir()
    old_logs = json.dumps([make_agent_output(name) for name in
                           ("Financial_Agent", "Market_Agent", "Sentiment_Agent")])
    (outputs_dir / "logs.json").write_text(old_logs)
    quota = LLMAPIError("quota", "free-models-per-day")

    with patch("main.financial_run", side_effect=quota), \
         patch("main.market_run", side_effect=quota), \
         patch("main.sentiment_run", side_effect=quota), \
         patch("main.run_mediator") as mediator:
        status = main.main()

    mediator.assert_not_called()
    assert status == "api_error"
    assert (outputs_dir / "logs.json").read_text() == old_logs
    assert not (outputs_dir / "mediator_result.json").exists()
    run_status = json.loads((outputs_dir / "run_status.json").read_text())
    assert (run_status["status"], run_status["reason"]) == ("api_error", "quota")
    assert [e["agent"] for e in run_status["errors"]] == ["Financial_Agent", "Market_Agent", "Sentiment_Agent"]


def test_json_and_review_failures_are_reported_separately(isolated_cwd):
    rejected = GroundingError({"status": "rejected", "reason": "review_rejected",
                               "attempts": [{"error": "Unsupported facts"}]})
    malformed = GroundingError({"status": "json_invalid", "reason": "truncated",
                                "attempts": [{"error": "finish_reason=length"}]})
    with patch("main.financial_run", side_effect=malformed), \
         patch("main.market_run", side_effect=rejected), \
         patch("main.sentiment_run", side_effect=RuntimeError("bug")):
        status = main.main()
    run_status = json.loads((isolated_cwd / "outputs" / "run_status.json").read_text())
    assert status == "json_invalid"
    assert [(e["status"], e["reason"]) for e in run_status["errors"]] == [
        ("json_invalid", "truncated"), ("rejected_by_reviewer", "review_rejected"), ("error", "RuntimeError")]


def test_rejected_explanation_keeps_previous_results(isolated_cwd):
    outputs_dir = isolated_cwd / "outputs"
    outputs_dir.mkdir()
    (outputs_dir / "mediator_result.json").write_text('{"S_final": 0.5}')
    validation = {"explanations_valid": False, "explanation_failure": "rejected", "degraded_mode": False,
                  "debate_updated_outputs": None, "conflict_score": 0.9, "conflict_detected": True,
                  "metrics": {"mean_pairwise_kl": 1, "decision_variance": 1}, "conflict_categories": [],
                  "trigger_debate_module": True, "root_cause_analysis": "x"}
    with patch("main.financial_run", return_value=make_agent_output("Financial_Agent")), \
         patch("main.market_run", return_value=make_agent_output("Market_Agent")), \
         patch("main.sentiment_run", return_value=make_agent_output("Sentiment_Agent")), \
         patch("main.ValidatorAgent.evaluate_pipeline", return_value=validation):
        status = main.main()
    assert status == "rejected_by_reviewer"
    assert (outputs_dir / "mediator_result.json").read_text() == '{"S_final": 0.5}'
    assert not (outputs_dir / "logs.json").exists()


def test_validator_api_error_exits_with_status(isolated_cwd):
    with patch("main.financial_run", return_value=make_agent_output("Financial_Agent")), \
         patch("main.market_run", return_value=make_agent_output("Market_Agent")), \
         patch("main.sentiment_run", return_value=make_agent_output("Sentiment_Agent")), \
         patch("main.ValidatorAgent.evaluate_pipeline", side_effect=DeadlineExceeded("budget")):
        status = main.main()
    assert status == "timeout_budget"
    assert not (isolated_cwd / "outputs" / "mediator_result.json").exists()
