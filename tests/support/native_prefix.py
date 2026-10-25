"""Share read-only native preparation for an explicitly non-final early prefix.

Only raw candles and their real native feature expansion are cached.  Models,
preprocessors, predictions and final-holdout values are never cached here.
Each consumer receives a deep copy after source/config/code identity checks.
"""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from quant_strategy.errors import DataContractError
from quant_strategy.infrastructure.experiment_store import (
    canonical_hash,
    environment_versions,
    file_hash,
    write_json,
)
from quant_strategy.market_data import load_ohlcv
from quant_strategy.market_data.contracts import frame_fingerprint
from quant_strategy.validation.native_features import populate_native_features

_ROOT = Path(__file__).resolve().parents[2]
_PAIRS = ("BTC/USDT:USDT", "ETH/USDT:USDT", "BNB/USDT:USDT")
_PREFIX_BARS = 600


class NativePrefixCache:
    """Private session preparation with fresh, independently mutable snapshots."""

    def __init__(self, receipt: Path) -> None:
        sources = {
            pair: _ROOT
            / "data/futures"
            / f"{pair.replace('/', '_').replace(':', '_')}-4h-futures.feather"
            for pair in _PAIRS
        }
        config_path = _ROOT / "config.json"
        code = sorted((_ROOT / "src").rglob("*.py"))
        code.extend(sorted((_ROOT / "freqaimodels").glob("*.py")))
        code.extend(_ROOT / name for name in ("MyStrategy.py", "feature.py", "model.py"))
        code.append(Path(__file__))
        self._bound_inputs = {
            path: file_hash(path) for path in [config_path, *sources.values(), *code]
        }
        config = json.loads(config_path.read_text())
        if config["timeframe"] != "4h" or (
            config["freqai"]["feature_parameters"]["label_period_candles"] != 3
        ):
            raise DataContractError("Shared development fixture requires 4h/horizon=3")

        # load_ohlcv checks each file before and after its actual read.  The
        # whole-input checks below also detect replacement between pair reads.
        raw = {pair: load_ohlcv(path) for pair, path in sources.items()}
        begin = max(frame.date.iloc[0] for frame in raw.values())
        frames = {
            pair: frame.loc[frame.date >= begin].iloc[:_PREFIX_BARS].copy()
            for pair, frame in raw.items()
        }
        diagnostic_tail_starts = {
            pair: frame.date.iloc[int(len(frame) * 0.85)] for pair, frame in raw.items()
        }
        if any(len(frame) != _PREFIX_BARS for frame in frames.values()):
            raise DataContractError("Cannot shorten the required common 600-bar prefix")
        if max(frame.date.max() for frame in frames.values()) >= min(
            diagnostic_tail_starts.values()
        ):
            raise DataContractError("Development fixture overlaps the historical diagnostic tail")
        expanded = {pair: populate_native_features(config, frames, pair) for pair in _PAIRS}
        self.assert_current_inputs()
        provenance = {
            "schema": "shared-native-development-prefix-v1",
            "scope": "development",
            "pairs": list(_PAIRS),
            "bars_per_pair": _PREFIX_BARS,
            "common_start": begin.isoformat(),
            "config_sha256": self._bound_inputs[config_path],
            "source_sha256": {pair: self._bound_inputs[path] for pair, path in sources.items()},
            "source_frame_sha256": {pair: frame_fingerprint(frame) for pair, frame in raw.items()},
            "prefix_frame_sha256": {
                pair: frame_fingerprint(frame) for pair, frame in frames.items()
            },
            "expanded_frame_sha256": {
                pair: frame_fingerprint(frame) for pair, frame in expanded.items()
            },
            "production_source_sha256": {
                path.relative_to(_ROOT).as_posix(): self._bound_inputs[path] for path in code
            },
            "environment": environment_versions(),
            "diagnostic_tail_start_identities": {
                pair: date.isoformat() for pair, date in diagnostic_tail_starts.items()
            },
            "final_holdout_values_cached": False,
            "models_cached": False,
            "predictions_cached": False,
        }
        provenance["identity_sha256"] = canonical_hash(provenance)
        write_json(receipt, provenance)
        self._payload = {
            "config": config,
            "pairs": list(_PAIRS),
            "sources": sources,
            "source_sha256": provenance["source_sha256"],
            "frames": frames,
            "expanded": expanded,
            "diagnostic_tail_starts": diagnostic_tail_starts,
            "provenance": provenance,
        }
        self._frame_hashes = {
            "frames": deepcopy(provenance["prefix_frame_sha256"]),
            "expanded": deepcopy(provenance["expanded_frame_sha256"]),
        }

    def assert_current_inputs(self) -> None:
        """Fail on input drift; a different hash never silently renews a cache."""

        for path, expected in self._bound_inputs.items():
            if file_hash(path) != expected:
                raise DataContractError(f"Shared native prefix input changed: {path.name}")

    def snapshot(self) -> dict:
        """Check identities around copying and expose no shared mutable objects."""

        self.assert_current_inputs()
        for group, expected in self._frame_hashes.items():
            cached = self._payload[group]
            if set(cached) != set(expected) or any(
                frame_fingerprint(cached[pair]) != digest for pair, digest in expected.items()
            ):
                raise DataContractError(f"Shared native prefix cached {group} changed")
        result = deepcopy(self._payload)
        self.assert_current_inputs()
        return result


@pytest.fixture(scope="session")
def native_prefix_cache(tmp_path_factory) -> NativePrefixCache:
    directory = tmp_path_factory.mktemp("shared-early-native-prefix")
    return NativePrefixCache(directory / "provenance.json")
