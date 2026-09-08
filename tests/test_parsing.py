import pytest

from utils.parsing import parse_json_response


def test_parses_clean_json():
    assert parse_json_response('{"signal": "BUY", "confidence": 0.8}') == {
        "signal": "BUY",
        "confidence": 0.8,
    }


def test_recovers_json_wrapped_in_markdown_fence():
    raw = '```json\n{"signal": "BUY", "confidence": 0.8}\n```'
    assert parse_json_response(raw) == {"signal": "BUY", "confidence": 0.8}


def test_recovers_json_with_leading_and_trailing_prose():
    raw = 'Sure, here is the analysis:\n{"signal": "SELL", "confidence": 0.6}\nLet me know if you need more.'
    assert parse_json_response(raw) == {"signal": "SELL", "confidence": 0.6}


def test_raises_value_error_on_unrecoverable_text():
    with pytest.raises(ValueError):
        parse_json_response("this is not JSON at all")
