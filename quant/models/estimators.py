"""One validated constructor for the project's supported regression estimators."""

from collections.abc import Mapping
from typing import Any

from quant.errors import ConfigurationError


def create_estimator(
    name: str,
    params: Mapping[str, Any] | None = None,
    *,
    seed: int | None = None,
    defaults: Mapping[str, Any] | None = None,
) -> Any:
    """Construct Ridge or XGBoost after validating parameters against the library.

    This framework-independent seam is shared by standalone experiments and the
    FreqAI model adapters.  The caller owns lifecycle concerns such as preprocessing,
    fit ordering, callbacks and persistence.
    """
    if name == "ridge":
        from sklearn.linear_model import Ridge

        constructor = Ridge
    elif name == "xgboost":
        from xgboost import XGBRegressor

        constructor = XGBRegressor
    else:
        raise ConfigurationError(f"Unregistered estimator: {name}")

    supplied = dict(params or {})
    if seed is not None and "random_state" in supplied and supplied["random_state"] != seed:
        raise ConfigurationError("model.params.random_state must equal the experiment seed")

    parameters = dict(defaults or {})
    if seed is not None:
        parameters["random_state"] = seed
    parameters.update(supplied)
    unknown = set(parameters) - set(constructor().get_params())
    if unknown:
        raise ConfigurationError(
            f"Unknown model parameters for {name}: {sorted(unknown)}"
        )
    return constructor(**parameters)
