# XJTU-SY RUL experiment — pending

Status: **not run**. The full run-to-failure dataset has not been manually placed
in `data/raw/xjtu-sy`; no metric below has been fabricated.

| Field | Value |
| --- | --- |
| Dataset | XJTU-SY Bearing Dataset |
| Dataset version | Pending local download receipt and checksum |
| Raw samples | Not available |
| Bearings | 15 described by the author source; not available locally |
| Train bearings | Not run |
| Validation bearings | Not run |
| Test bearings | Not run |
| Feature version | `bearing-features-v1` |
| Window size / stride | 32768 / 32768 |
| Algorithms | Ridge, RandomForestRegressor, optional HistGradientBoostingRegressor |
| Hyperparameters | `configs/ml/rul_v1.yaml` |

Leakage audit: not run. A real report must paste the CLI-generated bearing/run
lists and show empty train/validation/test intersections before metrics are
accepted. Scaler/model fitting must remain train-only; test is final evaluation
only.

MAE, RMSE, Median AE, R², relative error, early error, late error: **not available**.

The author repository has no explicit LICENSE file; unattended redistribution
and claims of unrestricted commercial use are prohibited by this workflow.
