"""Non-production orchestration probe for immutable staging ML predictions."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models.intelligence import AgentRun, ToolInvocation
from app.models.ml import DatasetVersion, ModelVersion, PredictionRecord, TrainingRun

_STEPS = (
    "monitoring_agent",
    "diagnosis_agent",
    "knowledge_agent",
    "decision_agent",
    "work_order_agent",
    "scheduling_agent",
)


def record_staging_workflow_probe(
    db: Session, prediction: PredictionRecord, model: ModelVersion
) -> AgentRun:
    if model.status != "staging" or model.is_production:
        raise ValueError("workflow probe requires a non-production staging model")
    if prediction.model_version_id != model.id:
        raise ValueError("prediction/model lineage mismatch")
    training = db.get(TrainingRun, model.training_run_id)
    dataset = db.get(DatasetVersion, model.dataset_version_id)
    if training is None or dataset is None:
        raise ValueError("staging model lineage is incomplete")
    immutable = _immutable_prediction(prediction)
    lineage: dict[str, Any] = {
        "model_version": model.version,
        "model_status": model.status,
        "feature_version": model.feature_schema_version,
        "dataset_version": dataset.version,
        "artifact_sha256": model.artifact_sha256,
        "config_sha256": training.config_sha256,
        "git_commit_sha": model.git_commit_sha,
    }
    now = datetime.now(UTC)
    agent_run = AgentRun(
        equipment_id=prediction.equipment_id,
        anomaly_event_id=None,
        goal="Dry-run staging prediction through maintenance workflow",
        status="running",
        provider="deterministic-staging-probe",
        input={
            "prediction_record_id": prediction.id,
            "immutable_ml_output": immutable,
            "lineage": lineage,
        },
        confidence=prediction.confidence,
        requires_human_review=True,
        started_at=now,
    )
    db.add(agent_run)
    db.flush()
    for step in _STEPS:
        db.add(
            ToolInvocation(
                agent_run_id=agent_run.id,
                tool_name=step,
                provider="local",
                status="success",
                request={
                    "prediction_record_id": prediction.id,
                    "immutable_ml_output_sha": _stable_value(immutable),
                },
                response={
                    "mode": "dry_run",
                    "external_write": False,
                    "ml_output_mutated": False,
                    "human_approval_required": step
                    in {"work_order_agent", "scheduling_agent"},
                },
                duration_ms=0,
            )
        )
    agent_run.status = "completed"
    agent_run.output = {
        "mode": "dry_run",
        "steps": list(_STEPS),
        "prediction_record_id": prediction.id,
        "work_order_created": False,
        "parts_reserved": False,
        "schedule_changed": False,
        "high_risk_operation_executed": False,
        "human_approval_required": True,
        "immutable_ml_output": immutable,
        "lineage": lineage,
    }
    agent_run.finished_at = datetime.now(UTC)
    db.commit()
    db.refresh(prediction)
    if _immutable_prediction(prediction) != immutable:
        raise RuntimeError("staging workflow mutated the immutable ML prediction")
    db.refresh(agent_run)
    return agent_run


def _immutable_prediction(prediction: PredictionRecord) -> dict[str, Any]:
    return {
        "prediction": prediction.prediction,
        "probability": prediction.probability,
        "confidence": prediction.confidence,
        "rul_hours": prediction.rul_hours,
        "model_version_id": prediction.model_version_id,
        "feature_schema_version": prediction.feature_schema_version,
    }


def _stable_value(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
