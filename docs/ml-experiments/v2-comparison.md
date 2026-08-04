# Predictive Model V1 / V2 Comparison

## Paderborn fault classification

| Evaluation | Macro recall | Healthy recall | PR-AUC | FNR | Cross-fold std / worst |
|---|---:|---:|---:|---:|---:|
| V1 fixed validation, best recall model | 0.6764 | 0.0000 | 0.6300 | 0.3236 | N/A |
| V1 fixed validation, best PR-AUC model | 0.6532 | 0.0006 | 0.7122 | 0.3468 | N/A |
| V2 F4 selected, 26-bearing Development grouped CV | 0.7904 | 0.6005 | 0.9482 | 0.0198 | 0.2550 / 0.4548 |
| V2 one-time six-bearing Frozen Test | 0.9867 | 0.9742 | 0.9999 | 0.0007 | N/A |

V2 genuinely improves the preregistered held-out-bearing Development estimate and resolves the V1 healthy-recall collapse at the aggregate level. F4's verified phase-current channels add the strongest gain over F0–F3, while envelope-only and condition-normalization families provide smaller gains. The evidence is still high variance: Development worst-fold recall is 0.4548, and the final test has only six independent bearings with one healthy bearing despite 29,860 correlated windows. The high final window-level metrics therefore justify local non-production staging validation, not production deployment.

These rows are not strict apples-to-apples comparisons. V1 used one fixed six-bearing validation split; V2 selected only on five grouped folds over 26 Development bearings and then accessed the original six-bearing test exactly once after config freeze.

## XJTU-SY RUL

| Evaluation | MAE (h) | RMSE (h) | R² | Late error (h) | Raw oscillations |
|---|---:|---:|---:|---:|---:|
| V1 fixed validation | 16.9812 | 21.0193 | -1.6999 | 0.2643 | N/A |
| V1 one-time three-bearing test | 7.3857 | 8.6048 | -0.3054 | 6.7066 | 41 |
| V2 R0, 15-bearing grouped estimate | 10.0543 | 14.2737 | -0.3288 | 2.0043 | 2,024 |
| V2 R1 dual-channel | 10.6005 | 14.8111 | -0.4308 | 1.8243 | 1,330 |
| V2 R2 causal context | 10.8835 | 15.1300 | -0.4931 | 1.8944 | 692 |
| V2 R3 degradation | 10.9994 | 15.2089 | -0.5087 | 1.9387 | 737 |

The V2 estimate improves on V1 validation MAE but is worse than the already-seen V1 test MAE, and every V2 family still has negative R². Because V2 uses all 15 bearings in fixed grouped outer CV while V1 used a 9/3/3 split, neither direction is a causal or strict apples-to-apples improvement claim. The honest conclusion is that cross-bearing RUL accuracy has **not been demonstrated to improve**.

Dual-channel and causal features reduce raw positive-jump counts, and fixed causal EWMA reduces the selected R0 count from 2,024 to 510. Counts span 15 runs of very different lengths, so rates are the promotion statistic. Smoothing is supplemental only and cannot rescue promotion. R2 gives the best raw causal-feature oscillation count (692), while R3 worsens it to 737 and both worsen accuracy. No V2 RUL family passes MAE <= 5 h and R² > 0.

## Decision

- Fault V2: passed locked policy; registered and promoted only to local non-production `staging`; online dry-run preserved immutable ML output and human approval.
- RUL V2: all families rejected; no model registry entry, staging inference, or Agent/work-order integration.
- Production: no model promotion, deployment, database migration, or autonomous equipment action.
