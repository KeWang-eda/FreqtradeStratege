"""Deterministic causal OHLCV fixtures, independent of ignored market files."""

import numpy as np
import pandas as pd
import pytest


def make_ohlcv(count: int = 240) -> pd.DataFrame:
    """Build valid 4h candles with nonconstant features and no external I/O."""
    index = np.arange(count, dtype=float)
    close = 100 + index * 0.04 + 2 * np.sin(index * 0.3)
    return pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=count, freq="4h", tz="UTC"),
            "open": close * 1.001,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": 500 + index + 50 * np.cos(index * 0.2),
        }
    )


@pytest.fixture
def candles() -> pd.DataFrame:
    return make_ohlcv()
