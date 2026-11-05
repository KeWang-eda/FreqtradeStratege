"""Direction margins cannot silently become return-valued model predictions."""

import joblib
import numpy as np
import pandas as pd
import pytest

from quant.errors import DataContractError
from quant.models.native_direction import NativeDirectionLearner

pytest.importorskip("xgboost")
pytestmark = pytest.mark.unit_contract
IDENTITY = "a" * 64


@pytest.fixture
def native_rows():
    rng = np.random.default_rng(42)
    X = pd.DataFrame({"%x": rng.normal(size=120), "%z": rng.normal(size=120)})
    y = pd.Series(X["%x"] * 0.2 + rng.normal(scale=0.1, size=120), index=X.index)
    y.iloc[0] = 0.0
    return X.iloc[:80], y.iloc[:80], X.iloc[80:], y.iloc[80:]


def learner():
    return NativeDirectionLearner(
        preprocessing_id=IDENTITY,
        params={"n_estimators": 20, "random_state": 42},
        early_stopping_rounds=3,
    )


def fit(model, rows):
    X, y, V, vy = rows
    model.fit_preprocessed(
        X, y, validation_features=V, validation_returns=vy,
        sample_weight=np.linspace(0.4, 1.0, len(X)),
        validation_weight=np.linspace(0.5, 1.0, len(V)),
    )
    return model


def test_prediction_units_and_best_iteration(native_rows):
    model = fit(learner(), native_rows)
    V = native_rows[2]
    probability = model.predict_proba_up(V, preprocessing_id=IDENTITY)
    margin = model.predict_margin(V, preprocessing_id=IDENTITY)
    np.testing.assert_array_equal(margin, 2 * probability - 1)
    assert ((probability >= 0) & (probability <= 1)).all()
    assert model.prediction_kind == "direction_margin"
    assert not hasattr(model, "predict")
    assert model.estimator.get_booster().num_boosted_rounds() == model.estimator.best_iteration + 1


def test_matches_direct_native_binary_logloss_reference(native_rows):
    import xgboost as xgb

    X, y, V, vy = native_rows
    model = fit(learner(), native_rows)
    params = dict(model.params)
    params["callbacks"] = [xgb.callback.EarlyStopping(
        rounds=3, metric_name="logloss", data_name="validation_0",
        maximize=False, save_best=True,
    )]
    reference = xgb.XGBClassifier(**params)
    reference.fit(X, (y > 0).astype(int), sample_weight=np.linspace(0.4, 1.0, len(X)),
                  eval_set=[(V, (vy > 0).astype(int))],
                  sample_weight_eval_set=[np.linspace(0.5, 1.0, len(V))], verbose=False)
    np.testing.assert_array_equal(
        model.predict_proba_up(V, preprocessing_id=IDENTITY),
        reference.predict_proba(V)[:, 1],
    )


@pytest.mark.parametrize("split", ["train", "valid"])
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_rejects_nonfinite_original_returns(native_rows, split, bad):
    X, y, V, vy = [d.copy() for d in native_rows]
    target = y if split == "train" else vy
    target.iloc[0] = bad
    with pytest.raises(DataContractError, match="finite"):
        fit(learner(), (X, y, V, vy))


def test_rejects_misaligned_label_identity(native_rows):
    X, y, V, vy = native_rows
    with pytest.raises(DataContractError, match="align"):
        fit(learner(), (X, y.iloc[::-1], V, vy))


@pytest.mark.parametrize("bad_weight", [-1.0, np.nan, np.inf, 0.0])
def test_rejects_invalid_weights(native_rows, bad_weight):
    X, y, V, vy = native_rows
    with pytest.raises(DataContractError, match="weights"):
        learner().fit_preprocessed(X, y, validation_features=V, validation_returns=vy,
                                   sample_weight=np.full(len(X), bad_weight),
                                   validation_weight=np.ones(len(V)))


def test_rejects_train_validation_overlap(native_rows):
    X, y, _, _ = native_rows
    with pytest.raises(DataContractError, match="overlap"):
        fit(learner(), (X, y, X, y))


def test_rejects_single_training_class(native_rows):
    X, y, V, vy = native_rows
    with pytest.raises(DataContractError, match="both binary"):
        fit(learner(), (X, y.abs()+0.01, V, vy))


def test_rejects_effectively_single_weighted_class(native_rows):
    X, y, V, vy = native_rows
    with pytest.raises(DataContractError, match="positive weight in both"):
        learner().fit_preprocessed(X, y, validation_features=V, validation_returns=vy,
                                   sample_weight=(y > 0).to_numpy(dtype=float),
                                   validation_weight=np.ones(len(V)))


@pytest.mark.parametrize("change", ["reorder", "missing", "duplicate", "nonfinite"])
def test_rejects_wrong_prediction_features(native_rows, change):
    model = fit(learner(), native_rows)
    V = native_rows[2].copy()
    if change == "reorder":
        V = V.iloc[:, ::-1]
    elif change == "missing":
        V = V.iloc[:, :1]
    elif change == "duplicate":
        V.columns = ["%x", "%x"]
    else:
        V.iloc[0, 0] = np.nan
    with pytest.raises(DataContractError):
        model.predict_margin(V, preprocessing_id=IDENTITY)


def test_roundtrip_binds_pipeline_and_dependency(native_rows, tmp_path):
    model = fit(learner(), native_rows)
    path = tmp_path/"direction.joblib"
    model.save(path)
    loaded = NativeDirectionLearner.load(path, preprocessing_id=IDENTITY)
    V = native_rows[2]
    np.testing.assert_array_equal(model.predict_margin(V, preprocessing_id=IDENTITY),
                                  loaded.predict_margin(V, preprocessing_id=IDENTITY))
    with pytest.raises(DataContractError, match="identity"):
        loaded.predict_margin(V, preprocessing_id="b"*64)
    with pytest.raises(DataContractError, match="pipeline"):
        NativeDirectionLearner.load(path, preprocessing_id="b"*64)
    with pytest.raises(DataContractError, match="already exists"):
        model.save(path)
    payload = joblib.load(path)
    payload["dependency_versions"]["xgboost"] = "incompatible"
    changed = tmp_path/"changed.joblib"
    joblib.dump(payload, changed)
    with pytest.raises(DataContractError, match="dependency"):
        NativeDirectionLearner.load(changed, preprocessing_id=IDENTITY)


@pytest.mark.parametrize("field", ["parameter", "patience"])
def test_load_rejects_corrupted_training_metadata(native_rows, tmp_path, field):
    model = fit(learner(), native_rows)
    path = tmp_path/"direction.joblib"
    model.save(path)
    payload = joblib.load(path)
    if field == "parameter":
        payload["params"]["max_depth"] = 9
    else:
        payload["patience"] = 10
    changed = tmp_path/"changed.joblib"
    joblib.dump(payload, changed)
    with pytest.raises(DataContractError, match="metadata mismatch"):
        NativeDirectionLearner.load(changed, preprocessing_id=IDENTITY)


@pytest.mark.parametrize("params", [{"objective":"reg:squarederror"},
                                    {"eval_metric":"rmse"},
                                    {"early_stopping_rounds":1}])
def test_rejects_inconsistent_task_or_callback(params):
    with pytest.raises(DataContractError):
        NativeDirectionLearner(preprocessing_id=IDENTITY, params=params)
