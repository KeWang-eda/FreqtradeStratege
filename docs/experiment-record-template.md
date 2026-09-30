# Experiment record template

## Metadata

- Experiment ID: `EXP-XXX`
- Branch: `experiment/EXP-XXX-name`
- Parent branch: `main`
- Parent commit:
- Todoist task:
- Status: `proposed / running / promoted / rejected / blocked`

## Layer scope

- Primary layer:
- Contract module:
- Integration point:
- Independent validation command:
- Combined validation command:

## Hypothesis and single variable

- Hypothesis:
- Single variable:
- Parent value:
- Candidate value:
- Explicitly unchanged:

## Run protocol

- Freqtrade version or commit:
- Python version:
- Timeframe:
- Timerange:
- Pairlist:
- Initial balance:
- Leverage:
- Fee:
- Funding-rate source:
- Maximum open trades:
- FreqAI identifier:
- Data snapshot:
- Feature version:
- Label version:

## Commands and checks

```text
Parent control command:
Candidate command:
Layer validation command:
Metrics command:
```

- [ ] Strategy loads.
- [ ] Layer contract checks pass.
- [ ] Smoke run passes.
- [ ] Parent control group is rerun.
- [ ] Candidate is run.
- [ ] No unresolved `ERROR`, `Traceback`, time shift, or model-path failure.
- [ ] Result artifacts and hashes are recorded.

## Results

| Metric | Parent | Candidate | Change |
|---|---:|---:|---:|
| Wallet Sharpe | | | |
| Wallet Calmar | | | |
| Wallet Sharpe × Calmar | | | |
| Maximum relative drawdown | | | |
| Return | | | |
| Trade count | | | |
| Layer-specific metric | | | |

## Promotion decision

- Candidate product greater than parent product:
- Maximum relative drawdown below 30%:
- Independent window reproduced:
- DSR/PBO or other statistical gate:
- Decision: `promoted / rejected / blocked`
- Evidence:

## Conclusion

Write the result, limitations, and the next experiment. Do not describe an unrun backtest as successful.
