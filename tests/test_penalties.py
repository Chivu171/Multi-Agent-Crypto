import datetime

import pytest

from utils.penalties import (
    combined_weight,
    entropy_penalty,
    recency_weight_from_iso_timestamp,
    redundancy_penalty,
    time_decay_penalty,
)


def test_entropy_penalty_maps_linearly_and_clamps():
    assert entropy_penalty(0.0) == 0.0
    assert entropy_penalty(1.0) == 1.0
    assert entropy_penalty(0.5) == 0.5
    assert entropy_penalty(2.0) == 1.0  # clamped above max_entropy
    assert entropy_penalty(-0.5) == 0.0  # clamped below zero


def test_redundancy_penalty_maps_linearly_and_clamps():
    assert redundancy_penalty(0.0) == 0.0
    assert redundancy_penalty(1.0) == 1.0
    assert redundancy_penalty(0.5) == 0.5
    assert redundancy_penalty(5.0) == 1.0


def test_time_decay_penalty_is_one_at_zero_age():
    assert time_decay_penalty(0) == 1.0


def test_time_decay_penalty_decreases_with_age():
    recent = time_decay_penalty(60)
    one_year = time_decay_penalty(86400 * 365)
    assert 0.0 < one_year < recent <= 1.0


def test_combined_weight_no_penalties_equals_base_weight():
    assert combined_weight(base_weight=1.0, entropy=0.0, redundancy=0.0, delta_t=0) == 1.0


def test_combined_weight_penalties_reduce_weight():
    penalized = combined_weight(base_weight=1.0, entropy=0.5, redundancy=0.5, delta_t=0)
    assert 0.0 < penalized < 1.0
    # entropy=0.5 and redundancy=0.5 halve the weight twice: 1 * 0.5 * 0.5 = 0.25
    assert penalized == 0.25


def test_combined_weight_scales_with_base_weight():
    low = combined_weight(base_weight=0.5, entropy=0.0, redundancy=0.0, delta_t=0)
    high = combined_weight(base_weight=1.0, entropy=0.0, redundancy=0.0, delta_t=0)
    assert low == high / 2


def test_recency_weight_returns_intrinsic_value():
    """recency_weight_from_iso_timestamp no longer applies time decay;
    it returns a fixed intrinsic trust score of 1.0."""
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    old = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=30)).isoformat()
    assert recency_weight_from_iso_timestamp(now) == 1.0
    assert recency_weight_from_iso_timestamp(old) == 1.0
