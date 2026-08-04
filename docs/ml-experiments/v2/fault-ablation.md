# Paderborn Fault V2 Grouped Development Results

- Scope: 26 Development bearings; six Frozen Test bearings remain closed.
- Dataset / feature: `paderborn-snapshot-e513a6320d755ce5` / `bearing-features-v2`
- Git SHA: `ece573c4d29f48acc6fb1a50fddf7af8f9d8409f`
- Candidates: 50 across F0–F4 and five fixed folds
- Classification threshold: 0.50

## Selected Development candidate

- Selection pool: gate-passing candidates
- Family / algorithm: **F4 / random_forest**
- Hyperparameters: `{'class_weight': 'balanced_subsample', 'max_depth': 12, 'max_features': 'sqrt', 'min_samples_leaf': 2, 'n_estimators': 300}`
- OOF macro recall: **0.7904**
- OOF healthy recall: **0.6005**
- OOF damaged recall: 0.9802
- OOF PR-AUC: 0.9482
- Fold macro recall: 0.7900 ± 0.2550; worst 0.4548
- Promotion gate: **PASS**

## Hierarchical result

`{'status': 'evaluated', 'target': 'damage_origin artificial vs real', 'bearing_counts': {'artificial': 10, 'real': 11}, 'metrics': {'macro_precision': 0.7991264790987527, 'macro_recall': 0.7923652502557316, 'macro_f1': 0.7932720668841561, 'roc_auc': 0.7968783068298025, 'pr_auc': 0.7095663137790236, 'healthy_recall': 0.7274883898594721, 'damaged_recall': 0.8572421106519911, 'false_negative_rate': 0.14275788934800893, 'false_positive_rate': 0.27251161014052794, 'confusion_matrix': [[36186, 13555], [7808, 46886]]}, 'promotion_role': 'none; Stage 1 remains the safety classifier'}`

## Frozen-test decision

Development gates passed. Freeze and commit a final config before any one-time test access.
