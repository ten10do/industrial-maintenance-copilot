# Paderborn fault-classification experiment — pending

Status: **not run**. The authorized full dataset has not been manually placed in
`data/raw/paderborn`; no metric below has been fabricated.

| Field | Value |
| --- | --- |
| Dataset | Paderborn University Bearing Data Center |
| Dataset version | Pending local download receipt and checksum |
| Raw samples | Not available |
| Bearings | Not available locally |
| Train bearings | Not run |
| Validation bearings | Not run |
| Test bearings | Not run |
| Feature version | `bearing-features-v1` |
| Window size / stride | 4096 / 4096 |
| Algorithms | LogisticRegression, RandomForestClassifier, optional HistGradientBoostingClassifier |
| Hyperparameters | `configs/ml/fault_v1.yaml` |

Leakage audit: not run. A real report must paste the CLI-generated bearing lists
and show empty train/validation/test intersections before metrics are accepted.

Precision, Recall, F1, ROC-AUC, PR-AUC, FNR, FPR, Brier score: **not available**.

License boundary: CC BY-NC 4.0. 仅用于学习、研究和作品集实验，不得据此宣称可直接商业使用。
