# XJTU-SY RUL V2 Cross-Bearing Generalization Estimate

This is a 15-bearing Development estimate, not an unbiased final test.

- Protocol: fixed condition-balanced 5-fold grouped outer; grouped 3-fold inner
- Dataset / feature: `xjtu-sy-snapshot-6364ef9cb50663c5` / `bearing-features-v2`
- Git SHA: `82abb8cabbdbd43a738e19f951014df9ef7f9924`
- Selected family: **R0** (best failed family)

## Raw trajectory (promotion basis)

- MAE / RMSE: **10.0543 h** / 14.2737 h
- R²: **-0.3288**
- Mean late error: 2.0043 h
- Oscillation count / mean bearing rate: 2024 / 0.0984
- Mean / max positive jump: 1.3094 h / 23.6728 h

## Causal EWMA (alpha=0.20; supplemental only)

- MAE / RMSE: 9.9503 h / 14.1610 h
- R²: -0.3079
- Oscillation count / mean bearing rate: 510 / 0.0241

Promotion: **REJECTED**
Uncertainty: `{'calibrated_probability_interval': False, 'coverage_fraction': 0.7689887152777778, 'covered_rows': 7087, 'empirical_target_coverage': 0.33737829829264854, 'mean_interval_width_hours': 14.286913658753088, 'status': 'partial empirical 10th/90th tree dispersion'}`
