# Predictive ML Staging Safety Audit

Status: **PASS — NON-PRODUCTION ONLY**

The audit covers the model registry, online inference endpoint, deterministic staging probe, and their regression tests.

| Safety invariant | Enforcement |
|---|---|
| Default online lookup cannot select staging/candidate models | `active_model` filters `is_production=true`; a missing production model returns HTTP 409. |
| A staging model is opt-in | Online inference can load it only through an explicit `model_version_id`; task and `status=staging` are validated. |
| Only a promoted model creates operational risk state | `RiskPrediction` is created only when `is_production=true`; staging writes only an immutable `PredictionRecord`. |
| Staging orchestration cannot write maintenance state | The probe records audit-only `AgentRun`/`ToolInvocation` rows with `external_write=false`; it creates no WorkOrder, reservation, schedule change, or equipment command. |
| High-risk actions remain human-controlled | Staging output sets `human_approval_required=true` and `high_risk_operation_executed=false`. Production equipment commands remain behind the existing approval workflow. |
| Staging lineage is bound to the selected artifact | Prediction/model IDs must match and model, training, dataset, config, Git, feature, and artifact identifiers are recorded. |

Regression coverage verifies that demoting the only production model makes implicit inference fail, explicit staging inference succeeds, operational risk rows do not increase, the equipment/work-order/reservation state is unchanged, and the staging prediction is immutable across the dry-run workflow.

This audit proves software isolation and traceability, not model fitness, live-equipment safety, or production readiness. The V2 Paderborn artifact remains local, `staging`, and `is_production=false`.
