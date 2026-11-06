"""Time-safe volatility-6/24 ablation with lag-return baseline.

Removes only volatility-6/24 while retaining lag-return baseline.
This is a research runner; it never edits production features or model caches.
"""
import json
import sys
import joblib
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from xgboost import XGBRegressor
from freqtrade.freqai.freqai_interface import IFreqaiModel
from quant.training.native_isolation import IdentityPreservingPipeline

ROOT = Path("artifacts/direction-threshold-study/rolling")
EXTENDED = Path("artifacts/direction-threshold-study/extended")
LAGS = (1, 2, 3, 6)


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    cfg = json.loads(Path("config.json").read_text())
    rows = []
    audits = []
    for week_dir in sorted((p for p in ROOT.glob("week-*") if p.is_dir()),
                           key=lambda p: int(p.name.split("-")[1])):
        week = int(week_dir.name.split("-")[1])
        model_dirs = sorted((week_dir / "userdir/models").glob("*/sub-train-*"))
        for model_dir in model_dirs:
            pair_symbol = model_dir.name.split("-")[2].split("_")[0]
            metadata = json.loads(next(model_dir.glob("*_metadata.json")).read_text())
            audit = next((model_dir / "native_training_audit").glob("*"))
            samples = pd.read_parquet(audit / "samples.parquet")
            samples.index = samples.source_index.astype(int)
            train = pd.read_parquet(audit / "train_before_preprocessing.parquet")
            valid = pd.read_parquet(audit / "test_before_preprocessing.parquet")
            label = metadata["label_list"][0]
            features = metadata["training_features_list"]
            source = pd.read_feather(Path("data/futures") /
                f"{pair_symbol}_USDT_USDT-4h-futures.feather")
            source["date"] = pd.to_datetime(source["date"], utc=True)
            source = source.set_index("date")
            lagged = pd.DataFrame({f"%-lag-return-{n}": source["close"].pct_change(n)
                                   for n in LAGS})

            def augmented(frame: pd.DataFrame, dates) -> pd.DataFrame:
                index = pd.DatetimeIndex(pd.to_datetime(dates, utc=True))
                result = frame[kept].copy()
                result.index = index
                result[lagged.columns] = lagged.reindex(index).to_numpy()
                return result.reset_index(drop=True)

            kept = [c for c in features if c not in ("%-volatility-6", "%-volatility-24")]
            train_dates = samples.loc[train.index, "candle_timestamp"]
            valid_dates = samples.loc[valid.index, "candle_timestamp"]
            tr = augmented(train, train_dates)
            va = augmented(valid, valid_dates)
            label_pipeline = joblib.load(next(model_dir.glob("*_label_pipeline.pkl")))
            ytr = label_pipeline.inverse_transform(train[[label]])[0].iloc[:, 0].to_numpy(float)
            yv = label_pipeline.inverse_transform(valid[[label]])[0].iloc[:, 0].to_numpy(float)
            factory = IFreqaiModel.define_data_pipeline(
                SimpleNamespace(freqai_info=cfg["freqai"]), threads=1)
            pipeline = IdentityPreservingPipeline(factory.steps, factory.fitparams)
            X, y, weights = pipeline.fit_transform(
                tr, pd.DataFrame({label: ytr}), train.sample_weight.to_numpy())
            V, vy, vw = pipeline.transform(
                va, pd.DataFrame({label: yv}), valid.sample_weight.to_numpy())
            saved = joblib.load(next(model_dir.glob("*_model.joblib")))
            params = saved.get_params()
            params.update(n_estimators=300, early_stopping_rounds=30)
            params.pop("eval_metric", None)
            candidate = XGBRegressor(**params, eval_metric="rmse")
            candidate.fit(X, y[label], sample_weight=weights,
                          eval_set=[(V, vy[label])],
                          sample_weight_eval_set=[vw], verbose=False)
            prediction = pd.read_parquet(model_dir / "populated_prediction.parquet").iloc[:42].copy()
            dates = pd.to_datetime(prediction.date, utc=True)
            P, ready, _ = pipeline.transform(augmented(prediction, dates), outlier_check=True)
            score = candidate.predict(P)
            baseline = pd.read_parquet(EXTENDED / f"20260101-{pair_symbol}.parquet")
            baseline = baseline[baseline.new].copy()
            baseline["date"] = pd.to_datetime(baseline.date, utc=True)
            baseline = baseline.set_index("date")
            assert dates.is_unique and dates.isin(baseline.index).all()
            truth = baseline.loc[dates, "truth"].to_numpy(float)
            assert len(ready) == len(dates)
            rows.extend({"week": week, "pair": pair_symbol, "date": str(date),
                         "truth": float(t), "prediction": float(p),
                         "ready": int(r), "correct": bool(np.sign(p) == np.sign(t))}
                        for date, t, p, r in zip(dates, truth, score, ready))
            audits.append({"week": week, "pair": pair_symbol,
                           "train_n": len(X), "valid_n": len(V), "prediction_n": len(score),
                           "feature_n": len(X.columns), "removed": ["%-volatility-6", "%-volatility-24"],
                           "baseline": "lag_return_1/2/3/6",
                           "ready_n": int(np.asarray(ready).sum()),
                           "best_iteration": int(candidate.best_iteration)})
    result = pd.DataFrame(rows)
    result.to_parquet(output / "predictions.parquet", index=False)
    (output / "audit.json").write_text(json.dumps(audits, indent=2))
    selected = result[result.ready == 1]
    print("lag-volatility-ablation", int(selected.correct.sum()), len(selected),
          float(selected.correct.mean()), "coverage", len(selected) / len(result))
    print(selected.groupby(["week", "pair"]).correct.mean().to_string())


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=Path("artifacts/direction-threshold-study/lag-volatility-ablation-v1"))
    args = parser.parse_args()
    run(args.output)
