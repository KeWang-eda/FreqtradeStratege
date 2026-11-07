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


def run(output: Path, remove: tuple[str, ...], add_bollinger: bool = False, add_clv: bool = False, add_stoch: bool = False, add_obv: bool = False, add_cmf: bool = False, add_vfi: bool = False) -> None:
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
            bb_mean = source["close"].rolling(20).mean()
            bb_std = source["close"].rolling(20).std().replace(0.0, np.nan)
            bollinger = ((source["close"] - bb_mean) / (2.0 * bb_std)).rename("%-bollinger-position-20")
            clv = ((2.0 * source["close"] - source["high"] - source["low"]) /
                   (source["high"] - source["low"]).replace(0.0, np.nan)).rename("%-clv")
            stoch_low = source["low"].rolling(14).min(); stoch_high = source["high"].rolling(14).max()
            stoch = ((source["close"] - stoch_low) / (stoch_high - stoch_low).replace(0.0, np.nan)).rename("%-stoch-position-14")
            obv = (np.sign(source["close"].diff()) * source["volume"]).rolling(14).sum() / source["volume"].rolling(14).sum().replace(0.0, np.nan)
            obv = obv.rename("%-obv-pressure-14")
            cmf = (((2.0 * source["close"] - source["high"] - source["low"]) /
                    (source["high"] - source["low"]).replace(0.0, np.nan)) * source["volume"]).rolling(14).sum() / source["volume"].rolling(14).sum().replace(0.0, np.nan)
            cmf = cmf.rename("%-cmf-14")
            # VFI-hist follows technical 1.7.0's causal VFI implementation.
            # Keep this research arm isolated: only the histogram is added.
            import technical.indicators as indicators
            _, _, vfi_hist = indicators.vfi(source.reset_index()[["date", "open", "high", "low", "close", "volume"]])
            vfi_hist = pd.Series(np.asarray(vfi_hist), index=source.index, name="%-vfi-hist")

            # `remove` entries are stable substrings so generated native
            # families (e.g. range_gen and range_gen_shift-1) are removed
            # together while exact calendar/volatility names still work.
            kept = [c for c in features if not any(token in c for token in remove)]

            def augmented(frame: pd.DataFrame, dates, columns, include_bollinger: bool = False, include_clv: bool = False, include_stoch: bool = False, include_obv: bool = False, include_cmf: bool = False) -> pd.DataFrame:
                index = pd.DatetimeIndex(pd.to_datetime(dates, utc=True))
                base_columns = [c for c in columns if c not in {"%-bollinger-position-20", "%-clv", "%-stoch-position-14", "%-obv-pressure-14", "%-cmf-14", "%-vfi-hist"}]
                result = frame[base_columns].copy()
                result.index = index
                result[lagged.columns] = lagged.reindex(index).to_numpy()
                if include_bollinger:
                    result["%-bollinger-position-20"] = bollinger.reindex(index).to_numpy()
                if include_clv:
                    result["%-clv"] = clv.reindex(index).to_numpy()
                if include_stoch:
                    result["%-stoch-position-14"] = stoch.reindex(index).to_numpy()
                if include_obv:
                    result["%-obv-pressure-14"] = obv.reindex(index).to_numpy()
                if include_cmf:
                    result["%-cmf-14"] = cmf.reindex(index).to_numpy()
                if add_vfi and columns is candidate_columns:
                    result["%-vfi-hist"] = vfi_hist.reindex(index).to_numpy()
                return result.reset_index(drop=True)

            train_dates = samples.loc[train.index, "candle_timestamp"]
            valid_dates = samples.loc[valid.index, "candle_timestamp"]
            label_pipeline = joblib.load(next(model_dir.glob("*_label_pipeline.pkl")))
            ytr = label_pipeline.inverse_transform(train[[label]])[0].iloc[:, 0].to_numpy(float)
            yv = label_pipeline.inverse_transform(valid[[label]])[0].iloc[:, 0].to_numpy(float)
            factory = IFreqaiModel.define_data_pipeline(
                SimpleNamespace(freqai_info=cfg["freqai"]), threads=1)
            saved = joblib.load(next(model_dir.glob("*_model.joblib")))
            params = saved.get_params()
            params.update(n_estimators=300, early_stopping_rounds=30)
            params.pop("eval_metric", None)
            prediction = pd.read_parquet(model_dir / "populated_prediction.parquet").iloc[:42].copy()
            dates = pd.to_datetime(prediction.date, utc=True)
            baseline = pd.read_parquet(EXTENDED / f"20260101-{pair_symbol}.parquet")
            baseline = baseline[baseline.new].copy()
            baseline["date"] = pd.to_datetime(baseline.date, utc=True)
            baseline = baseline.set_index("date")
            assert dates.is_unique and dates.isin(baseline.index).all()
            truth = baseline.loc[dates, "truth"].to_numpy(float)
            arm_scores = {}
            arm_ready = {}
            candidate_columns = kept + (["%-bollinger-position-20"] if add_bollinger else []) + (["%-clv"] if add_clv else []) + (["%-stoch-position-14"] if add_stoch else []) + (["%-obv-pressure-14"] if add_obv else []) + (["%-cmf-14"] if add_cmf else []) + (["%-vfi-hist"] if add_vfi else [])
            for arm, columns in (("lag_baseline", features), ("lag_candidate", candidate_columns)):
                pipeline = IdentityPreservingPipeline(factory.steps, factory.fitparams)
                X, y, weights = pipeline.fit_transform(
                    augmented(train, train_dates, columns, add_bollinger and arm == "lag_candidate", add_clv and arm == "lag_candidate", add_stoch and arm == "lag_candidate", add_obv and arm == "lag_candidate", add_cmf and arm == "lag_candidate"), pd.DataFrame({label: ytr}),
                    train.sample_weight.to_numpy())
                V, vy, vw = pipeline.transform(
                    augmented(valid, valid_dates, columns, add_bollinger and arm == "lag_candidate", add_clv and arm == "lag_candidate", add_stoch and arm == "lag_candidate", add_obv and arm == "lag_candidate", add_cmf and arm == "lag_candidate"), pd.DataFrame({label: yv}),
                    valid.sample_weight.to_numpy())
                learner = XGBRegressor(**params, eval_metric="rmse")
                learner.fit(X, y[label], sample_weight=weights,
                            eval_set=[(V, vy[label])], sample_weight_eval_set=[vw], verbose=False)
                P, ready, _ = pipeline.transform(augmented(prediction, dates, columns, add_bollinger and arm == "lag_candidate", add_clv and arm == "lag_candidate", add_stoch and arm == "lag_candidate", add_obv and arm == "lag_candidate", add_cmf and arm == "lag_candidate"), outlier_check=True)
                arm_scores[arm] = learner.predict(P)
                arm_ready[arm] = np.asarray(ready, dtype=bool)
                assert len(ready) == len(dates)
            common = arm_ready["lag_baseline"] & arm_ready["lag_candidate"]
            for date, t, bp, cp, ready in zip(dates, truth, arm_scores["lag_baseline"], arm_scores["lag_candidate"], common):
                rows.append({"week": week, "pair": pair_symbol, "date": str(date), "truth": float(t),
                             "baseline_prediction": float(bp), "candidate_prediction": float(cp),
                             "ready": int(ready), "baseline_correct": bool(np.sign(bp) == np.sign(t)),
                             "candidate_correct": bool(np.sign(cp) == np.sign(t))})
            audits.append({"week": week, "pair": pair_symbol,
                           "train_n": len(train), "valid_n": len(valid), "prediction_n": len(dates),
                           "baseline_features": len(features) + len(LAGS), "candidate_features": len(kept) + len(LAGS),
                           "removed": list(remove), "ready_n": int(common.sum())})
    result = pd.DataFrame(rows)
    result.to_parquet(output / "predictions.parquet", index=False)
    (output / "audit.json").write_text(json.dumps(audits, indent=2))
    selected = result[result.ready == 1]
    print("paired", int(selected.baseline_correct.sum()), int(selected.candidate_correct.sum()), len(selected),
          float(selected.baseline_correct.mean()), float(selected.candidate_correct.mean()))
    print(selected.groupby(["week", "pair"])[["baseline_correct", "candidate_correct"]].mean().to_string())
    # Synchronized circular block bootstrap on date-level paired deltas.
    # A date block is one 4h candle; all pairs at that date stay together.
    dates = sorted(selected.date.unique())
    delta = selected.assign(delta=selected.candidate_correct.astype(int) - selected.baseline_correct.astype(int))
    by_date = delta.groupby("date").delta.sum().reindex(dates).to_numpy(float) / 3.0
    rng = np.random.default_rng(42)
    reps = []
    block = 12
    for _ in range(5000):
        starts = rng.integers(0, len(by_date), size=int(np.ceil(len(by_date) / block)))
        sample = np.concatenate([by_date[np.arange(s, s + block) % len(by_date)] for s in starts])[:len(by_date)]
        reps.append(float(sample.mean()))
    lo, hi = np.quantile(reps, [0.025, 0.975])
    print("bootstrap_block12_delta_pp", float(delta.delta.mean() * 100), float(lo * 100), float(hi * 100))


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path,
                        default=Path("artifacts/direction-threshold-study/lag-volatility-ablation-v1"))
    parser.add_argument("--remove", default="%-volatility-6,%-volatility-24",
                        help="Comma-separated feature columns to remove")
    parser.add_argument("--add-bollinger", action="store_true")
    parser.add_argument("--add-clv", action="store_true")
    parser.add_argument("--add-stoch", action="store_true")
    parser.add_argument("--add-obv", action="store_true")
    parser.add_argument("--add-cmf", action="store_true")
    parser.add_argument("--add-vfi", action="store_true")
    args = parser.parse_args()
    run(args.output, tuple(x for x in args.remove.split(",") if x), args.add_bollinger, args.add_clv, args.add_stoch, args.add_obv, args.add_cmf, args.add_vfi)
