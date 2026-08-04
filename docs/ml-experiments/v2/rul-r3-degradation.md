# XJTU-SY RUL V2 — R3 Fold-local Degradation Indicator

R3 adds the preregistered degradation distance to R2. For every inner and outer split, the early-life reference, RobustScaler, and median baseline are fitted on train bearings only; validation bearings are transform-only. All 15 XJTU-SY bearings remain Development data, so this is a **Cross-Bearing Generalization Estimate**, not a new final test.

| Metric | Raw | Causal EWMA |
|---|---:|---:|
| MAE (h) | 10.9994 | 11.0183 |
| RMSE (h) | 15.2089 | 15.2037 |
| R² | -0.5087 | -0.5076 |
| Late error (h) | 1.9387 | 1.9707 |
| Oscillation count | 737 | 38 |
| Mean per-bearing oscillation rate | 0.0606 | 0.0028 |
| Max positive jump (h) | 9.2310 | 1.8212 |

All five outer folds selected Extra Trees; four selected depth 8/min leaf 3 and one selected depth 12/min leaf 1. Permutation importance used the V2.4 deterministic cap of 1,000 held-out rows per fold. Negative effects for several vertical/cross-channel features remain evidence of unstable feature use. Reliable nonlinear sample-level attribution is unavailable.

The uncalibrated tree-dispersion interval covered all 9,216 rows, with empirical target coverage 0.5143 and mean width 16.8344 h. It is not a calibrated probability interval.

The fold-local degradation indicator did not improve R2 accuracy or raw trajectory stability. Promotion is **rejected** because MAE exceeds 5 h and R² is not positive. No R3 model is registered or promoted.
