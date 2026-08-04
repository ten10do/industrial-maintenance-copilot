# Fault F2 - V1 plus train-only condition normalization

- Scope: same Development-only protocol; every condition baseline is fit from healthy rows in the training fold only.
- No candidate passed both gates.
- Best failed candidate: `fault-f2-random_forest-0fc07eeae9` (300 trees, unrestricted depth, leaf 1).
- Feature count: 46.

| Metric | Value |
|---|---:|
| OOF macro recall | 0.7769 |
| OOF healthy / damaged recall | 0.599799 / 0.9540 |
| OOF PR-AUC / FNR | 0.9211 / 0.0460 |
| Fold macro recall mean +/- std | 0.7758 +/- 0.2758 |
| Worst fold / stability score | 0.3829 / 0.6379 |

The family improves aggregate macro recall and FNR, but healthy recall is strictly below 0.60; it is rejected without rounding the threshold. Variance increases, so condition normalization alone does not solve bearing shift.
