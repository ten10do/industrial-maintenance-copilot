# Paderborn V2 Development-only Domain Analysis

- Scope: Paderborn 26 Development bearings only
- Rows / bearings: 129280 / 26
- Dataset / feature: `paderborn-snapshot-e513a6320d755ce5` / `bearing-features-v2`
- Config SHA: `4f9a0aed0603ed1ce4bdcdabb73adb9e734ebf8e65fa13a8e481317be440b654`
- Git SHA: `7593f701f5e4c0d4ebb9d6bcb86a265b8830f2eb`
- Frozen test accessed: **no**
- Frozen-test intersection: `[]`

## Distribution

- Bearing fault class: `{'combined_inner_outer': 2, 'healthy': 5, 'inner_ring': 9, 'outer_ring': 10}`
- Bearing damage origin: `{'artificial': 10, 'healthy': 5, 'real': 11}`
- Window operating condition: `{'N09_M07_F10': 32292, 'N15_M01_F10': 32327, 'N15_M07_F04': 32359, 'N15_M07_F10': 32302}`

## Healthy vs damaged overlap

| Feature | Direction-invariant AUC | Standardized mean difference |
|---|---:|---:|
| rms | 0.5425 | 0.0814 |
| kurtosis | 0.7340 | -0.6436 |
| crest_factor | 0.6886 | -0.5977 |
| spectral_centroid_hz | 0.8711 | -1.6923 |
| low_band_energy | 0.5880 | 0.5692 |
| mid_band_energy | 0.7841 | -1.3308 |
| high_band_energy | 0.8069 | -1.4022 |

## PCA factor effects

PCA is analysis-only and is not used as a model input. Eta-squared is reported for PC1–PC3; a larger value means that factor explains more coordinate variance.

- Explained variance: `[0.4466862864028708, 0.38521160911040186, 0.12631426193453196]`
- Bearing identity eta²: `[0.6648088525369208, 0.8079301406447739, 0.5394136107099351]`
- Operating condition eta²: `[0.21033694378736667, 0.09637285471098615, 0.02781736005640052]`
- Damage origin eta²: `[0.4112687706585879, 0.12652795519956014, 0.15325638492747462]`

## Quantitative interpretation

- RMS alone has direction-invariant AUC 0.5425, which is close to random and confirms substantial healthy/damaged overlap.
- Spectral centroid is the strongest audited univariate separator (AUC 0.8711), but a univariate Development effect is not cross-bearing proof.
- Mean PC1–PC3 eta² is bearing=0.6707, condition=0.1115, and damage-origin=0.2304. Bearing identity is the dominant factor, so identity/domain learning is a material generalization risk.
- Operating condition contributes measurable variance (especially PC1), so fold-local condition normalization is justified but cannot by itself remove bearing-specific shift.

## Channel audit

- Representative files: 104
- Coverage: `{'force': 104, 'phase_current_1': 104, 'phase_current_2': 104, 'speed': 104, 'temp_2_bearing_module': 104, 'torque': 104, 'vibration_1': 104}`
- Aligned high-rate triplets: 104
- F4: **applicable** using `['vibration_1', 'phase_current_1', 'phase_current_2']`
- BPFO/BPFI/BSF/FTF: disabled because locked inputs do not contain bearing geometry.

## Interpretation guardrail

The committed JSON contains bearing- and condition-specific medians. This analysis quantifies whether identity/condition effects rival damage-origin effects; it does not inspect or summarize the six frozen test bearings and does not select a model.
