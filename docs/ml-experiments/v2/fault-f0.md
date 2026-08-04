# Fault F0 - V1 feature baseline

- Scope: 26 Paderborn Development bearings, five fixed grouped folds; Frozen Test not accessed.
- Search: 10 V2.3 candidates; one passed both aggregate gates.
- Family representative: `fault-f0-hist_gradient_boosting-1e5241259c`.
- Model: HistGradientBoosting, 150 iterations, learning rate 0.03, 15 leaves, L2 1.0.
- Feature count: 36.

| Metric | Value |
|---|---:|
| OOF macro recall | 0.7527 |
| OOF healthy / damaged recall | 0.6001 / 0.9052 |
| OOF PR-AUC / FNR | 0.9179 / 0.0948 |
| Fold macro recall mean +/- std | 0.7507 +/- 0.2582 |
| Worst fold / stability score | 0.3814 / 0.6216 |

F0 fixes V1's near-zero aggregate healthy recall, but its worst fold and variance show that the boundary is still strongly bearing-dependent.
