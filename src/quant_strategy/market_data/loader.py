"""Read existing Feather, Parquet and CSV OHLCV without framework imports."""

from pathlib import Path

import pandas as pd

from quant_strategy.errors import DataContractError

from .validation import validate_ohlcv


def load_ohlcv(path: str | Path) -> pd.DataFrame:
    """Load a file, explicitly parsing CSV dates as UTC candle-open times."""
    path = Path(path)
    if path.suffix == ".feather":
        frame = pd.read_feather(path)
    elif path.suffix == ".parquet":
        frame = pd.read_parquet(path)
    elif path.suffix == ".csv":
        frame = pd.read_csv(path)
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="raise")
    else:
        raise DataContractError(f"Unsupported OHLCV format: {path.suffix}")
    return validate_ohlcv(frame)
