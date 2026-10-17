"""Explicit registry: new models require deliberate adapters and contracts."""

from typing import Callable

from quant_strategy.config import ModelConfig
from quant_strategy.errors import ConfigurationError, UnsupportedCapabilityError

from .standalone import StandaloneRegressor


def _ridge(params: dict, seed: int) -> StandaloneRegressor:
    from sklearn.linear_model import Ridge

    _validate_params(params, Ridge().get_params())
    return StandaloneRegressor(Ridge(**{"random_state": seed, **params}), "ridge")


def _xgboost(params: dict, seed: int) -> StandaloneRegressor:
    from xgboost import XGBRegressor

    _validate_params(params, XGBRegressor().get_params())
    return StandaloneRegressor(
        XGBRegressor(**{"random_state": seed, "n_jobs": 1, "tree_method": "hist", **params}),
        "xgboost",
    )


MODEL_REGISTRY: dict[str, Callable[[dict, int], StandaloneRegressor]] = {
    "ridge": _ridge,
    "xgboost": _xgboost,
}


def _validate_params(params: dict, supported: dict) -> None:
    if unknown := set(params) - set(supported):
        raise ConfigurationError(f"Unknown model parameters: {sorted(unknown)}")


def create_regressor(config: ModelConfig, seed: int = 42) -> StandaloneRegressor:
    """Build a supported standalone estimator; never dynamically import names."""
    if config.backend != "standalone":
        raise UnsupportedCapabilityError("FreqAI estimators must use the FreqAI lifecycle adapter")
    if config.name not in MODEL_REGISTRY:
        raise ConfigurationError(f"Unregistered model: {config.name}")
    if "random_state" in config.params and config.params["random_state"] != seed:
        raise ConfigurationError("model.params.random_state must equal the experiment seed")
    return MODEL_REGISTRY[config.name](dict(config.params), seed)
