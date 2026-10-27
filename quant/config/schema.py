"""Configuration contracts; Freqtrade native settings remain framework-owned."""

from dataclasses import dataclass, field
from typing import Any, Mapping

from quant.errors import ConfigurationError

TECHNICAL_FEATURES = frozenset({"laguerre", "vwmacd", "tke", "vfi", "rmi"})


def validate_features(features: tuple[str, ...]) -> None:
    """Reject unknown feature names and non-sequence input before computation."""
    if not isinstance(features, (list, tuple)) or any(not isinstance(x, str) for x in features):
        raise ConfigurationError("features must be a list of feature names")
    unknown = set(features) - TECHNICAL_FEATURES
    if unknown:
        raise ConfigurationError(f"Unknown features: {sorted(unknown)}")


def positive_int(value: int, name: str, minimum: int = 1) -> None:
    """Validate integer values without truncating floats or accepting booleans."""
    if type(value) is not int or value < minimum:
        raise ConfigurationError(f"{name} must be an integer >= {minimum}")


def known_fields(raw: Mapping[str, Any], allowed: set[str], context: str) -> dict[str, Any]:
    """Strip annotation keys and reject misspelled configuration fields."""
    if not isinstance(raw, Mapping):
        raise ConfigurationError(f"{context} must be a mapping")
    if any(not isinstance(key, str) for key in raw):
        raise ConfigurationError(f"{context} keys must be strings")
    cleaned = {k: v for k, v in raw.items() if not k.startswith("_comment")}
    if unknown := set(cleaned) - allowed:
        raise ConfigurationError(f"Unknown {context} fields: {sorted(unknown)}")
    return cleaned


@dataclass(frozen=True)
class LabelConfig:
    """Future close-to-close return; volnorm uses causal ATR / close."""

    mode: str = "raw"
    prediction_horizon: int = 3
    volatility_period: int = 14

    def __post_init__(self) -> None:
        if not isinstance(self.mode, str) or self.mode not in {"raw", "volnorm"}:
            raise ConfigurationError(f"Unknown label mode: {self.mode}")
        positive_int(self.prediction_horizon, "prediction_horizon")
        positive_int(self.volatility_period, "volatility_period", 2)


@dataclass(frozen=True)
class ValidationConfig:
    """Chronological validation with label-interval purge on every split."""

    method: str = "purged_walk_forward"
    n_splits: int = 3
    test_size: float = 0.2
    min_train_size: int | None = None
    train_window_size: int | None = None
    purge_candles: int | None = None
    purge_reason: str | None = None
    embargo_candles: int = 3
    final_holdout_fraction: float = 0.15

    def __post_init__(self) -> None:
        if not isinstance(self.method, str) or self.method not in {
            "fixed_holdout",
            "expanding_window",
            "rolling_window",
            "purged_walk_forward",
        }:
            raise ConfigurationError(f"Unknown split method: {self.method}")
        positive_int(self.n_splits, "n_splits", 1 if self.method == "fixed_holdout" else 2)
        for name in ("test_size", "final_holdout_fraction"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not 0 < value < 1:
                raise ConfigurationError(f"{name} must be in (0, 1)")
        positive_int(self.embargo_candles, "embargo_candles", 0)
        for name in ("min_train_size", "train_window_size", "purge_candles"):
            if getattr(self, name) is not None:
                positive_int(getattr(self, name), name, 0 if name == "purge_candles" else 1)
        if self.purge_candles is not None and not self.purge_reason:
            raise ConfigurationError("Explicit purge_candles requires purge_reason")
        if self.method == "rolling_window" and self.train_window_size is None:
            raise ConfigurationError("rolling_window requires train_window_size")


@dataclass(frozen=True)
class ModelConfig:
    """Backend selection and explicit estimator parameters."""

    backend: str = "standalone"
    name: str = "ridge"
    params: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.backend, str) or self.backend not in {"standalone", "freqai"}:
            raise ConfigurationError(f"Unknown backend: {self.backend}")
        names = (
            {"ridge", "xgboost"}
            if self.backend == "standalone"
            else {"XGBoostRegressorES", "MomentumRidgeRegressor"}
        )
        if not isinstance(self.name, str) or self.name not in names:
            raise ConfigurationError(f"Unsupported {self.backend} model: {self.name}")
        if not isinstance(self.params, dict):
            raise ConfigurationError("model.params must be a mapping")


@dataclass(frozen=True)
class ExperimentConfig:
    """Resolved research settings, separate from Freqtrade native JSON."""

    name: str = "baseline_raw"
    label: LabelConfig = field(default_factory=LabelConfig)
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    model: ModelConfig = field(default_factory=ModelConfig)
    feature_version: str = "baseline-v2"
    seed: int = 42
    features: tuple[str, ...] = ()
    periods: tuple[int, ...] = (6, 14, 24)
    timeframe: str = "4h"
    data: dict[str, str] = field(default_factory=dict)
    research_contract: str | None = None

    def __post_init__(self) -> None:
        validate_features(self.features)
        if self.research_contract is not None and (
            not isinstance(self.research_contract, str) or not self.research_contract
        ):
            raise ConfigurationError("research_contract must be a nonempty path or null")
        positive_int(self.seed, "seed", 0)
        if (
            not isinstance(self.name, str)
            or not self.name
            or not isinstance(self.feature_version, str)
            or not self.feature_version
        ):
            raise ConfigurationError("name and feature_version must not be empty")
        if not isinstance(self.periods, (tuple, list)) or not self.periods:
            raise ConfigurationError("periods must be a nonempty list or tuple")
        for period in self.periods:
            positive_int(period, "period", 2)
        if len(set(self.periods)) != len(self.periods):
            raise ConfigurationError("periods must be nonempty and unique")
        if not isinstance(self.data, dict) or any(
            not isinstance(v, str) for v in self.data.values()
        ):
            raise ConfigurationError("data must map pairs to input file paths")
        from quant.market_data.time_index import timeframe_delta

        timeframe_delta(self.timeframe)


@dataclass(frozen=True)
class StrategyConfig:
    """Compatibility mapping for my_experiment and FreqAI target horizon."""

    label: str = "raw"
    features: tuple[str, ...] = ()
    probe: bool = False
    label_period_candles: int = 1

    def __post_init__(self) -> None:
        LabelConfig(mode=self.label, prediction_horizon=self.label_period_candles)
        validate_features(self.features)
        if type(self.probe) is not bool:
            raise ConfigurationError("probe must be a boolean")

    @classmethod
    def from_strategy(
        cls, config: Mapping[str, Any], freqai_info: Mapping[str, Any]
    ) -> "StrategyConfig":
        """Map existing native JSON without silently coercing invalid values."""
        raw = known_fields(
            config.get("my_experiment", {}) or {}, {"label", "features", "probe"}, "my_experiment"
        )
        features = raw.get("features", [])
        validate_features(features)
        return cls(
            label=raw.get("label", "raw"),
            features=tuple(sorted(set(features))),
            probe=raw.get("probe", False),
            label_period_candles=freqai_info.get("feature_parameters", {}).get(
                "label_period_candles", 1
            ),
        )
