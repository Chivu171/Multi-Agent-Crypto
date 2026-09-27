"""Failure handling shared by live and backtest runs: JSON, retries, time budget,
resume and the full specialist → RCA → two-round Debate path."""
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import httpx
import openai
import pytest

from scripts.evaluate_direction import fatal_api_error, needs_run, run_day, save
from utils import llm
from utils.grounding import GROUNDING_SYSTEM_PROMPT, REVIEW_SYSTEM_PROMPT
from utils.llm import DeadlineExceeded, LLMAPIError, LLMResponseError
from utils.parsing import parse_json_response
from utils.specialist_response import SPECIALIST_REVIEW_PROMPT


def api_error(status, message, headers=None):
    response = httpx.Response(status, headers=headers or {}, request=httpx.Request("POST", "https://x"))
    cls = openai.RateLimitError if status == 429 else openai.APIStatusError
    return cls(message, response=response, body={"message": message})


# ── JSON ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("raw, kind", [
    ("", "empty"), ("   ", "empty"),
    ('{"signal": "BUY", "logic_path": {"steps": ["a"]', "no_json"),
    ("không có JSON", "no_json"),
    ('{"a": 1} rồi {"a": 2}', "no_json"),
    ("[1, 2]", "schema"),
])
def test_json_failures_are_classified_not_repaired(raw, kind):
    with pytest.raises(LLMResponseError) as error:
        parse_json_response(raw)
    assert error.value.kind == kind


def test_broken_outer_object_is_not_replaced_by_inner_fragment():
    with pytest.raises(LLMResponseError):
        parse_json_response('{"claims": [{"citations": {"evidence_id": "E001"}}, {"text": "cut')


def test_prose_and_repeated_identical_object_are_accepted():
    assert parse_json_response('Kết quả:\n```json\n{"a": 1}\n```\nNhắc lại {"a": 1}') == {"a": 1}


# ── API errors and retry ─────────────────────────────────────────────────────
@pytest.mark.parametrize("status, message, kind", [
    (429, "Provider returned error", "rate_limit"),
    (429, "Rate limit exceeded: free-models-per-day", "quota"),
    (429, "Rate limit reached ... on tokens per day", "quota"),
    (402, "Insufficient credits", "quota"),
    (404, "This model is unavailable for free", "config"),
    (401, "No auth", "config"),
    (503, "Upstream down", "provider_5xx"),
])
def test_quota_is_distinguished_from_rate_limit(status, message, kind):
    assert llm.classify_api_error(api_error(status, message)) == kind


class FakeClient:
    base_url = "https://fake"

    def with_options(self, **kwargs):
        return self


