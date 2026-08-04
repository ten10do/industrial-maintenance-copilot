# Excluded pre-V2.3 Fault runs

These three F0 RandomForest runs were completed under the original larger grid before V2.3 bounded the search. Their file names/counts were known, but no numeric metrics were inspected before the amendment. Their hyperparameters are not in the locked V2.3 grid, so they never entered family comparison, model selection, or promotion.

| Run JSON | SHA256 |
|---|---|
| `fault-f0-random_forest-277e760db0.json` | `f56087e37b70eb68ce7c7bfaf126db2bc22e81036cd80d97f7dc0c5be1ea9a15` |
| `fault-f0-random_forest-6bccd5bf40.json` | `29a939c7d991e03d5575252dcd4d912c15011dc5385be40746f84db4b54432c6` |
| `fault-f0-random_forest-b8a81b52cc.json` | `aaf8004286b2e4ece3666d5d2b2a22237bceddb8191a01bf7bb909d223845882` |

The authoritative selected-candidate pool is the 50 top-level Fault JSON files referenced by `paderborn-fault-results.json`.
