import numpy as np

from quant.backends.standalone import StandaloneBackend


def test_weight_factor_mean_normalization_preserves_relative_weights():
    weights = np.exp(-np.arange(100, dtype=float) / (0.9 * 100))[::-1]
    normalized = weights / weights.mean()
    assert np.isclose(normalized.mean(), 1.0)
    np.testing.assert_allclose(normalized / normalized[-1], weights / weights[-1])
