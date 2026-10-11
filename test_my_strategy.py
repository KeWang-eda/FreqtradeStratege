import pandas as pd

from MyStrategy import make_next_direction_labels


def test_threshold_direction_labels_and_unfinished_tail():
    close = pd.Series([100.0, 100.3, 99.6, 99.5])
    labels = make_next_direction_labels(close, horizon=1, threshold=0.002)

    assert labels.iloc[0] == "up"
    assert labels.iloc[1] == "down"
    assert labels.iloc[2] == "flat"
    assert pd.isna(labels.iloc[3])
