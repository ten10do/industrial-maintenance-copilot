# XJTU-SY RUL V2 — R0 V1 Feature Baseline

R0 evaluates the retained V1-style horizontal-vibration feature family under the V2 protocol: all 15 bearings are Development data, with the fixed five-fold grouped outer manifest and group-aware inner selection. The numbers below are a **Cross-Bearing Generalization Estimate**, not an unbiased final test.

| Metric | Raw | Causal EWMA |
|---|---:|---:|
| MAE (h) | 10.0543 | 9.9503 |
| RMSE (h) | 14.2737 | 14.1610 |
| R² | -0.3288 | -0.3079 |
| Late error (h) | 2.0043 | 1.9717 |
| Oscillation count | 2,024 | 510 |
| Mean per-bearing oscillation rate | 0.0984 | 0.0241 |
| Max positive jump (h) | 23.6728 | 3.1595 |

Outer folds selected Extra Trees three times, HistGradientBoosting once, and Random Forest once from the preregistered finite grids. Permutation importance is global held-out-fold analysis; nonlinear sample-level attribution is explicitly unavailable rather than approximated as SHAP.

The uncalibrated tree-dispersion interval covered 7,087 rows, with empirical target coverage 0.3374 and mean width 14.2869 h. It is not a calibrated probability interval.

Promotion is **rejected**: late error and raw oscillation-rate gates pass, but MAE exceeds 5 h and R² is not positive. No R0 model is registered or promoted.
