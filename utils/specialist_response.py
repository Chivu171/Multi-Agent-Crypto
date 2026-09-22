"""Validate specialist responses and retry one invalid model completion.

Never repair a truncated JSON string or replace a failed prediction with
NEUTRAL. Data fetching and transient API retries remain with their callers.
"""

import logging
import math
import unicodedata

from utils.llm import IncompleteLLMResponse
from utils.parsing import parse_json_response

logger = logging.getLogger(__name__)

SPECIALIST_SYSTEM_PROMPT = """You are a JSON-only API. Return one complete JSON object.
No markdown fences or text outside the object. Keep all schema keys in English.
signal must be exactly BUY, SELL or NEUTRAL: never translate these enum values.
confidence must be a finite JSON number between 0 and 1.
Write descriptive text in Vietnamese; keep logic_path under 100 words and
include at most 4 short factors. Escape newlines and quotation marks in strings.
Use only the supplied evidence. Missing measurements are unknown, not zero.
Do not invent values or trends; distinguish forecast from actual and label
unconfirmed hypotheses. Any supplied news may be used even outside named metrics.
Follow the requested schema and close all braces.
"""


def validate_specialist_response(parsed):
    if not isinstance(parsed, dict):
        raise ValueError("Specialist response must be a JSON object")

    raw_signal = parsed.get("signal")
    if not isinstance(raw_signal, str):
        raise ValueError("signal must be BUY, SELL or NEUTRAL")
    signal = unicodedata.normalize("NFC", raw_signal).strip().upper()
    # Exact translations only; never infer a direction from narrative text.
    signal = {"MUA": "BUY", "BÁN": "SELL", "BAN": "SELL",
              "TRUNG LẬP": "NEUTRAL", "TRUNG LAP": "NEUTRAL"}.get(signal, signal)
    if signal not in {"BUY", "SELL", "NEUTRAL"}:
        raise ValueError(f"Invalid signal {raw_signal!r}; expected BUY, SELL or NEUTRAL")

    confidence = parsed.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise ValueError("confidence must be a number between 0 and 1")
    if not math.isfinite(confidence) or not 0 <= confidence <= 1:
        raise ValueError("confidence must be finite and between 0 and 1")

    logic = parsed.get("logic_path")
    steps = logic.get("steps") if isinstance(logic, dict) else logic
    valid_logic = (isinstance(steps, str) and bool(steps.strip())) or (
        isinstance(steps, list) and bool(steps)
        and all(isinstance(step, str) and bool(step.strip()) for step in steps)
    )
    if not valid_logic:
        raise ValueError("logic_path must contain nonempty text or reasoning steps")

    return {**parsed, "signal": signal, "confidence": float(confidence)}


def request_specialist_response(prompt, *, agent_name, ask):
    """Use the same evidence for at most two completions, then surface failure."""
    for attempt in range(2):
        current_prompt = prompt
        if attempt:
            current_prompt += (
                "\nPhản hồi trước không đúng định dạng hoặc chưa hoàn chỉnh. "
                "Trả lại toàn bộ JSON theo schema, dựa trên cùng bằng chứng ở trên. "
                "Viết logic_path ngắn tối đa 3 câu; giữ nguyên mã BUY/SELL/NEUTRAL."
            )
        try:
            raw = ask(current_prompt, agent_name=agent_name, system=SPECIALIST_SYSTEM_PROMPT)
        except IncompleteLLMResponse as exc:
            error = exc
        else:
            try:
                return validate_specialist_response(parse_json_response(raw))
            except ValueError as exc:
                error = exc
        if attempt == 0:
            logger.warning("%s returned invalid/incomplete output; retrying once: %s", agent_name, error)
    raise ValueError(f"{agent_name}: invalid LLM response after 2 attempts: {error}") from error
