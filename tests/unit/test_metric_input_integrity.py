"""Evaluation may not silently turn missing predictions into a better sample."""

import numpy as np
import pytest

from quant_strategy.validation import prediction_metrics


@pytest.mark.parametrize(
    "truth,predicted", [([1, 2], [1, np.nan]), ([np.inf], [0]), ([0], [-np.inf])]
)
def test_nonfinite_metric_input_is_an_error_not_a_filtered_success(truth, predicted):
    with pytest.raises(ValueError, match="finite"):
        prediction_metrics(truth, predicted)


def test_prediction_metrics_match_hand_calculation_without_sample_filtering():
    result = prediction_metrics([1, -1, 3], [2, -1, 1])
    assert result["n"] == 3
    assert result["mae"] == 1
    assert result["rmse"] == pytest.approx(np.sqrt(5 / 3))
    assert result["direction_accuracy"] == 1
