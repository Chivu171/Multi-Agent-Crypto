from types import SimpleNamespace
from unittest.mock import patch

import pytest

from utils.llm import IncompleteLLMResponse, ask_llm


@pytest.mark.parametrize("finish_reason", ["stop", "length"])
def test_provider_finish_reason_is_checked_before_returning_content(finish_reason):
    # Even syntactically complete content must not be accepted if the provider
    # explicitly reports that the response was cut off at its generation limit.
    raw = '{"signal":"BUY","confidence":0.6,"logic_path":"test"}'
    response = SimpleNamespace(choices=[SimpleNamespace(
        finish_reason=finish_reason, message=SimpleNamespace(content=raw),
    )])
    config = {"provider": "openrouter", "model": "test-model", "temperature": 0, "max_tokens": 1500}
    with patch("utils.llm.get_agent_config", return_value=config), \
         patch("utils.llm._get_openrouter_client", return_value=object()), \
         patch("utils.llm._create_completion", return_value=response) as completion:
        if finish_reason == "length":
            with pytest.raises(IncompleteLLMResponse, match="finish_reason=length, max_tokens=1500"):
                ask_llm("test evidence", agent_name="financial")
        else:
            assert ask_llm("test evidence", agent_name="financial") == raw
    assert completion.call_count == 1


def test_reasoning_setting_reaches_provider_before_budget_is_consumed():
    config = {"provider": "openrouter", "model": "fixture", "temperature": 0,
              "max_tokens": 1200, "reasoning_effort": "none"}
    def provider(client, **kwargs):
        off = kwargs.get("extra_body", {}).get("reasoning", {}).get("effort") == "none"
        return SimpleNamespace(choices=[SimpleNamespace(
            finish_reason="stop" if off else "length",
            message=SimpleNamespace(content='{"ok":true}' if off else None),
        )])
    with patch("utils.llm.get_agent_config", return_value=config), \
         patch("utils.llm._get_openrouter_client", return_value=object()), \
         patch("utils.llm._create_completion", side_effect=provider):
        assert ask_llm("review the supplied snapshot", agent_name="grounding") == '{"ok":true}'
