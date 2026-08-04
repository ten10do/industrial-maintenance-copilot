# XJTU-SY RUL V2 — R1 Dual-channel Features

R1 adds verified horizontal and vertical vibration features plus cross-channel ratios/correlation. It uses the same fixed grouped outer folds and group-aware inner selection as R0. All 15 bearings are Development data; this is a **Cross-Bearing Generalization Estimate**.

| Metric | Raw | Causal EWMA |
|---|---:|---:|
| MAE (h) | 10.6005 | 10.6238 |
| RMSE (h) | 14.8111 | 14.8090 |
| R² | -0.4308 | -0.4304 |
| Late error (h) | 1.8243 | 1.8550 |
| Oscillation count | 1,330 | 57 |
| Mean per-bearing oscillation rate | 0.0861 | 0.0046 |
| Max positive jump (h) | 6.8354 | 1.1411 |

Every outer fold selected Extra Trees from the preregistered finite grids. Global permutation effects show unstable use of several vertical/cross-channel features, including negative effects for `vertical_mid_band_energy_ratio` and `cross_channel_correlation`. Reliable nonlinear sample-level attribution is unavailable.

The uncalibrated tree-dispersion interval covered all 9,216 rows, with empirical target coverage 0.5507 and mean width 18.4297 h. This is descriptive ensemble dispersion, not a calibrated 80% probability interval.

Dual-channel features reduce raw trajectory jumps relative to R0 but worsen MAE, RMSE, and R². Promotion is **rejected** because MAE exceeds 5 h and R² is not positive. No R1 model is registered or promoted.
