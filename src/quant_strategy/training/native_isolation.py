"""Strict, indexed isolation around the installed FreqAI 2026.7 training split.

Sources: FreqAI BaseRegressionModel.train, FreqaiDataKitchen.make_train_test_datasets,
and datasieve.pipeline.Pipeline. These installed sources are hashed into the cache
contract. No global classes or dependencies are modified. A candle is observable
at its close; a horizon-h return is complete at the close of the actual h-th
future candle. Equality with the first validation close is forbidden.
"""

import hashlib
import importlib.metadata
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from datasieve.pipeline import Pipeline

from quant_strategy.errors import DataContractError
from quant_strategy.market_data.contracts import frame_fingerprint, validate_candle_grid
from quant_strategy.market_data.time_index import timeframe_delta

TRAINING_CONTRACT = "native-strict-label-end-before-validation-v2"
CACHE_MANIFEST = "native_training_contract.json"


def file_sha256(path: Path) -> str:
    """Hash real bytes without retaining private absolute paths in manifests."""
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_sha256(value: Any) -> str:
    """Fingerprint JSON-compatible contract data deterministically."""
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), default=str, allow_nan=False
        ).encode()
    ).hexdigest()


def _unique_json_keys(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _read_contract_json(path: Path) -> dict:
    value = json.loads(path.read_text(), object_pairs_hook=_unique_json_keys)
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    return value


def validate_native_config(config: dict) -> None:
    """Reject unsupported identity-changing modes before constructing FreqAI."""
    import freqtrade

    if freqtrade.__version__ != "2026.7":
        raise DataContractError("Native isolation requires the audited Freqtrade 2026.7")
    settings = config.get("freqai", {})
    parameters = settings.get("feature_parameters", {})
    split = settings.get("data_split_parameters", {})
    horizon = parameters.get("label_period_candles")
    if isinstance(horizon, bool) or not isinstance(horizon, int) or horizon < 1:
        raise DataContractError("The current return-label contract requires positive horizon")
    if split.get("shuffle", False) or parameters.get("shuffle_after_split", False):
        raise DataContractError("Native isolation refuses shuffled sample identities")
    if parameters.get("reverse_train_test_order", False):
        raise DataContractError("Native isolation refuses reverse train/test ordering")
    if parameters.get("use_SVM_to_remove_outliers", False) or parameters.get(
        "use_DBSCAN_to_remove_outliers", False
    ):
        raise DataContractError("Unaudited row-removing SVM/DBSCAN pipelines are unsupported")
    if settings.get("continual_learning", False):
        raise DataContractError("Continual learning needs a separate cross-window isolation audit")
    if settings.get("fit_live_predictions_candles", 0):
        raise DataContractError("Live prediction label statistics need a separate isolation audit")
    if parameters.get("noise_standard_deviation", 0):
        raise DataContractError(
            "Stochastic feature noise needs an explicit reproducibility contract"
        )


def training_contract(config: dict) -> dict:
    """Bind caches to the actual semantics, software and local backtest inputs."""
    from freqtrade.freqai.base_models.BaseRegressionModel import BaseRegressionModel
    from freqtrade.freqai.data_kitchen import FreqaiDataKitchen
    from freqtrade.freqai.freqai_interface import IFreqaiModel

    validate_native_config(config)
    root = Path(__file__).resolve().parents[3]
    sources = {
        "training/native_isolation.py": Path(__file__),
        "freqaimodels/XGBoostRegressorES.py": root / "freqaimodels/XGBoostRegressorES.py",
        "freqtrade/BaseRegressionModel.py": Path(inspect.getfile(BaseRegressionModel)),
        "freqtrade/data_kitchen.py": Path(inspect.getfile(FreqaiDataKitchen)),
        "freqtrade/freqai_interface.py": Path(inspect.getfile(IFreqaiModel)),
        "datasieve/pipeline.py": Path(inspect.getfile(Pipeline)),
    }
    # Strategy, labels and features are part of cache semantics as well as model code.
    for folder in ("features", "labels", "backends"):
        for path in sorted((root / "src/quant_strategy" / folder).glob("*.py")):
            sources[f"quant_strategy/{folder}/{path.name}"] = path
    sources["execution/freqtrade_strategy.py"] = (
        root / "src/quant_strategy/execution/freqtrade_strategy.py"
    )
    for path in sorted(Path(inspect.getfile(Pipeline)).parent.joinpath("transforms").glob("*.py")):
        sources[f"datasieve/transforms/{path.name}"] = path
    mode = getattr(config.get("runmode"), "value", config.get("runmode", "unspecified"))
    local_sources: dict[str, str | None] = {}
    if mode not in {"live", "dry_run"} and config.get("datadir"):
        base = Path(config["datadir"])
        pairs = set(config.get("exchange", {}).get("pair_whitelist", [])) | set(
            config["freqai"]["feature_parameters"].get("include_corr_pairlist", [])
        )
        timeframes = config["freqai"]["feature_parameters"].get("include_timeframes", [])
        extension = config.get("dataformat_ohlcv", "feather")
        for pair in sorted(pairs):
            symbol = pair.replace("/", "_").replace(":", "_")
            for timeframe in sorted(set(timeframes) | {config["timeframe"]}):
                relative = f"futures/{symbol}-{timeframe}-futures.{extension}"
                path = base / relative
                local_sources[relative] = file_sha256(path) if path.is_file() else None
    settings = config["freqai"]
    semantic = {
        "timeframe": config["timeframe"],
        "model": config.get("freqaimodel", "XGBoostRegressorES"),
        "features": settings.get("feature_parameters", {}),
        "split": settings.get("data_split_parameters", {}),
        "parameters": settings.get("model_training_parameters", {}),
        "label": config.get("my_experiment", {}),
        "train_period_days": settings.get("train_period_days"),
        "backtest_period_days": settings.get("backtest_period_days"),
        "pairs": sorted(config.get("exchange", {}).get("pair_whitelist", [])),
        "cache_mode": mode,
    }
    return {
        "schema_version": 1,
        "training_contract": TRAINING_CONTRACT,
        "config_sha256": canonical_sha256(semantic),
        "implementation_sha256": {name: file_sha256(path) for name, path in sources.items()},
        "software": {
            name: importlib.metadata.version(name)
            for name in ("freqtrade", "datasieve", "xgboost", "pandas", "numpy", "scikit-learn")
        },
        "backtest_input_sha256": local_sources,
    }


def bind_cache_contract(config: dict) -> dict:
    """Refuse old or incompatible caches before native DataDrawer can load them."""
    contract = training_contract(config)
    root = Path(config["user_data_dir"]) / "models" / config["freqai"]["identifier"]
    marker = root / CACHE_MANIFEST
    if marker.exists():
        try:
            actual = _read_contract_json(marker)
        except (OSError, ValueError) as exc:
            raise DataContractError("Invalid native cache manifest; use a new identifier") from exc
        if actual != contract:
            raise DataContractError("Native cache contract mismatch; use a new identifier")
        _validate_cached_artifacts(root, contract)
    else:
        if root.exists() and any(root.iterdir()):
            raise DataContractError(
                "Existing native cache has no isolation manifest; use a new identifier"
            )
        root.mkdir(parents=True, exist_ok=True)
        # Exclusive creation prevents silently replacing a marker from a concurrent run.
        with marker.open("x") as stream:
            json.dump(contract, stream, indent=2, sort_keys=True)
    return contract


def _validate_cached_artifacts(root: Path, contract: dict) -> None:
    """A root marker alone cannot bless an old model or failed-window prediction."""
    model_names = set()
    try:
        for metadata_path in root.rglob("*_metadata.json"):
            if metadata_path.name == "global_metadata.json":
                continue
            metadata = _read_contract_json(metadata_path)
            if metadata.get("native_training_contract") != TRAINING_CONTRACT:
                raise ValueError("Cached native metadata has no matching training contract")
            audit_path = (
                metadata_path.parent / metadata["native_training_audit"] / "audit.json"
            ).resolve()
            if not audit_path.is_relative_to(root.resolve()):
                raise ValueError("Cached audit path escapes its model namespace")
            audit = _read_contract_json(audit_path)
            if audit.get("status") != "PASS" or audit.get("phase") != "trained":
                raise ValueError("Cached window did not complete audited training")
            if audit.get("cache_contract_sha256") != canonical_sha256(contract):
                raise ValueError("Cached window training contract is incompatible")
            for filename, expected in audit["artifacts"].items():
                artifact = (audit_path.parent / filename).resolve()
                if artifact.parent != audit_path.parent or file_sha256(artifact) != expected:
                    raise ValueError("Cached training audit artifact is missing or corrupt")
            model_names.add(metadata["model_filename"])
        for path in root.rglob("*_model.joblib"):
            if path.name.removesuffix("_model.joblib") not in model_names:
                raise ValueError("Cached model has no successfully audited metadata")
        for path in root.rglob("*_prediction.feather"):
            if path.name.removesuffix("_prediction.feather") not in model_names:
                raise ValueError("Cached prediction has no successfully audited metadata")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise DataContractError(
            f"Invalid native cache artifacts: {exc}; use a new identifier"
        ) from exc


def _time_metadata(raw: pd.DataFrame, pair: str, config: dict) -> pd.DataFrame:
    if raw.empty or not raw.index.is_unique:
        raise DataContractError("Native training needs nonempty data and unique source indices")
    validate_candle_grid(raw, config["timeframe"])
    delta = timeframe_delta(config["timeframe"])
    dates = raw.date.dt.tz_convert("UTC")
    if len(dates) > 1 and not dates.diff().iloc[1:].eq(delta).all():
        raise DataContractError(
            "Native training refuses missing candles in the label dependency range"
        )
    horizon = config["freqai"]["feature_parameters"]["label_period_candles"]
    return pd.DataFrame(
        {
            "source_index": raw.index.map(str),
            "row_position": np.arange(len(raw)),
            "sample_id": [
                hashlib.sha256(f"{pair}|{date.isoformat()}".encode()).hexdigest() for date in dates
            ],
            "pair": pair,
            "candle_timestamp": dates,
            "available_at": dates + delta,
            "label_start_time": dates + delta,
            "label_end_time": dates.shift(-horizon) + delta,
            "original_split": "filtered",
            "assignment": "filtered",
            "reason": "missing_feature_or_label",
            "weight": np.nan,
        },
        index=raw.index,
    )


def purge_native_split(
    raw: pd.DataFrame, pair: str, dk: Any, dd: dict, config: dict
) -> pd.DataFrame:
    """Validate native split identities, then synchronously remove unsafe train rows."""
    validate_native_config(config)
    metadata = _time_metadata(raw, pair, config)
    expected = raw[dk.training_features_list].replace([np.inf, -np.inf], np.nan)
    targets = raw[dk.label_list]
    eligible = expected.notna().all(axis=1) & targets.notna().all(axis=1)
    filtered = raw.index[eligible]
    expected_weights = (
        dk.set_weights_higher_recent(len(filtered))
        if config["freqai"]["feature_parameters"].get("weight_factor", 0) > 0
        else np.ones(len(filtered))
    )
    weights = pd.Series(expected_weights, index=filtered)
    validation = config["freqai"]["data_split_parameters"].get("test_size", 0.1) != 0
    train_index = dd["train_features"].index
    valid_index = dd["test_features"].index if validation else raw.index[:0]
    combined = train_index.append(valid_index)
    if not combined.equals(filtered) or not combined.is_unique:
        raise DataContractError(
            "Native train/validation index alignment does not match filtered order"
        )
    if not len(train_index) or (validation and not len(valid_index)):
        raise DataContractError("Native train/validation split is empty")
    for split, index in (("train", train_index), ("test", valid_index)):
        if split == "test" and not validation:
            continue
        features, labels = dd[f"{split}_features"], dd[f"{split}_labels"]
        if not features.index.equals(labels.index):
            raise DataContractError(f"Native {split} X/y indices are misaligned")
        if not features.equals(expected.loc[index]) or not labels.equals(targets.loc[index]):
            raise DataContractError(
                f"Native {split} X/y values are misaligned with original samples"
            )
        actual_weights = np.asarray(dd[f"{split}_weights"])
        if actual_weights.ndim != 1 or not np.array_equal(actual_weights, weights.loc[index]):
            raise DataContractError(f"Native {split} sample weights are misaligned")
        if (
            not np.isfinite(features.to_numpy(dtype=float)).all()
            or not np.isfinite(labels.to_numpy(dtype=float)).all()
        ):
            raise DataContractError("Nonfinite native training features or labels")
        if metadata.loc[index, "label_end_time"].isna().any():
            raise DataContractError("Labeled sample has no observable future label completion time")
        name = "validation" if split == "test" else "train"
        metadata.loc[index, ["original_split", "assignment", "reason"]] = [name, name, "eligible"]
        metadata.loc[index, "weight"] = actual_weights
    boundary = metadata.loc[valid_index, "available_at"].min() if validation else None
    unsafe = (
        metadata.loc[train_index, "label_end_time"].ge(boundary)
        if validation
        else pd.Series(False, index=train_index)
    )
    removed = train_index[unsafe.to_numpy()]
    keep = ~unsafe.to_numpy()
    if not keep.any():
        raise DataContractError("Purge removed all native training samples")
    metadata.loc[removed, ["assignment", "reason"]] = ["purged", "label_end_ge_validation_start"]
    metadata["validation_start"] = boundary if validation else pd.NaT
    dd["train_features"] = dd["train_features"].iloc[keep].copy()
    dd["train_labels"] = dd["train_labels"].iloc[keep].copy()
    dd["train_weights"] = np.asarray(dd["train_weights"])[keep].copy()
    # Native train_dates denotes the entire filtered period, also saved by DataDrawer.
    # Keep that upstream meaning; explicit per-split identities are exported separately.
    return metadata


def validate_training_alignment(metadata: pd.DataFrame, dd: dict, *, fitted=False, dk=None) -> None:
    """Independently reject post-purge boundary, identity and weight violations."""
    train = metadata[metadata.assignment == "train"]
    validation = metadata[metadata.assignment == "validation"]
    if not metadata.index.is_unique or not metadata.sample_id.is_unique or train.empty:
        raise DataContractError("Invalid native sample identity metadata")
    if len(validation) and not train.label_end_time.lt(validation.available_at.min()).all():
        raise DataContractError("Retained train label boundary violation")
    for split, rows in (("train", train), ("test", validation)):
        X, y = dd[f"{split}_features"], dd[f"{split}_labels"]
        if split == "test" and rows.empty:
            if len(X):
                raise DataContractError("Unexpected validation rows in no-validation mode")
            continue
        if not isinstance(X, pd.DataFrame) or not isinstance(y, pd.DataFrame):
            raise DataContractError("Native X/y must retain indexed DataFrames")
        if not X.index.is_unique or not X.index.equals(y.index):
            raise DataContractError("Native preprocessed X/y index alignment failed")
        if not X.index.isin(rows.index).all():
            raise DataContractError("Purged or foreign sample entered model/preprocessor inputs")
        # All supported feature-fit transforms retain training rows. DI can remove validation.
        if split == "train" and not X.index.equals(rows.index):
            raise DataContractError("Native retained training identity/order mismatch")
        expected_order = rows.index[rows.index.isin(X.index)]
        if not X.index.equals(expected_order):
            raise DataContractError("Native validation identity/order mismatch")
        weights = np.asarray(dd[f"{split}_weights"])
        if weights.ndim != 1 or not np.array_equal(weights, metadata.loc[X.index, "weight"]):
            raise DataContractError("Native preprocessed sample weights are misaligned")
        if (
            not np.isfinite(X.to_numpy(dtype=float)).all()
            or not np.isfinite(y.to_numpy(dtype=float)).all()
        ):
            raise DataContractError("Native preprocessed X/y has nonfinite values")
    if fitted:
        for name in ("feature_pipeline", "label_pipeline"):
            indices = getattr(getattr(dk, name), "fit_indices", None)
            if indices is None or not indices.equals(train.index):
                raise DataContractError("Preprocessor fit included purged or validation identities")


class IdentityPreservingPipeline(Pipeline):
    """Keep sample indices through unchanged native transform computations.

    Datasieve 0.1.9 reconstructs DataFrames with RangeIndex. Production DI is the
    only supported row-removing transform here; its actual decision vector maps
    validation rows back to their identities. Unknown removals fail closed.
    """

    def fit_transform(self, X, y=None, sample_weight=None):
        result = super().fit_transform(X, y, sample_weight)
        self.fit_indices = X.index.copy()
        return self._restore(result, X.index, fit=True)

    def transform(self, X, y=None, sample_weight=None, outlier_check=False):
        result = super().transform(X, y, sample_weight, outlier_check=outlier_check)
        return self._restore(result, X.index, fit=False, outlier_check=outlier_check)

    def _restore(self, result, original_index, *, fit, outlier_check=False):
        features, labels, weights = result
        index = original_index
        if len(features) != len(index):
            if fit or outlier_check or "di" not in self:
                raise DataContractError(
                    "Unaudited preprocessor row removal prevents identity alignment"
                )
            step = self["di"]
            mask = np.asarray(step.di_values) < step.di_threshold
            if len(mask) != len(index) or int(mask.sum()) != len(features):
                raise DataContractError("DI output and identity decision vector are misaligned")
            index = index[mask]
        if not isinstance(features, pd.DataFrame):
            raise DataContractError("Native indexed preprocessing requires DataFrame features")
        features.index = index.copy()
        if isinstance(labels, pd.DataFrame):
            if len(labels) != len(index):
                raise DataContractError("Preprocessed X/y are misaligned")
            labels.index = index.copy()
        if weights is not None and len(weights) != len(index):
            raise DataContractError("Preprocessed sample weights are misaligned")
        return features, labels, weights


def write_audit_artifacts(
    directory: Path,
    metadata: pd.DataFrame,
    raw: pd.DataFrame,
    dd: dict,
    dk: Any,
    config: dict,
    *,
    phase: str,
    contract: dict,
    error: str | None = None,
) -> dict:
    """Persist independent-verification inputs, actual outputs and their byte hashes."""
    directory.mkdir(parents=True, exist_ok=True)
    features = list(dk.training_features_list)
    labels = list(dk.label_list)
    tables = {"samples.parquet": metadata, "input.parquet": raw[["date", *features, *labels]]}
    if phase == "before_preprocessing":
        for split in ("train", "test"):
            frame = dd[f"{split}_features"]
            if len(frame):
                tables[f"{split}_before_preprocessing.parquet"] = frame.join(
                    dd[f"{split}_labels"]
                ).assign(sample_weight=np.asarray(dd[f"{split}_weights"]))
    else:
        for split in ("train", "test"):
            frame = dd[f"{split}_features"]
            if len(frame):
                tables[f"{split}_after_preprocessing.parquet"] = frame.join(
                    dd[f"{split}_labels"]
                ).assign(sample_weight=np.asarray(dd[f"{split}_weights"]))
    for filename, frame in tables.items():
        path = directory / filename
        if not path.exists():
            frame.to_parquet(path)
    report = {
        "schema_version": 1,
        "recorded_at": datetime.now(UTC).isoformat(),
        "training_contract": TRAINING_CONTRACT,
        "phase": phase,
        "status": "FAIL" if error else ("PASS" if phase == "trained" else "RUNNING"),
        "error": error,
        "pair": str(metadata.pair.iloc[0]),
        "timeframe": config["timeframe"],
        "label_horizon": config["freqai"]["feature_parameters"]["label_period_candles"],
        "label_mode": config.get("my_experiment", {}).get("label", "raw"),
        "boundary_rule": "label_end_time < validation_start",
        "counts": metadata.assignment.value_counts().to_dict(),
        "feature_schema": features,
        "label_schema": labels,
        "input_fingerprint": frame_fingerprint(raw[["date", *features, *labels]]),
        "cache_contract_sha256": canonical_sha256(contract),
        "cache_contract": contract,
        "artifacts": {path.name: file_sha256(path) for path in sorted(directory.glob("*.parquet"))},
    }
    fitted = {}
    learned_statistics = {}
    for name in ("feature_pipeline", "label_pipeline"):
        pipeline = getattr(dk, name)
        # A DataKitchen is reused across native rolling windows. Before fitting
        # this window, any existing pipeline belongs to the previous window.
        indices = (
            getattr(pipeline, "fit_indices", None) if phase != "before_preprocessing" else None
        )
        if indices is not None:
            fitted[name] = {
                "source_indices": indices.map(str).tolist(),
                "sample_ids": metadata.loc[indices, "sample_id"].tolist(),
                "steps": [step for step, _ in pipeline.steps],
            }
            learned_statistics[name] = {}
            for step_name, step in pipeline.steps:
                estimator = getattr(step, "_skl", step)
                learned_statistics[name][step_name] = {
                    attribute: np.asarray(getattr(estimator, attribute)).tolist()
                    for attribute in (
                        "data_min_",
                        "data_max_",
                        "scale_",
                        "mean_",
                        "var_",
                        "n_samples_seen_",
                    )
                    if hasattr(estimator, attribute)
                }
    report["preprocessor_fit"] = fitted
    report["preprocessor_learned_statistics"] = learned_statistics
    report["label_statistics"] = (
        {"mean": dk.data.get("labels_mean"), "std": dk.data.get("labels_std")}
        if phase != "before_preprocessing"
        else None
    )
    report["label_statistics_fit_sample_ids"] = (
        metadata.loc[metadata.assignment == "train", "sample_id"].tolist()
        if phase != "before_preprocessing"
        else []
    )
    for split in ("train", "test"):
        frame = dd[f"{split}_features"]
        report[f"{split}_output_sample_ids"] = metadata.loc[frame.index, "sample_id"].tolist()
    temporary = directory / "audit.json.tmp"
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True, default=str))
    temporary.replace(directory / "audit.json")
    return report
