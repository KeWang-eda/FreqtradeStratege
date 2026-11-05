"""Lag-return features are causal and match the researched formulas."""
import numpy as np
import pandas as pd

from quant.features.price import add_basic_price_features


def test_lagged_return_features_match_close_pct_change_and_warmup():
    close = pd.Series([100., 103., 101., 106., 104., 110., 108., 112.])
    frame = pd.DataFrame({"open": close, "high": close + 1., "low": close - 1., "close": close, "volume": 10.})
    add_basic_price_features(frame)
    for lag in (1, 2, 3, 6):
        np.testing.assert_allclose(frame[f"%-lag-return-{lag}"], close.pct_change(lag), equal_nan=True)
        assert frame[f"%-lag-return-{lag}"].iloc[:lag].isna().all()


def test_lagged_return_at_time_does_not_depend_on_future_rows():
    frame = pd.DataFrame({"open": [100., 101., 103., 99., 104., 105., 106., 107.], "high": [101., 102., 104., 100., 105., 106., 107., 108.], "low": [99., 100., 102., 98., 103., 104., 105., 106.], "close": [100., 101., 103., 99., 104., 105., 106., 107.], "volume": [10.] * 8})
    prefix, full = frame.iloc[:7].copy(), frame.copy()
    add_basic_price_features(prefix); add_basic_price_features(full)
    for lag in (1, 2, 3, 6):
        column = f"%-lag-return-{lag}"
        np.testing.assert_allclose(prefix[column], full.loc[:6, column], equal_nan=True)
