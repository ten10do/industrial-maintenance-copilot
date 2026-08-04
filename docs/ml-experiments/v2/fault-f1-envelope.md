# Fault F1 - V1 plus envelope features

- Scope: same 26 Development bearings, candidates, folds, and threshold as F0.
- Family representative: `fault-f1-hist_gradient_boosting-1e5241259c`; one of ten candidates passed.
- Feature count: 46.

| Metric | Value |
|---|---:|
| OOF macro recall | 0.7532 |
| OOF healthy / damaged recall | 0.6002 / 0.9063 |
| OOF PR-AUC / FNR | 0.9054 / 0.0937 |
| Fold macro recall mean +/- std | 0.7512 +/- 0.2582 |
| Worst fold / stability score | 0.3805 / 0.6221 |

Envelope features provide only a marginal stability gain over F0 and reduce PR-AUC. They are not independently sufficient for cross-bearing stability.
