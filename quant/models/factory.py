"""Create the standalone model wrapper through the shared estimator factory."""

from quant.config import ModelConfig
from quant.errors import ConfigurationError, UnsupportedCapabilityError

from .estimators import create_estimator
from .standalone import StandaloneRegressor


def create_regressor(config: ModelConfig, seed: int = 42) -> StandaloneRegressor:
    """Build a supported standalone estimator; never dynamically import names."""
    if config.backend != "standalone":
        raise UnsupportedCapabilityError("FreqAI estimators must use the FreqAI lifecycle adapter")
    if config.name not in {"ridge", "elastic_net", "xgboost", "xgboost_direction", "lightgbm", "catboost", "hist_gradient_boosting", "extra_trees", "random_forest"}:
        raise ConfigurationError(f"Unregistered model: {config.name}")
    defaults = (
        ({"n_jobs": 1, "tree_method": "hist"}
        if config.name in {"xgboost", "xgboost_direction"} else
        {"n_jobs": 1})
        if config.name in {"xgboost", "xgboost_direction", "lightgbm"}
        else None
    )
    prediction_power = config.params.get("prediction_power", "identity")
    blend_objective = config.params.get("blend_objective")
    blend_weight = float(config.params.get("blend_weight", 0.0))
    blend_quantile_alpha = config.params.get("blend_quantile_alpha")
    if blend_objective is not None:
        if config.name != "xgboost" or not 0.0 < blend_weight < 1.0:
            raise ConfigurationError("blend_objective requires xgboost and blend_weight in (0, 1)")
    parameters = {k: v for k, v in config.params.items() if k not in {"blend_objective", "blend_weight", "blend_quantile_alpha"}}
    estimator = create_estimator(config.name, parameters, seed=seed, defaults=defaults)
    blend_estimator = None
    if blend_objective is not None:
        secondary = dict(parameters)
        secondary["objective"] = blend_objective
        if blend_quantile_alpha is not None:
            secondary["quantile_alpha"] = float(blend_quantile_alpha)
        blend_estimator = create_estimator(config.name, secondary, seed=seed, defaults=defaults)
    return StandaloneRegressor(estimator, config.name, prediction_power, blend_estimator, blend_weight)
