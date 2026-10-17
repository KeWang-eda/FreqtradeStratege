"""Compare overlapping trades symmetrically; this is a regression audit.

Usage: python verify_no_lookahead.py short.zip long.zip --report /tmp/audit.json
"""

import _quant_strategy_bootstrap  # noqa: F401
from quant_strategy.validation.truncation import load_backtest, trade_key
from quant_strategy.validation.truncation import main as _main


def load_trades(zip_path: str) -> list[dict]:
    """Retain the original helper while validating the backtest export schema."""
    return load_backtest(zip_path)["trades"]


def main(short_zip: str, long_zip: str) -> int:
    """Retain the original two-argument Python entry point."""
    return _main([short_zip, long_zip])


__all__ = ["load_trades", "main", "trade_key"]

if __name__ == "__main__":
    raise SystemExit(_main())
