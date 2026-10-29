"""Create the standalone model wrapper through the shared estimator factory."""

from quant.config import ModelConfig
from quant.errors import ConfigurationError, UnsupportedCapabilityError

from .estimators import create_estimator
from .standalone import StandaloneRegressor


def create_regressor(config: ModelConfig, seed: int = 42) -> StandaloneRegressor:
    """Build a supported standalone estimator; never dynamically import names."""
    if config.backend != "standalone":
        raise UnsupportedCapabilityError("FreqAI estimators must use the FreqAI lifecycle adapter")
    if config.name not in {"ridge", "xgboost", "xgboost_direction"}:
        raise ConfigurationError(f"Unregistered model: {config.name}")
    defaults = (
        {"n_jobs": 1, "tree_method": "hist"}
        if config.name in {"xgboost", "xgboost_direction"}
        else None
    )
    prediction_power = config.params.get("prediction_power", "identity")
    estimator = create_estimator(config.name, config.params, seed=seed, defaults=defaults)
    return StandaloneRegressor(estimator, config.name, prediction_power)
