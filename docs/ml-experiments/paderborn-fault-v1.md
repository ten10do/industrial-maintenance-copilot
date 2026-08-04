# Paderborn fault classification v1

**REAL DATA EXPERIMENT**

## Outcome

The experiment is valid but did not produce an eligible model. All three candidates were trained on the locked training bearings and evaluated on validation bearings only. None reached the pre-registered macro-recall floor of 0.70, so model selection stopped before the test set. There is no selected fault model, final test result, registry entry, or staging promotion from this run.

## Provenance

- Dataset version: `paderborn-snapshot-e513a6320d755ce5`
- Processed SHA256: `b365516ffb669ecfe9f30b2bf659a12e760d5234d620fd52fce5f4eb16deef34`
- Feature version: `bearing-features-v1`
- Training code Git SHA: `81803b36f92655b9fb4afa3723a3c396abf36dda`
- Seed: `20260803`
- Processed rows / bearings: 159,140 / 32
- Signal: named official `vibration_1`, 64 kHz, 4,096-sample non-overlapping windows
- Memory strategy: streaming extraction, 512-row disk chunks, memmap consolidation

One official file, `KA08/N15_M01_F10_KA08_2.mat` (SHA256 `e137cbb2368caa8bd56889eff8609d2569d2c196a85107e16aa4740437f2ccb3`), contains complete `vibration_1` name/data but zero-filled optional metadata after that final channel. The source RAR passes 7-Zip integrity testing and exact re-extraction produces the same file hash. The strict MAT-v5 named-channel fallback retained all 256,000 finite signal samples after `scipy.io.loadmat` rejected the optional trailing metadata; no source file or sample was skipped or modified.

## Locked split

- Train: `K001, K002, K003, K006, KA01, KA04, KA05, KA06, KA08, KA09, KA15, KA30, KB23, KI03, KI05, KI08, KI14, KI16, KI17, KI21`
- Validation: `K005, KA07, KA16, KB24, KI07, KI18`
- Test: `K004, KA03, KA22, KB27, KI01, KI04`
- Train / validation intersection: empty
- Train / test intersection: empty
- Validation / test intersection: empty
- Train / validation / test rows: 99,450 / 29,830 / 29,860
- Open-set status: false; every test fault type is represented in train

The formal leakage audit passed identity, source, adjacent-window, label, preprocessing, hyperparameter, and condition-distribution checks. Scalers and models fit train only; validation is selection-only; the test set was not accessed because selection failed.

## Validation results

| Model | Accuracy | Macro precision | Macro recall | Macro F1 | ROC-AUC | PR-AUC | FNR | Brier |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| LogisticRegression | 0.6407 | 0.5192 | 0.6054 | 0.5498 | 0.8144 | 0.6221 | 0.3946 | 0.1526 |
| RandomForestClassifier | 0.7247 | 0.6183 | 0.6532 | 0.6190 | 0.8759 | 0.7122 | 0.3468 | 0.1070 |
| HistGradientBoostingClassifier | 0.7415 | 0.6208 | 0.6764 | 0.6347 | 0.7621 | 0.6300 | 0.3236 | 0.1217 |

RandomForest has the highest validation PR-AUC, while HistGradientBoosting has the highest macro recall. Neither is eligible because recall is below 0.70. The policy correctly refuses to trade the safety constraint for the higher PR-AUC.

The main generalization failure is the healthy class: validation recall is 0.0000 for LogisticRegression and HistGradientBoosting and 0.0006 for RandomForest. This indicates that the present feature/model combination is largely discriminating dataset or bearing domains instead of learning a reliable healthy-versus-fault boundary across held-out bearings.

## Final test and registry

- Selected model: none
- Final test executed: **no**
- Test metrics: unavailable by design
- Candidate registered: **no**
- Staging promotion: **not attempted**
- Staging inference / PredictionRecord / Diagnosis / RAG / Work Order: **not executed**

## Limitations

- Paderborn is licensed CC BY-NC 4.0; this experiment does not establish commercial-use rights.
- The dataset is a controlled bearing test rig, not a production motor fleet or live PLC/sensor stream.
- The experiment currently uses vibration channel 1 only; the other recorded channels are not fused into the model.
- The fixed split exposes strong held-out-bearing domain shift, especially for healthy bearings. Improving it requires a new, pre-registered experiment—not test-driven tuning of this run.
