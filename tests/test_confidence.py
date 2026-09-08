from utils.confidence import update_confidence


def test_no_rebuttal_keeps_confidence_unchanged():
    assert update_confidence(0.8, 0.0) == 0.8


def test_full_rebuttal_decays_confidence():
    result = update_confidence(0.8, 1.0, beta=0.8)
    assert 0.0 < result < 0.8


def test_stronger_beta_decays_more():
    weak_decay = update_confidence(0.8, 1.0, beta=0.2)
    strong_decay = update_confidence(0.8, 1.0, beta=2.0)
    assert strong_decay < weak_decay


def test_result_is_clipped_to_valid_range():
    assert update_confidence(0.1, 1.0, beta=10.0) >= 0.0
    assert update_confidence(0.9, 0.0) <= 1.0
