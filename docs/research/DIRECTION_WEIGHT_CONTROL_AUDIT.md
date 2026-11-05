# Direction accuracy: recency-weight control

## Question

Does the existing FreqAI recency sample weighting improve out-of-sample
direction accuracy?

## Protocol

The experiment used the same three forward splits, rows, features, XGBoost
parameters, seed, and `logloss` early stopping in both arms. The `weighted`
arm used the existing recency weights; `unweighted` set both training and
early-stopping evaluation weights to equal weights. Accuracy was then scored
as an unweighted count of `sign(prediction) == sign(future return)` on the
same 3,927 forward observations.

This is a joint intervention on training loss and weighted early-stopping
evaluation. FreqAI's `set_weights_higher_recent` implements exponential
sample weights, and XGBoost applies `sample_weight` and
`sample_weight_eval_set` to training and evaluation respectively.

## Result

| arm | direction accuracy |
|---|---:|
| weighted | 51.5915% |
| unweighted | 51.5915% |

The paired comparison had 288 observations improved and 288 worsened. The
bootstrap confidence intervals for the unweighted-minus-weighted difference
were [-1.375, 1.401] percentage points (6-row blocks), [-1.248, 1.325] points
(12-row blocks), and [-1.299, 1.222] points (24-row blocks). Every interval
includes zero.

## Decision

Reject the hypothesis that recency weighting improves direction accuracy.
Keep the current production setting unchanged. This experiment provides no
evidence for a direction-accuracy gain.

## References

- Freqtrade FreqAI parameter table and `set_weights_higher_recent` behavior.
- XGBoost Python API documentation for `sample_weight` and
  `sample_weight_eval_set`.
