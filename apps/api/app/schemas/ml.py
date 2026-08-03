"""ML registry and online-inference API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OnlineInferenceIn(BaseModel):
    equipment_id: int
    bearing_id: str = Field(min_length=1, max_length=128)
    task_type: str = Field(pattern="^(failure_risk|fault_classification|rul)$")
    signal: list[float] = Field(min_length=32)
    sampling_rate_hz: float = Field(gt=0)
    started_at: datetime
    ended_at: datetime
    unit: str = "m/s2"
    operating_condition: str | None = None
    context: dict[str, float] = Field(default_factory=dict)


class ModelStatusIn(BaseModel):
    status: str = Field(pattern="^(registered|candidate|staging|production|archived)$")


class RollbackIn(BaseModel):
    task_type: str = Field(pattern="^(failure_risk|fault_classification|rul)$")
    target_model_id: int


class ModelVersionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    task_type: str
    algorithm: str
    version: str
    dataset_version_id: int
    training_run_id: int
    feature_schema_version: str
    git_commit_sha: str
    artifact_path: str
    artifact_sha256: str
    status: str
    is_production: bool
    created_at: datetime


class PredictionOut(BaseModel):
    prediction_record_id: int
    prediction_type: str
    prediction: str | float
    probability: float | None
    confidence: float
    prediction_horizon: str | None
    rul_hours: float | None
    degradation_index: float | None
    probabilities: dict[str, float]
    top_contributing_features: list[dict[str, str | float]]
    model_version: str
    feature_schema_version: str
    feature_timestamp_start: datetime
    feature_timestamp_end: datetime
