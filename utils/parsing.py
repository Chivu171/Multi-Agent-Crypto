# utils/parsing.py

import json
from typing import Any, Dict

from utils.llm import LLMResponseError


def parse_json_response(raw: str) -> Dict[str, Any]:
    """Extract exactly one complete JSON object from an LLM response.

    Markdown fences and prose around the object are ignored. Nothing is ever
    repaired: a truncated object, no object, or several different objects is
    an ``LLMResponseError`` (kind ``empty`` / ``no_json`` / ``schema``).
    """
    if not isinstance(raw, str) or not raw.strip():
        raise LLMResponseError("Empty LLM response", "empty")
    text = raw.strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = _single_embedded_object(text)
    if not isinstance(value, dict):
        raise LLMResponseError("LLM response JSON is not an object", "schema")
    return value


def _single_embedded_object(text):
    decoder = json.JSONDecoder()
    start = text.find("{")
    if start == -1:
        raise LLMResponseError(f"No JSON object in LLM response: {text[:200]!r}", "no_json")
    try:
        value, end = decoder.raw_decode(text, start)
    except json.JSONDecodeError as exc:
        # Do not fall back to an inner fragment of a broken outer object.
        raise LLMResponseError(f"Incomplete/invalid JSON in LLM response: {exc}", "no_json") from exc
    index = text.find("{", end)
    while index != -1:
        try:
            other, next_end = decoder.raw_decode(text, index)
        except json.JSONDecodeError:
            index = text.find("{", index + 1)
            continue
        if other != value:
            raise LLMResponseError("LLM response contains several different JSON objects", "no_json")
        index = text.find("{", next_end)
    return value
