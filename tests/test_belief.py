import pytest

from utils.belief import build_belief_vector


def test_buy_maps_to_positive_direction():
    bv = build_belief_vector("BUY", 0.7834)
    assert bv == {"direction": 1, "strength": 0.783}


def test_sell_maps_to_negative_direction():
    bv = build_belief_vector("SELL", 0.5)
    assert bv["direction"] == -1


def test_neutral_maps_to_zero_direction():
    bv = build_belief_vector("NEUTRAL", 0.5)
    assert bv["direction"] == 0


def test_unknown_signal_raises():
    with pytest.raises(KeyError):
        build_belief_vector("HOLD", 0.5)
