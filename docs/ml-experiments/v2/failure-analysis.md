# Predictive Model V2 Failure Analysis and V3 Research Proposal

## Failure analysis

The Paderborn Fault V2 aggregate policy passes, but its 0.2550 Development fold standard deviation and 0.4548 worst fold remain a cross-bearing risk. XJTU RUL V2 fails every family because MAE remains 10.05–11.00 h and R² remains negative. The locked thresholds are unchanged.

| Cause | Evidence |
|---|---|
| Insufficient data | XJTU has 15 controlled run-to-failure bearings; Paderborn final evaluation has six bearings and only one healthy bearing. Window counts do not increase the number of independent bearings. |
| Class imbalance | Fault V2's single healthy final-test bearing makes healthy recall statistically fragile even though the window-level result is high. RUL is continuous rather than class-balanced, but long condition-3 runs dominate row counts. |
| Domain shift | Paderborn bearing identity explains substantial feature variance (PCA eta² 0.6707). XJTU condition-3 bearings dominate R0 trajectory instability. |
| Operating-condition shift | Condition-aware normalization improves Fault only modestly; XJTU importance repeatedly uses speed/radial-force context and performance varies by condition. |
| Feature insufficiency | Verified current channels help Fault. XJTU dual-channel, causal history, and degradation distance reduce some jumps but do not produce positive R². |
| Model bias | Tree ensembles dominate fold selection yet regress toward training-domain lifecycle patterns; negative permutation effects show unstable use of several spectral/cross-channel features. |
| Label granularity | XJTU RUL treats the last recorded acquisition as the observable endpoint, not an independently verified physical failure instant. One scalar RUL target does not distinguish operating regimes or degradation stages. |
| Cross-bearing variance | Fault Development worst-fold recall is 0.4548. RUL per-bearing oscillation rates range from 0 to 0.4221 in selected R0. |

Uncertainty is also insufficient: tree-dispersion intervals are explicitly uncalibrated, with empirical coverage only 0.3374–0.5507. They must not be presented as probabilistic confidence intervals.

## What worked and what did not

- Worked for Fault: fixed grouped folds, train-only condition baselines, verified phase-current channels, locked selection, one-time Frozen Test, serialized V2 preprocessor, and dry-run staging lineage.
- Partially worked for RUL: dual-channel/causal features and EWMA reduce trajectory jumps; grouped nested evaluation exposes the actual domain shift.
- Did not work for RUL accuracy: dual-channel fusion, causal multi-scale context, and fold-local robust degradation distance all worsen MAE/RMSE/R² versus R0.
- Not available: reliable nonlinear sample-level attribution and calibrated uncertainty. Neither is fabricated.

## V3 research proposal — not started

1. Freeze V2 and define bearing-level/condition-level error artifacts before new modeling, including per-bearing MAE/RMSE and lifecycle-stage curves.
2. Revisit the target with a preregistered normalized health/degradation formulation while retaining raw-hour RUL as the safety metric; audit the physical meaning of each run endpoint.
3. Evaluate condition-hierarchical or condition-held-out baselines and monotonic post-processing under grouped inner folds only; do not tune on any final/external set.
4. Calibrate uncertainty with grouped out-of-fold residuals or conformal intervals, reporting coverage by bearing and condition.
5. Add a licensed external run-to-failure benchmark only after explicit reuse terms and schema compatibility are confirmed, with one-time evaluation after freeze.

V3 is worth considering because V2 produced clear failure evidence and a reproducible evaluation harness, but it must be a separately preregistered research task. This PR does not start V3, lower policy thresholds, register a failed RUL model, or deploy anything.
