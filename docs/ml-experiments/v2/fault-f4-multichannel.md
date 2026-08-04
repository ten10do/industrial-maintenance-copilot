# Fault F4 - Combined vibration and verified motor-current channels

- Inputs: F3 vibration features plus named `phase_current_1`, `phase_current_2`, and cross-current features. All channels were verified in the Development channel audit; no synthetic channel or bearing-frequency geometry was used.
- Six of ten candidates passed aggregate gates.
- Locked winner: `fault-f4-random_forest-3cc8229aab`.
- Model: RandomForest, 300 trees, depth 12, leaf 2, sqrt features, balanced-subsample weights.
- Feature count: 93.

| Metric | Value |
|---|---:|
| OOF macro recall | 0.7904 |
| OOF healthy / damaged recall | 0.6005 / 0.9802 |
| OOF PR-AUC / FNR | 0.9482 / 0.0198 |
| Fold macro recall mean +/- std | 0.7900 +/- 0.2550 |
| Worst fold / stability score | 0.4548 / 0.6625 |

F4 is the clear Development winner and materially improves damaged recall, FNR, PR-AUC, stability, and worst-fold recall. The remaining 0.2550 fold standard deviation is a material limitation, not evidence of production readiness.

Development-only permutation importance uses all 93 features, three repeats, and deterministic samples of at most 250 held-out rows per fold. The strongest effect is condition-normalized spectral centroid. The selected nonlinear estimator has no reliable native sample-level linear attribution, so local contributors are explicitly `unavailable` rather than represented as SHAP.
