# Fault F3 - Envelope plus train-only condition normalization

- Scope: same Development-only grouped CV.
- Family representative: `fault-f3-hist_gradient_boosting-1e5241259c`; one candidate passed.
- Feature count: 56.

| Metric | Value |
|---|---:|
| OOF macro recall | 0.7740 |
| OOF healthy / damaged recall | 0.6002 / 0.9477 |
| OOF PR-AUC / FNR | 0.9040 / 0.0523 |
| Fold macro recall mean +/- std | 0.7728 +/- 0.2752 |
| Worst fold / stability score | 0.3788 / 0.6352 |

F3 passes aggregate gates and improves recall relative to F0/F1, but it remains less stable than the final multi-channel family.
