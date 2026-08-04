# Paderborn Fault V2 Final Leakage and High-Metric Audit

Status: **PASS WITH MATERIAL GENERALIZATION LIMITATIONS**

| Check | Result | Evidence |
|---|---|---|
| Identity leakage | PASS | 26 Development and 6 Frozen Test bearing IDs are disjoint; the final runner used the locked manifest. |
| Source leakage | PASS | Training cache contains only Development groups; Frozen MAT files were opened only after the config commit and access ledger. |
| Adjacent-window leakage | PASS | All windows from one bearing stay in one group; no bearing appears on both sides. |
| Label leakage | PASS | Features exclude `fault_class`, `damage_origin`, bearing ID, and target fields. |
| Preprocessing leakage | PASS | The serialized preprocessor was byte-for-byte numerically checked against a fresh fit on all 129,280 Development rows only: 93 features, four training-condition baselines. |
| Hyperparameter leakage | PASS | Family, model, hyperparameters, threshold, preprocessing, and gates were fixed in commit `0295151` before the access ledger. |
| Artifact integrity | PASS | Bundle reload and SHA verification passed for `68ceffc5...e73b25`; config, dataset, feature, Git, and sample-count lineage match. |
| Replay protection | PASS | The ledger changed once from `started` to `completed`; output and ledger existence both block replay. |
| Test-driven changes | PASS | No feature, parameter, threshold, or gate was changed after the one final result. |

## Why the high metric is not treated as fleet proof

- The metric has 29,860 correlated windows but only six independent held-out bearings.
- Binary healthy recall comes from a single healthy test bearing; the remaining five are damaged.
- Paderborn is a controlled electromechanical test rig. It does not cover live PLC/sensor integration, field noise, installation variance, maintenance history, or fleet-level prevalence.
- Development CV is the stronger variance warning: standard deviation 0.2550 and worst fold 0.4548 remain poor despite the high final split result.
- The domain audit found bearing-identity PCA eta-squared 0.6707 versus condition 0.1115 and damage-origin 0.2304. Bearing/domain effects remain material.

Conclusion: the result is valid under the locked protocol and may enter non-production candidate/staging validation, but it is not evidence for production promotion or autonomous maintenance actions.
