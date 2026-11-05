"""Training-only redundancy audit for an Alpha#12-inspired time-series term.

This is a candidate-screening diagnostic, not an OOS model experiment.  It
uses only the already frozen native training snapshots and never reads the
development/outer truth files.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import json
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

ROOT = Path("artifacts/direction-threshold-study/rolling/week-1/userdir/models")
OUT = Path("artifacts/direction-feature-study")
PAIRS = ("BTC", "ETH", "BNB")

rows = []
protocol = {
    "scope": "training-only descriptive redundancy audit",
    "candidate": "-sign(volume.diff(1))*close.diff(1)",
    "formula": "-sign(volume[t]-volume[t-1])*(close[t]-close[t-1])",
    "features_compared": ["return", "volume-change", "candidate"],
    "periods": 4,
    "label_purge": "exclude rows whose label_end_time crosses next segment available_at",
    "outer_labels_read": False,
    "selection": "none; no production decision",
}
(OUT / "alpha12-redundancy-protocol.json").write_text(json.dumps(protocol, indent=2))

for pair in PAIRS:
    model_dir = next(ROOT.glob(f"*/sub-train-{pair}_*"))
    metadata = json.loads(next(model_dir.glob("*_metadata.json")).read_text())
    audit = model_dir / metadata["native_training_audit"]
    data = pd.read_parquet(audit / "train_after_preprocessing.parquet")
    before = pd.read_parquet(audit / "train_before_preprocessing.parquet")
    pipeline = joblib.load(next(model_dir.glob("*_label_pipeline.pkl")))
    label_values = pipeline.inverse_transform(data[["&-s_return"]])[0].iloc[:, 0].to_numpy()
    label = pd.Series(label_values, index=data.index)
    np.testing.assert_allclose(label.to_numpy(), before.loc[data.index, "&-s_return"], rtol=1e-6, atol=1e-6)
    samples = pd.read_parquet(audit / "samples.parquet")
    samples["source_index"] = samples.source_index.astype(int)
    meta = samples.set_index("source_index").loc[data.index].sort_values("candle_timestamp")
    data = data.loc[meta.index]
    label = label.loc[meta.index]
    close = data[f"%-return_gen_{pair}/USDTUSDT_4h"]
    volume = data[f"%-volume-change_gen_{pair}/USDTUSDT_4h"]
    # Return is already close.pct_change(1); use the exact raw OHLC values
    # only where available in the native audit to avoid inventing a new scale.
    candidate = -np.sign(volume) * close
    for segment, positions in enumerate(np.array_split(np.arange(len(data)), 4), 1):
        segment_meta = meta.iloc[positions]
        keep = np.ones(len(positions), dtype=bool)
        if segment < 4:
            keep = (segment_meta.label_end_time < meta.iloc[positions[-1] + 1].available_at).to_numpy()
        index = data.index[positions[keep]]
        values = {"return": close.loc[index], "volume-change": volume.loc[index], "candidate": candidate.loc[index]}
        truth = label.loc[index]
        for name, value in values.items():
            valid = value.notna() & truth.notna()
            auc = roc_auc_score(truth.loc[valid] > 0, value.loc[valid]) if (truth.loc[valid] > 0).nunique() == 2 else None
            rows.append({"pair": pair, "segment": segment, "feature": name, "n": int(valid.sum()),
                         "spearman_with_return": float(value.corr(close.loc[index], method="spearman")),
                         "spearman_with_volume_change": float(value.corr(volume.loc[index], method="spearman")),
                         "auc": auc})

pd.DataFrame(rows).to_csv(OUT / "alpha12-redundancy.csv", index=False)
print(pd.DataFrame(rows).to_string(index=False))
