# Native direction condition-drift diagnostic

## Question and protocol

The narrow question was whether the direction model's train-to-validation
accuracy loss is explained by changing class prior, a shifted 0.5 probability
boundary, or a reversal in score ordering. The fixed H8 learners were replayed
without refitting. Each pair's training window was split into four chronological
blocks and its early-stopping validation window into six blocks. At every
block boundary, rows whose label maturity reached the next block's availability
time were purged. No outer forecast truth was read; no threshold or model was
selected.

The training rows are in-sample fit diagnostics. Validation rows participated
in early stopping and are selection diagnostics, not independent confirmation.
Results are descriptive because blocks are short and adjacent 3-bar labels
overlap. Reproduction: `tools/diagnose_condition_drift.py`; machine-readable
output: `artifacts/native-direction-audit/condition-drift-diagnostic.json`.

## Results

| H8 window | Split | Mature rows | Direction accuracy | Nonzero AUC | Truth up rate | Predicted up rate |
|---|---|---:|---:|---:|---:|---:|
| 2023 replication | Train, in-sample | 5,211 | 62.03% | 0.6780 | 49.90% | 48.92% |
| 2023 replication | Validation, early-stop | 1,269 | 52.43% | 0.5509 | 48.70% | 39.87% |
| 2024 replication | Train, in-sample | 5,211 | 66.91% | 0.7480 | 51.48% | 61.43% |
| 2024 replication | Validation, early-stop | 1,269 | 57.07% | 0.5940 | 52.68% | 71.10% |

The validation class prior changes only modestly between these replications,
while the model's predicted-up rate moves from underprediction in 2023 to
overprediction in 2024. Validation AUC remains above 0.5 when averaged by pair
in both windows. This pattern is more consistent with a material score-boundary
or calibration shift than with a uniform loss of ranking ability. It does not
establish that boundary correction will improve direction accuracy: earlier
intercept and prior adjustments already failed to produce stable gains.

Some individual short blocks have AUC below 0.5, but with roughly 70 samples per
pair-block those reversals are weak evidence and are not consistent enough to
claim conditional relationship reversal. The D4 conditional-drift hypothesis
is therefore not confirmed by this diagnostic. No model/configuration change
or promotion follows.

## Decision and basis

Do not add a regime-aware feature or retrain by regime based on these results.
The next experiment must target a mechanism not already exhausted by prior,
intercept, and threshold controls, and must use a frozen time-forward protocol.
Promotion still requires paired direction-accuracy improvement; AUC and
probability diagnostics explain possible failure modes only.

Method references: Moreno-Torres et al. (2012), *A unifying view on dataset
shift in classification*, DOI `10.1016/j.patcog.2011.06.019`; Tashman (2000),
*Out-of-sample tests of forecasting accuracy*, DOI `10.1016/S0169-2070(00)00065-0`;
Cawley and Talbot (2010), *On Over-fitting in Model Selection and Subsequent
Selection Bias in Performance Evaluation*, JMLR 11. These motivate separating
prior, conditional, and selection effects; they do not prove a project-specific
cause.
