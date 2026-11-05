"""Training/validation block diagnostic for conditional direction drift.

Read-only: replays saved native direction learners, never reads outer forecast
truth and never selects a threshold or model.
"""
from pathlib import Path
import json
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
from sklearn.metrics import balanced_accuracy_score, log_loss, roc_auc_score

from quant.infrastructure.experiment_store import file_hash
from quant.models.native_direction import NativeDirectionLearner

SOURCE = Path("artifacts/native-direction-audit/binary-logloss-learner-replication")
SNAPSHOTS = Path("artifacts/native-prediction-study/runs")
OUTPUT = Path("artifacts/native-direction-audit/condition-drift-diagnostic.json")


def block_metrics(y, margin):
    y = np.asarray(y, dtype=float)
    margin = np.asarray(margin, dtype=float)
    p = np.clip((margin + 1.0) / 2.0, 1e-7, 1 - 1e-7)
    binary = (y > 0).astype(int)
    nz = y != 0
    return {
        "n": int(len(y)),
        "truth_positive_rate": float(binary.mean()),
        "prediction_positive_rate": float((margin > 0).mean()),
        "accuracy": float((np.sign(margin) == np.sign(y)).mean()),
        "balanced_accuracy": float(balanced_accuracy_score(binary, margin > 0)),
        "auc_nonzero": float(roc_auc_score(binary[nz], p[nz])) if nz.sum() and np.unique(binary[nz]).size == 2 else None,
        "logloss": float(log_loss(binary, p, labels=[0, 1])),
        "mean_residual_y_minus_p": float((binary - p).mean()),
        "median_probability": float(np.median(p)),
    }


def run():
    rows = []
    for period in ("base-20230701-direction-confirm1", "base-20240701-direction-confirm1"):
        report = json.loads((SNAPSHOTS / period / "training_run.json").read_text())
        for info in report["pairs"]:
            pair = info["pair"]
            symbol = pair.split("/")[0]
            directory = SNAPSHOTS / period / info["model_directory"]
            metadata = json.loads(next(directory.glob("*metadata.json")).read_text())
            audit = directory / metadata["native_training_audit"]
            pipeline = next(directory.glob("*feature_pipeline.pkl"))
            identity = file_hash(pipeline)
            learner = NativeDirectionLearner.load(SOURCE / f"{period}-{symbol}-learner.joblib", preprocessing_id=identity)
            sample = pd.read_parquet(audit / "samples.parquet")
            sample.index = sample.source_index.astype(int)
            if not sample.index.is_unique:
                raise ValueError("duplicate source index")
            for name, prefix, count in (("train", "train", 4), ("validation", "test", 6)):
                features = pd.read_parquet(audit / f"{prefix}_after_preprocessing.parquet")
                raw = pd.read_parquet(audit / f"{prefix}_before_preprocessing.parquet")
                timing = sample.loc[features.index].sort_values("candle_timestamp")
                features = features.loc[timing.index]
                y = raw.loc[timing.index, metadata["label_list"][0]].to_numpy(float)
                margin = learner.predict_margin(features.loc[:, list(learner.columns)], preprocessing_id=identity)
                for block, positions in enumerate(np.array_split(np.arange(len(features)), count), 1):
                    m = timing.iloc[positions]
                    keep = np.ones(len(positions), dtype=bool)
                    if block < count:
                        next_available = timing.iloc[positions[-1] + 1].available_at
                        keep = (pd.to_datetime(m.label_end_time, utc=True) < next_available).to_numpy()
                    selected = positions[keep]
                    if len(selected) == 0:
                        raise ValueError("maturity purge removed an entire block")
                    row = block_metrics(y[selected], margin[selected])
                    row.update({"period": period, "pair": pair, "split": name, "block": block,
                                "first_candle": str(timing.iloc[selected[0]].candle_timestamp),
                                "last_candle": str(timing.iloc[selected[-1]].candle_timestamp),
                                "last_label_end": str(pd.to_datetime(timing.iloc[selected].label_end_time, utc=True).max()),
                                "maturity_purged": int(len(positions) - len(selected)),
                                "prediction_role": "in-sample fit diagnostic" if name == "train" else "early-stopping selection diagnostic"})
                    rows.append(row)
    result = {"scope": "reused historical training/validation only; diagnostic, not OOS",
              "primary_metric": "direction accuracy; other metrics explain drift",
              "block_protocol": {"train": 4, "validation": 6}, "outer_forecast_truth_read": False,
              "rows": rows}
    OUTPUT.write_text(json.dumps(result, indent=2, allow_nan=False))
    print(pd.DataFrame(rows).to_string(index=False))


if __name__ == "__main__":
    run()
