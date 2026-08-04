# XJTU-SY RUL V2 — R2 Causal Multi-scale Context

R2 adds strictly backward-only 5/15/30/60-minute context to R1. Automated leakage tests forbid centered or future observations. The experiment uses the same fixed five-fold grouped outer manifest and group-aware inner selection across all 15 Development bearings.

| Metric | Raw | Causal EWMA |
|---|---:|---:|
| MAE (h) | 10.8835 | 10.9052 |
| RMSE (h) | 15.1300 | 15.1274 |
| R² | -0.4931 | -0.4925 |
| Late error (h) | 1.8944 | 1.9274 |
| Oscillation count | 692 | 35 |
| Mean per-bearing oscillation rate | 0.0663 | 0.0034 |
| Max positive jump (h) | 8.1224 | 1.5182 |

Four outer folds selected Extra Trees depth 8 and one selected Extra Trees depth 12. Explainability uses at most 1,000 deterministic held-out rows per fold under the V2.4 bounded-compute amendment. Negative permutation effects are retained as instability evidence; reliable nonlinear sample-level attribution is unavailable.

The uncalibrated tree-dispersion interval covered all 9,216 rows, with empirical target coverage 0.5062 and mean width 16.3327 h. It must not be presented as a calibrated probability interval.

Causal context materially reduces oscillation count versus R0/R1, but accuracy worsens. Promotion is **rejected** because MAE exceeds 5 h and R² is not positive. No R2 model is registered or promoted.
