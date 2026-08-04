# Paderborn Fault V2 Single Final Test

## Governed access

- Development result commit: `ec7cc67959063a2bcb604c632a6b310dee7ee9a4`.
- Frozen config commit: `029515104839c4719f018fa21ae5de12c2864859`.
- Config SHA256: `2bce080f002fd377fef6a65579f9d32ebe5286524a9d10a9aa749adfe2ed13a9`.
- Access interval: 2026-08-04 02:37:07Z to 02:42:25Z.
- Replay: forbidden; the ignored local access ledger is complete.
- Frozen bearings: `K004, KA03, KA22, KB27, KI01, KI04`.
- Rows / bearing-level units: 29,860 windows / 6 bearings.

## Frozen candidate

- Family / model: F4 / RandomForestClassifier.
- Hyperparameters: 300 trees, depth 12, minimum leaf 2, sqrt features, balanced-subsample class weights.
- Features: 93 verified vibration/current and train-only condition-normalized features.
- Threshold: 0.50; it was not changed after test access.

## One-time result

| Metric | Value |
|---|---:|
| Macro precision | 0.9956 |
| Macro recall | 0.9867 |
| Macro F1 | 0.9911 |
| ROC-AUC | 0.9996 |
| PR-AUC | 0.9999 |
| Healthy recall | 0.9742 |
| Damaged recall | 0.9993 |
| FNR / FPR | 0.0007 / 0.0258 |
| Brier | 0.0218 |

Confusion matrix (`healthy`, `damaged`): `[[4835, 128], [18, 24879]]`.

Both frozen gates passed: macro recall >= 0.70 and healthy recall >= 0.60. The immutable prediction hash is `7abee7d69e986dd60e2c212c4e4641c9b74053e4802f9e971867dee92a6c751c`.

## Interpretation boundary

This is one pre-registered final evaluation, not repeated test-driven tuning. The high window-level metrics do not imply production readiness: the independent statistical units are only six bearings, including one healthy bearing (`K004`) and five damaged bearings. Adjacent windows within a bearing are correlated, and the test rig is not a live motor fleet. Development CV still had 0.2550 fold macro-recall standard deviation and 0.4548 worst-fold recall. Both facts remain part of the model risk record.

The artifact is local and ignored by Git. Its integrity SHA256 is `68ceffc5dd066c51d4727eff1b4f3cd80cccd9c8655089971e312ef5f3e73b25`. Passing this test permits non-production candidate/staging evaluation only; production remains forbidden.
