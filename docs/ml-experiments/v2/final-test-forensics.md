# Paderborn Fault V2 Final-Test Forensics

Status: **PASS WITH MATERIAL GENERALIZATION LIMITATIONS**

This is a read-only forensic review of the already completed, one-time Frozen Test. It did not fit a model, call `predict`, recompute performance metrics, change the frozen configuration, or write any dataset/model artifact. The committed result remains the sole Final Test result.

## Governance chronology

| Event | Commit | Commit time (UTC+8) |
|---|---|---|
| Experiment preregistration | `772eacd9351fb72c0690d03446ee02640a9d9605` | 2026-08-03 18:00:15 |
| Fixed Development fold manifest | `33cc9e82073a177443a102141762028b37ceb709` | 2026-08-03 18:02:35 |
| Development result | `ec7cc67959063a2bcb604c632a6b310dee7ee9a4` | 2026-08-04 10:35:54 |
| Final candidate/config freeze | `029515104839c4719f018fa21ae5de12c2864859` | 2026-08-04 10:36:46 |
| One-time Final Test result | `dbdd4e6606099476e2fc46d6159e6e418f1bcfcc` | 2026-08-04 10:44:45 |

The ignored local access ledger records a completed access interval of 2026-08-04 02:37:07Z–02:42:25Z. The frozen configuration therefore preceded test access. The committed result and ledger both prohibit replay. Config SHA256 is `2bce080f002fd377fef6a65579f9d32ebe5286524a9d10a9aa749adfe2ed13a9`; the ignored artifact SHA256 is `68ceffc5dd066c51d4727eff1b4f3cd80cccd9c8655089971e312ef5f3e73b25`.

## Read-only reconstruction checks

The exact frozen feature-extraction path was reconstructed in memory from the authorized local Paderborn files. No estimator was loaded for prediction and no score was calculated.

| Check | Result |
|---|---|
| Development/Frozen bearing IDs | 26 / 6; intersection empty |
| Development/Frozen source files | 2,080 / 480; intersection empty |
| Development/Frozen windows | 129,280 / 29,860; sample-ID intersection empty |
| Raw 101-feature row hashes | zero exact Development/Frozen duplicates |
| Transformed 93-feature row hashes | zero exact Development/Frozen duplicates |
| Frozen feature cache SHA256 | `69e51b7cee210bb16936b56a3df049864e0d953fdcbe0652aaae77e908b23040`, exact committed match |
| Serialized preprocessor vs fresh Development-only fit | feature names, pooled center/scale, scaler mean/scale, and four condition baselines all exact |
| Preprocessor fit scope | 129,280 Development rows; zero Frozen Test rows |
| Explicit metadata-token scan | no bearing ID, source path, fault class, damage origin, split, or target feature |

The six frozen bearings contributed 4,963 (`K004`), 5,008 (`KA03`), 4,980 (`KA22`), 4,982 (`KB27`), 4,961 (`KI01`), and 4,966 (`KI04`) windows.

## Labels, conditions, and duplicate signals

The feature extractors consume vibration/current signals, sampling rate, and operating context; they do not consume fault labels. Targets are stored separately. `PaderbornFaultV2Preprocessor.fit` uses the Development target only to choose healthy **training** rows for condition baselines. Frozen labels were used only by the governed one-time runner to calculate the already committed metrics, not to generate, select, or normalize features.

All four operating conditions occur in both sets and contain both healthy and damaged windows. Development counts were 32,292 / 32,327 / 32,359 / 32,302; Frozen counts were 7,468 / 7,463 / 7,456 / 7,473. Thus operating condition cannot directly encode the split or target, although the context features can still carry controlled-test-rig domain information.

Exact hashes over the three raw high-rate channels produced 2,556 unique acquisitions from 2,560 files. There were no Development/Frozen duplicate waveforms. Three duplicate groups existed only inside Development bearing `KA04`:

- `N09_M07_F10_KA04_17.mat` and `_18.mat`
- `N15_M07_F04_KA04_15.mat`, `_20.mat`, and `_6.mat`
- `N15_M07_F04_KA04_19.mat` and `_5.mat`

Those duplicates may slightly overweight one Development bearing, but cannot directly explain Frozen Test performance because none crosses the boundary.

## Interpretation of the high result

No invalidating identity, source, adjacent-window, label, preprocessing, hyperparameter, or exact-duplicate leakage was found. The one-time macro recall of **0.9867** and its non-production staging eligibility therefore remain valid under the locked protocol.

The result is not fleet or production proof. The 29,860 windows represent only six independent bearings, with only one healthy bearing; adjacent windows are correlated; the source is a controlled rig rather than a field fleet. Development CV remains the variance warning (macro-recall standard deviation 0.2550; worst fold 0.4548). Development-only PCA also found strong implicit bearing-domain signal in sensor-derived features: bearing-identity eta-squared was 0.6648 / 0.8079 / 0.5394 for the first three components, versus 0.2103 / 0.0964 / 0.0278 for operating condition. This is not explicit metadata leakage, but it materially limits claims of cross-bearing generalization.

Final disposition: retain the frozen result and staging-only claim; prohibit production promotion, autonomous maintenance action, and further Final Test replay without a new preregistered protocol and genuinely independent data.
