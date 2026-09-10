# utils/parsing.py

import json
import re
from typing import Any, Dict


def parse_json_response(raw: str) -> Dict[str, Any]:
    """Parse an LLM's raw text response into a JSON object.

    LLMs sometimes wrap JSON in markdown code fences, add explanatory
    prose before/after it, or include thinking/reasoning text like
    "Here's a thinking process:" before the JSON. Try multiple recovery
    strategies in order:

    1. Direct ``json.loads`` on the raw string.
    2. Strip everything before the first ``{`` and after the last ``}``,
       then parse. This handles models that prepend thinking text.
    3. Strip common thinking-prefix lines, then direct parse.
    4. Extract the **last** ``{...}`` block using a greedy match (JSON is
       usually at the end, while reasoning text comes first).
    5. Extract the **first** ``{...}`` block as a last resort.

    Raises ValueError if no valid JSON object can be recovered.
    """
    # Strategy 1: direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: strip everything before first '{' and after last '}'
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and start < end:
        candidate = raw[start : end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    # Strategy 3: strip thinking-prefix lines, then retry direct parse
    cleaned = _strip_thinking_prefixes(raw)
    if cleaned is not raw:
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError:
            pass

    # Strategy 4: greedy last-block fallback — find the last `{...}` block
    # by matching from the final `{` to the final `}` in the string.
    # This works because reasoning text comes first, JSON comes last.
    start = raw.rfind("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and start < end:
        try:
            return json.loads(raw[start : end + 1])
        except json.JSONDecodeError:
            pass

    # Strategy 5: first-block fallback (legacy behavior)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass

    raise ValueError(f"Could not parse JSON from LLM response: {raw[:200]!r}")


def _strip_thinking_prefixes(text: str) -> str:
    """Remove common LLM 'thinking' prefixes that appear before JSON.

    Many models prepend reasoning text such as:
    - "Here's a thinking process:"
    - "Let me think step by step."
    - "Analysis:"
    - "Reasoning:"

    This strips those leading lines so the remaining text starts with
    the JSON payload.
    """
    lines = text.splitlines()
    # Drop leading empty / whitespace-only lines
    while lines and not lines[0].strip():
        lines.pop(0)

    # Drop lines that look like thinking-prefix markers
    thinking_markers = re.compile(
        r"^(here'?s\s+a\s+thinking\s+process"
        r"|let\s+me\s+think"
        r"|analysis"
        r"|reasoning"
        r"|thought"
        r"|step\s+by\s+step"
        r"|internal\s+monologue"
        r"|scratchpad"
        r"|reflection"
        r"|chain-of-thought"
        r"|cot"
        r")"
        r"[:.\-]?\s*$",
        re.IGNORECASE,
    )
    while lines and thinking_markers.match(lines[0].strip()):
        lines.pop(0)

    # Drop any following bullet/numbered reasoning lines until we hit
    # a line that looks like JSON start or is empty after reasoning.
    # We stop when we see a line starting with "{" or when the next
    # non-empty line does NOT look like a reasoning step.
    while lines:
        stripped = lines[0].strip()
        if not stripped:
            break
        # Heuristic: if the line starts with a number/bullet and is short,
        # treat it as a reasoning step and drop it.
        if re.match(r"^(\d+\.|[-•*])\s+", stripped) and len(stripped) < 200:
            lines.pop(0)
        else:
            break

    return "\n".join(lines)
