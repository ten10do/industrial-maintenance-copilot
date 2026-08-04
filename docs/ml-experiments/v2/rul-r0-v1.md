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

## Per-bearing raw trajectory diagnostics

| Bearing | Oscillations | Rate | Mean positive jump (h) | Max positive jump (h) |
|---|---:|---:|---:|---:|
| Bearing1_1 | 4 | 0.0328 | 0.3085 | 4.0616 |
| Bearing1_2 | 0 | 0.0000 | 0.0368 | 0.2652 |
| Bearing1_3 | 3 | 0.0191 | 0.1225 | 0.7438 |
| Bearing1_4 | 8 | 0.0661 | 0.2130 | 2.5914 |
| Bearing1_5 | 0 | 0.0000 | 0.1879 | 0.4643 |
| Bearing2_1 | 51 | 0.1041 | 0.4245 | 1.4962 |
| Bearing2_2 | 5 | 0.0312 | 0.1720 | 3.2457 |
| Bearing2_3 | 26 | 0.0489 | 0.1922 | 1.8681 |
| Bearing2_4 | 0 | 0.0000 | 0.1133 | 0.4448 |
| Bearing2_5 | 0 | 0.0000 | 0.0705 | 0.4461 |
| Bearing3_1 | 487 | 0.1920 | 0.5005 | 3.8494 |
| Bearing3_2 | 700 | 0.2806 | 1.0904 | 9.3287 |
| Bearing3_3 | 100 | 0.2703 | 0.8313 | 6.7396 |
| Bearing3_4 | 639 | 0.4221 | 4.6758 | 23.6728 |
| Bearing3_5 | 1 | 0.0088 | 0.1380 | 3.8813 |

The condition-3 bearings dominate the instability. Counts are not normalized for run length; the preregistered promotion check therefore uses the arithmetic mean of per-bearing rates.

Promotion is **rejected**: late error and raw oscillation-rate gates pass, but MAE exceeds 5 h and R² is not positive. No R0 model is registered or promoted.
