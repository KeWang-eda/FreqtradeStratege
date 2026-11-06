"""Export all saved XGBoost feature importances without changing predictions.

This is a research-only inventory. Gain/weight/cover are training
descriptions, not promotion evidence; candidates still require paired forward
evaluation. Outputs are written outside model directories and are keyed by the
saved model/schema hashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import joblib
import pandas as pd


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(root: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    rows = []
    for model_dir in sorted(root.glob("week-*/userdir/models/*/sub-train-*")):
        metadata_path = next(model_dir.glob("*_metadata.json"), None)
        model_path = next(model_dir.glob("*_model.joblib"), None)
        if metadata_path is None or model_path is None:
            continue
        metadata = json.loads(metadata_path.read_text())
        model = joblib.load(model_path)
        booster = model.get_booster()
        names = list(metadata["training_features_list"])
        gain = booster.get_score(importance_type="gain")
        weight = booster.get_score(importance_type="weight")
        cover = booster.get_score(importance_type="cover")
        total_gain = sum(float(v) for v in gain.values()) or 1.0
        model_hash = sha256(model_path)
        schema_hash = hashlib.sha256("\n".join(names).encode()).hexdigest()
        pair = metadata.get("pair", model_dir.name.split("-")[2].replace("_", "/"))
        week = model_dir.parts[-4]
        for rank, feature in enumerate(names, 1):
            rows.append({
                "week": week,
                "pair": pair,
                "model_path": model_path.as_posix(),
                "model_sha256": model_hash,
                "schema_sha256": schema_hash,
                "feature": feature,
                "gain": float(gain.get(feature, 0.0)),
                "gain_fraction": float(gain.get(feature, 0.0)) / total_gain,
                "weight": float(weight.get(feature, 0.0)),
                "cover": float(cover.get(feature, 0.0)),
                "schema_position": rank,
            })
    frame = pd.DataFrame(rows)
    frame.to_csv(output / "feature_importance.csv", index=False)
    summary = (frame.groupby("feature", as_index=False)
               .agg(models=("model_sha256", "nunique"),
                    mean_gain_fraction=("gain_fraction", "mean"),
                    mean_weight=("weight", "mean"),
                    mean_cover=("cover", "mean"))
               .sort_values("mean_gain_fraction", ascending=False))
    summary.to_csv(output / "feature_importance_summary.csv", index=False)
    (output / "protocol.json").write_text(json.dumps({
        "scope": "research_only_training_importance_inventory",
        "importance_types": ["gain", "weight", "cover"],
        "models": int(frame.model_sha256.nunique()) if not frame.empty else 0,
        "features": int(frame.feature.nunique()) if not frame.empty else 0,
        "promotion_rule": "importance selects hypotheses; paired temporal direction evaluation is required",
        "reference": "XGBoost parameter documentation: feature importance and tree booster statistics",
    }, indent=2))
    print(f"exported {len(frame)} feature/model rows to {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("artifacts/direction-threshold-study/rolling"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/direction-threshold-study/feature-importance-v1"))
    args = parser.parse_args()
    run(args.root, args.output)