def test_transient_error_is_retried_within_limit(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    send = Mock(side_effect=[api_error(429, "Provider returned error"), "ok"])
    with patch.object(llm, "_send", send):
        assert llm._create_completion(FakeClient(), model="m") == "ok"
    assert send.call_count == 2


def test_quota_and_config_errors_are_not_retried(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", Mock(side_effect=AssertionError("must not wait")))
    for message, kind in (("free-models-per-day", "quota"), ("model not found", "config")):
        send = Mock(side_effect=api_error(429 if kind == "quota" else 404, message))
        with patch.object(llm, "_send", send), pytest.raises(LLMAPIError) as error:
            llm._create_completion(FakeClient(), model="m")
        assert error.value.kind == kind and error.value.fatal
        assert send.call_count == 1


def test_retry_attempts_are_bounded(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    send = Mock(side_effect=api_error(503, "down"))
    with patch.object(llm, "_send", send), pytest.raises(LLMAPIError):
        llm._create_completion(FakeClient(), model="m")
    assert send.call_count == llm.MAX_ATTEMPTS


def test_deadline_stops_waiting_instead_of_retrying_forever(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", Mock(side_effect=AssertionError("must not wait")))
    send = Mock(side_effect=api_error(429, "busy", headers={"retry-after": "120"}))
    llm.set_deadline(30)
    try:
        with patch.object(llm, "_send", send), pytest.raises(DeadlineExceeded):
            llm._create_completion(FakeClient(), model="m")
        llm.set_deadline(0)
        with pytest.raises(DeadlineExceeded):
            llm._create_completion(FakeClient(), model="m")
    finally:
        llm.set_deadline(None)
    assert send.call_count == 1


def test_empty_and_truncated_content_is_rejected_from_cache():
    rejected = []
    config = {"provider": "openrouter", "model": "m", "temperature": 0, "max_tokens": 10}
    for finish, content, kind in (("stop", "  ", "empty"), ("length", '{"a"', "truncated")):
        response = SimpleNamespace(choices=[SimpleNamespace(finish_reason=finish, message=SimpleNamespace(content=content))])
        with patch("utils.llm.get_agent_config", return_value=config), \
             patch("utils.llm._get_openrouter_client", return_value=FakeClient()), \
             patch("utils.llm._create_completion", return_value=response), \
             patch("utils.llm._on_rejected", side_effect=lambda key, reason: rejected.append(key)), \
             pytest.raises(LLMResponseError) as error:
            llm.ask_llm("p", agent_name="market")
        assert error.value.kind == kind
    assert len(rejected) == 2


# ── Resume and atomic progress ───────────────────────────────────────────────
def test_only_unfinished_days_are_rerun():
    assert needs_run(None, False)
    assert not needs_run({"status": "ok"}, True)
    assert not needs_run({"status": "rejected_by_reviewer"}, False)
    assert needs_run({"status": "rejected_by_reviewer"}, True)
    for status in ("json_invalid", "api_error", "timeout_budget", "data_error", "not_run_quota", "error"):
        assert needs_run({"status": status}, False)


def test_fatal_provider_error_stops_the_run():
    assert fatal_api_error({"errors": [{"status": "api_error", "reason": "quota"}]}) == "quota"
    assert fatal_api_error({"errors": [{"status": "api_error", "reason": "rate_limit"}]}) is None


def test_save_is_atomic(tmp_path):
    path = tmp_path / "day.json"
    save(path, {"status": "ok"})
    with patch("scripts.evaluate_direction.os.replace", side_effect=KeyboardInterrupt):
        with pytest.raises(KeyboardInterrupt):
            save(path, {"status": "error"})
    assert json.loads(path.read_text()) == {"status": "ok"}


# ── Whole day, including two Debate rounds ───────────────────────────────────
def snapshot():
    return json.loads(Path("data/datasets/pilot_2022_01_forecast_previous/snapshots.jsonl").read_text().splitlines()[0])


SIGNALS = {"financial": ("BUY", 0.9), "market": ("SELL", 0.9), "sentiment": ("BUY", 0.85)}


def fake_provider(debate_review=None, debate_error=None):
    """Answer each role by its system prompt; count Debate generations/reviews."""
    calls = {"debate": 0, "debate_review": 0}

    def complete(client, **kwargs):
        system, user = kwargs["messages"][0]["content"], kwargs["messages"][1]["content"]
        if system == SPECIALIST_REVIEW_PROMPT:
            content = json.dumps({"checks": [{"claim_index": 0, "verdict": "supported", "reason": "ok"}]})
        elif system == REVIEW_SYSTEM_PROMPT:
            count = len(json.loads(user)["claims"])
            is_debate = "Vòng" in current["task"]
            if is_debate:
                calls["debate_review"] += 1
            if is_debate and debate_review is not None:
                content = debate_review
            else:
                content = json.dumps({"checks": [{"claim_index": i, "verdict": "supported", "reason": "ok"}
                                                 for i in range(count)]})
        elif system == GROUNDING_SYSTEM_PROMPT:
            current["task"] = json.loads(user)["task"]
            if "Vòng" in current["task"]:
                calls["debate"] += 1
                if debate_error is not None:
                    raise debate_error
            content = json.dumps({"claims": [{"type": "fact", "text": "Nguồn có dữ liệu",
                                              "citations": [{"evidence_id": "E001", "quote_id": "L1"}]}]})
        else:
            agent = next(a for a in SIGNALS if kwargs["model"] == a)
            signal, confidence = SIGNALS[agent]
            content = json.dumps({"signal": signal, "confidence": confidence, "logic_path": "Theo dữ liệu."})
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(content=content))])

    current = {"task": ""}
    return complete, calls


@pytest.fixture
def provider(monkeypatch):
    # Route by agent name through the model field so the fake can tell specialists apart.
    monkeypatch.setattr(llm, "get_agent_config", lambda name: {
        "provider": "openrouter", "model": name, "temperature": 0, "max_tokens": 100})
    monkeypatch.setattr(llm, "_get_openrouter_client", lambda name: FakeClient())

    def install(**options):
        complete, calls = fake_provider(**options)
        monkeypatch.setattr(llm, "_send", complete)
        return calls
    return install


def test_full_day_with_two_accepted_debate_rounds(provider):
    calls = provider()
    result = run_day(snapshot(), day_budget=300)
    assert result["status"] == "ok", result.get("errors")
    validation = result["validation"]
    assert validation["conflict_detected"] and validation["debate_status"] == "accepted"
    assert all([a["round"] for a in out["debate_audit"]] == [1, 2] for out in validation["debate_updated_outputs"])
    assert calls == {"debate": 6, "debate_review": 6}
    assert result["signal"] in {"BUY", "SELL", "NEUTRAL"}


def test_malformed_debate_review_is_json_invalid_not_a_prediction(provider):
    provider(debate_review="không phải JSON")
    result = run_day(snapshot(), day_budget=300)
    assert (result["status"], result["reason"]) == ("json_invalid", "debate_round_1:review_json")
    assert "signal" not in result


def test_quota_during_debate_is_api_error_and_stops_run(provider):
    provider(debate_error=api_error(429, "free-models-per-day"))
    result = run_day(snapshot(), day_budget=300)
    assert (result["status"], result["reason"]) == ("api_error", "quota")
    assert fatal_api_error(result) == "quota"
    assert "signal" not in result


def test_exhausted_day_budget_is_reported(provider):
    provider()
    result = run_day(snapshot(), day_budget=0)
    assert (result["status"], result["reason"]) == ("timeout_budget", "time_budget")
    assert llm.remaining_seconds() is None


def test_corrupt_snapshot_is_data_error_without_calls(provider):
    calls = provider()
    snap = snapshot()
    snap["features"]["close"] += 1
    result = run_day(snap, day_budget=300)
    assert result["status"] == "data_error"
    assert calls == {"debate": 0, "debate_review": 0}
