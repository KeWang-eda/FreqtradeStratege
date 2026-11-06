"""Aggregate the all-model importance inventory by stable feature family."""
from pathlib import Path
import argparse
import pandas as pd


FAMILIES = {
    "atr": "atr-ratio", "rsi": "rsi", "ema": "ema-distance",
    "sma": "sma-distance", "momentum": "momentum", "relative-volume": "relative-volume",
    "volume-change": "volume-change", "return": "return", "body": "body",
    "range": "range", "volatility": "volatility", "calendar": "hour|day-of-week",
    "lag-return": "lag-return",
}


def family(name: str) -> str:
    for label, token in FAMILIES.items():
        if any(part in name for part in token.split("|")):
            return label
    return "other"


def run(source: Path, output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    frame = pd.read_csv(source)
    frame["family"] = frame.feature.map(family)
    frame["used"] = frame.gain > 0
    grouped = frame.groupby(["family", "pair"], as_index=False).agg(
        models=("model_sha256", "nunique"), features=("feature", "nunique"),
        mean_gain_fraction=("gain_fraction", "mean"),
        median_gain_fraction=("gain_fraction", "median"),
        gain_iqr=("gain_fraction", lambda x: float(x.quantile(.75)-x.quantile(.25))),
        nonzero_usage=("used", "mean"), mean_weight=("weight", "mean"),
    ).sort_values(["pair", "mean_gain_fraction"], ascending=[True, False])
    grouped.to_csv(output / "family_importance_by_pair.csv", index=False)
    overall = frame.groupby("family", as_index=False).agg(
        models=("model_sha256", "nunique"), features=("feature", "nunique"),
        mean_gain_fraction=("gain_fraction", "mean"),
        median_gain_fraction=("gain_fraction", "median"),
        gain_iqr=("gain_fraction", lambda x: float(x.quantile(.75)-x.quantile(.25))),
        nonzero_usage=("used", "mean"), mean_weight=("weight", "mean"),
    ).sort_values("mean_gain_fraction", ascending=False)
    overall.to_csv(output / "family_importance_summary.csv", index=False)
    print(overall.to_string(index=False))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, default=Path("artifacts/direction-threshold-study/feature-importance-v1/feature_importance.csv"))
    p.add_argument("--output", type=Path, default=Path("artifacts/direction-threshold-study/feature-family-importance-v1"))
    a = p.parse_args(); run(a.source, a.output)
