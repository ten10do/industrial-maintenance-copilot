# Paderborn Fault V2 Non-production Staging Probe

- Registry: local SQLite only; model #2 is `staging`, `is_production=false`.
- Real input: first 4,096-sample vibration/current window from Development bearing `K001`, source `K001/N09_M07_F10_K001_1.mat`.
- PredictionRecord: #1, `healthy`, damage probability `0.00006355`, confidence `0.99993645`.
- Model/artifact: `paderborn-fault-v2-20260804T024225Z` / `68ceffc5...e73b25`.
- Dataset/feature/config: `paderborn-snapshot-e513a6320d755ce5` / `bearing-features-v2` / `2bce080f...13a9`.

AgentRun #4 executed the deterministic Workflow Orchestrator path:

`Monitoring -> Diagnosis -> Knowledge -> Decision -> Work Order -> Scheduling`

Every step ran in `dry_run` mode. The probe created no RiskPrediction, WorkOrder, parts reservation, schedule mutation, or high-risk equipment operation. Human approval remained required for work-order/scheduling actions. The PredictionRecord values were compared before and after the AgentRun and were unchanged.

This proves staging wiring and lineage, not operational effectiveness. It does not promote the model to production and does not bypass human approval.
