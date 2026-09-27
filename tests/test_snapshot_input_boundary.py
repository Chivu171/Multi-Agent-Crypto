import json
from copy import deepcopy
from pathlib import Path

import pytest

from scripts.evaluate_direction import adapter


def snapshot():
    return json.loads(Path('data/datasets/pilot_2022_01_forecast_previous/snapshots.jsonl').read_text().splitlines()[0])


@pytest.mark.parametrize('mutation', ['future_onchain', 'nan_change', 'negative_close', 'future_candle', 'wrong_feature_price'])
def test_corrupt_snapshot_cannot_reach_models(mutation):
    snap = deepcopy(snapshot())
    if mutation == 'future_onchain':
        snap['evidence']['hash-rate']['available_at'] = '2022-01-02T00:00:00+00:00'
    elif mutation == 'nan_change':
        snap['features']['hash_rate_change_1d'] = float('nan')
    elif mutation == 'negative_close':
        snap['market_window']['candles'][-1]['close'] = -1
    elif mutation == 'future_candle':
        snap['market_window']['candles'][-1]['open_time'] = snap['prediction_time']
    else:
        snap['features']['close'] += 100
    with pytest.raises(ValueError):
        adapter(snap)
