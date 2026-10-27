"""Read existing Feather, Parquet and CSV OHLCV without framework imports."""

from pathlib import Path

import pandas as pd

from quant.errors import DataContractError
from quant.infrastructure.experiment_store import file_hash

from .validation import validate_ohlcv


def load_ohlcv(path: str | Path) -> pd.DataFrame:
    """Load a file, explicitly parsing CSV dates as UTC candle-open times."""
    path = Path(path)
    before = file_hash(path)
    if path.suffix == ".feather":
        frame = pd.read_feather(path)
    elif path.suffix == ".parquet":
        frame = pd.read_parquet(path)
    elif path.suffix == ".csv":
        frame = pd.read_csv(path)
        frame["date"] = pd.to_datetime(frame["date"], utc=True, errors="raise")
    else:
        raise DataContractError(f"Unsupported OHLCV format: {path.suffix}")
    if before != file_hash(path):
        raise DataContractError(
            "Input file changed while reading; retry with a stable data version"
        )
    validated = validate_ohlcv(frame)
    validated.attrs["source_sha256"] = before
    return validated
