# Grouped feature permutation diagnostic

The all-feature inventory was followed by a single validation diagnostic: each
semantic feature family was permuted as a group across validation rows and the
direction accuracy was recomputed for 20 fixed-seed repetitions per saved
model. This is a screening signal only; row permutation breaks temporal order,
so it cannot be used as a forward promotion result.

Mean accuracy deltas (permuted minus baseline) were most negative for momentum
(`-0.109pp`), ATR (`-0.066pp`) and volatility (`-0.059pp`), indicating that
these families carry useful predictive information in validation. RSI had a
positive permutation delta (`+0.180pp`), consistent with the prior RSI removal
ablation being directionally positive, but neither result is independent
forward evidence.

The diagnostic is used only to prioritize a pre-registered family experiment;
paired chronological direction accuracy and block bootstrap remain the gate.

