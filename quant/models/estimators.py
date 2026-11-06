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
    elif name == "elastic_net":
        from sklearn.linear_model import ElasticNet

        constructor = ElasticNet
    elif name == "xgboost":
        from xgboost import XGBRegressor

        constructor = XGBRegressor
    elif name == "xgboost_direction":
        from xgboost import XGBClassifier

        constructor = XGBClassifier
    elif name == "lightgbm":
        from lightgbm import LGBMRegressor

        constructor = LGBMRegressor
    elif name == "catboost":
        from catboost import CatBoostRegressor

        constructor = CatBoostRegressor
    elif name == "hist_gradient_boosting":
        from sklearn.ensemble import HistGradientBoostingRegressor

        constructor = HistGradientBoostingRegressor
    elif name == "extra_trees":
        from sklearn.ensemble import ExtraTreesRegressor

        constructor = ExtraTreesRegressor
    elif name == "random_forest":
        from sklearn.ensemble import RandomForestRegressor

        constructor = RandomForestRegressor
    else:
        raise ConfigurationError(f"Unregistered estimator: {name}")

    supplied = dict(params or {})
    quantile_alpha = supplied.pop("quantile_alpha", None)
    supplied.pop("weight_factor", None)
    supplied.pop("normalize_sample_weight", None)
    supplied.pop("prediction_power", None)
    if name == "xgboost_direction" and supplied.get("objective", "binary:logistic") not in {
        "binary:logistic", "binary:hinge"
    }:
        raise ConfigurationError(
            "xgboost_direction requires objective='binary:logistic'"
        )
    if seed is not None and "random_state" in supplied and supplied["random_state"] != seed:
        raise ConfigurationError("model.params.random_state must equal the experiment seed")

    parameters = dict(defaults or {})
    if seed is not None:
        parameters["random_seed" if name == "catboost" else "random_state"] = seed
    parameters.update(supplied)
    supported = set(constructor().get_params())
    if name == "catboost":
        # CatBoost exposes only explicitly set parameters through get_params().
        supported |= {
            "iterations", "depth", "learning_rate", "l2_leaf_reg", "random_seed",
            "verbose", "thread_count", "bootstrap_type", "subsample",
            "rsm", "random_strength", "loss_function",
        }
    unknown = set(parameters) - supported
    if unknown:
        raise ConfigurationError(
            f"Unknown model parameters for {name}: {sorted(unknown)}"
        )
    estimator = constructor(**parameters)
    if quantile_alpha is not None:
        if name != "xgboost" or parameters.get("objective") != "reg:quantileerror":
            raise ConfigurationError(
                "quantile_alpha requires xgboost objective='reg:quantileerror'"
            )
        estimator.set_params(quantile_alpha=float(quantile_alpha))
    return estimator
