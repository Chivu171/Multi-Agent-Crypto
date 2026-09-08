# utils/parsing.py

import json
import re
from typing import Any, Dict


def parse_json_response(raw: str) -> Dict[str, Any]:
    """Parse an LLM's raw text response into a JSON object.

    LLMs sometimes wrap JSON in markdown code fences or add explanatory
    prose before/after it. Try a direct parse first, then fall back to
    extracting the first `{...}` block (same recovery strategy already
    used in agents/debate_agent.py).

    Raises ValueError if no valid JSON object can be recovered.
    """
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {raw[:200]!r}")
