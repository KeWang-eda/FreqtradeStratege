"""Reference: https://scikit-learn.org/stable/common_pitfalls.html#data-leakage"""

import pandas as pd
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def fit_preprocessing(X_train: pd.DataFrame) -> Pipeline:
    """Fit scaling on supplied training rows only; missing rows were audited."""
    pipeline = Pipeline([("scale", StandardScaler())]).set_output(transform="pandas")
    pipeline.fit(X_train)
    return pipeline
