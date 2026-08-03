# XJTU-SY RUL regression v1

**REAL DATA EXPERIMENT**

## Outcome

HistGradientBoostingRegressor was selected by the locked validation policy and received one final test evaluation. The artifact was registered in the local non-production model registry as `candidate`. Its code-generated promotion decision is ineligible because validation MAE exceeds the 5-hour threshold, so candidate-to-staging promotion was rejected. No staging inference or downstream Agent/Work Order linkage was run.

## Provenance

- Dataset version: `xjtu-sy-snapshot-6364ef9cb50663c5`
- Processed SHA256: `607c52a647e34c307a4114c3555c92ad624ff8e6896fe63211ba720f6b4f1e5d`
- Feature version: `bearing-features-v1`
- Training code Git SHA: `81803b36f92655b9fb4afa3723a3c396abf36dda`
- Seed: `20260803`
- Processed rows / bearings: 9,216 / 15
- RUL definition: `remaining_measurements / 60`, using the observable final acquisition as the run endpoint
- Feature input: horizontal vibration plus backward-only history; no future or centered window
- Memory strategy: one CSV at a time, 512-row disk chunks, memmap consolidation

## Locked split

- Train: `Bearing1_2, Bearing1_3, Bearing1_5, Bearing2_2, Bearing2_3, Bearing2_5, Bearing3_2, Bearing3_3, Bearing3_5`
- Validation: `Bearing1_1, Bearing2_4, Bearing3_1`
- Test: `Bearing1_4, Bearing2_1, Bearing3_4`
- Train / validation intersection: empty
- Train / test intersection: empty
- Validation / test intersection: empty
- Train / validation / test rows: 4,385 / 2,703 / 2,128

Every bearing run belongs to exactly one split. The formal leakage audit passed identity, source, adjacent-window, label, preprocessing, hyperparameter, and future-time checks. Scalers and models fit train only; validation selected the model; test was evaluated once after selection.

## Validation model selection

| Model | MAE h | RMSE h | Median AE h | R² | Relative error | Early error h | Late error h |
|---|---:|---:|---:|---:|---:|---:|---:|
| Ridge | 20.8575 | 22.2241 | 20.2874 | -2.0183 | 2.1879 | 19.7134 | 1.1441 |
| RandomForestRegressor | 17.0859 | 21.2040 | 15.4612 | -1.7476 | 0.8941 | 16.8000 | 0.2859 |
| HistGradientBoostingRegressor | 16.9812 | 21.0193 | 15.5683 | -1.6999 | 0.8827 | 16.7169 | 0.2643 |

The coded selection policy chose HistGradientBoosting because it has the lowest validation MAE/RMSE among candidates satisfying the 3-hour validation late-error constraint.

## Final test (one evaluation)

- MAE: 7.3857 h
- RMSE: 8.6048 h
- Median absolute error: 7.0936 h
- R²: -0.3054
- Relative error: 1.6666
- Early prediction error: 0.6790 h
- Late prediction error: 6.7066 h

| Test bearing | Run length | MAE h | RMSE h | Median AE h | R² | Early h | Late h |
|---|---:|---:|---:|---:|---:|---:|---:|
| Bearing1_4 | 122 | 4.6055 | 4.9901 | 4.1037 | -71.2795 | 0.0000 | 4.6055 |
| Bearing2_1 | 491 | 8.5799 | 9.3928 | 8.4138 | -14.8093 | 0.0498 | 8.5302 |
| Bearing3_4 | 1,515 | 7.2225 | 8.5676 | 6.8731 | -0.3816 | 0.9377 | 6.2849 |

Generalization is weakest on operating condition 2's held-out `Bearing2_1` (highest MAE and late error). R² is negative globally and for every test bearing, so this model does not outperform a per-evaluation-set mean baseline despite its lower absolute error on the shorter test lifetimes.

## Feature and trajectory diagnostics

Top validation permutation effects by absolute magnitude include `mid_band_energy` (0.2609), `shape_factor` (-0.2182), `mid_energy_ratio` (-0.0766), `context_radial_force_kn` (0.0727), `rolling_mean` (-0.0644), and `kurtosis` (-0.0610). Negative permutation values are retained as evidence of unstable or harmful feature use; they are not rewritten as positive importance.

- Raw negative predictions: 0
- Predictions above training lifecycle maximum: 0
- Training lifecycle maximum: 41.5833 h
- Near-failure mean late error: 3.9210 h
- Severe trajectory oscillations: 41
- Online display clamp policy: raw and display predictions remain separately recorded; this test report uses raw predictions

## Registry and promotion

- Model version: `rul-hist_gradient_boosting-20260803T090106Z`
- Artifact SHA256: `1a35084283efbe06c108e82e905d59dd13dd10cfee7c073c1660b0f0934b1fea`
- Local registry model ID: 1
- Training run: `xjtu-sy-rul-v1-rul-hist_gradient_boosting-20260803T090106Z`
- Registry status: `candidate`
- Production: false
- Promotion decision: rejected; validation MAE 16.9812 h exceeds 5 h
- Staging status: not reached
- Staging inference / PredictionRecord / Diagnosis / RAG / Work Order: not executed

## Limitations

- The author repository has no explicit LICENSE file or SPDX terms; public availability does not establish redistribution or commercial-use rights.
- The final recorded acquisition is treated as the observable run endpoint; it is not independently verified here as the exact physical failure instant.
- Only horizontal vibration is used for features; the vertical channel is validated but not fused into this v1 model.
- Split run lengths differ substantially, and the validation set is dominated by the long `Bearing3_1` run. The poor validation MAE and negative test R² show material cross-bearing/domain shift.
- This controlled run-to-failure dataset does not prove performance on live motors, PLCs, or production sensors.
