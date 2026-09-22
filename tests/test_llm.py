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
