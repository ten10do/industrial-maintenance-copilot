"""ML registry and deterministic online inference endpoints."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import admin_only, get_current_user, supervisor_or_admin
from app.db.session import get_db
from app.ml.artifacts import load_artifact_bundle
from app.ml.features import extract_features
from app.ml.inference import predict
from app.ml.registry import active_model, promote_model, rollback_model
from app.ml.types import TelemetryWindow
from app.ml.validation import SignalValidationError
from app.models.base import RiskLevelEnum
from app.models.equipment import Equipment
from app.models.intelligence import RiskPrediction
from app.models.ml import ModelVersion, PredictionRecord
from app.models.user import User
from app.schemas.ml import (
    ModelStatusIn,
    ModelVersionOut,
    OnlineInferenceIn,
    PredictionOut,
    RollbackIn,
)

router = APIRouter(prefix="/ml", tags=["predictive-ml"])


@router.get("/models", response_model=list[ModelVersionOut])
def list_models(
    task_type: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ModelVersion]:
    query = db.query(ModelVersion)
    if task_type:
        query = query.filter(ModelVersion.task_type == task_type)
    return query.order_by(ModelVersion.created_at.desc()).all()


@router.post("/models/{model_id}/status", response_model=ModelVersionOut)
def change_model_status(
    model_id: int,
    payload: ModelStatusIn,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
) -> ModelVersion:
    try:
        return promote_model(db, model_id, payload.status)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/models/rollback", response_model=ModelVersionOut)
def rollback(
    payload: RollbackIn,
    db: Session = Depends(get_db),
    _: User = Depends(admin_only),
) -> ModelVersion:
    try:
        return rollback_model(db, payload.task_type, payload.target_model_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/inference", response_model=PredictionOut)
def online_inference(
    payload: OnlineInferenceIn,
    db: Session = Depends(get_db),
    _: User = Depends(supervisor_or_admin),
) -> PredictionOut:
    equipment = db.get(Equipment, payload.equipment_id)
    if equipment is None:
        raise HTTPException(status_code=404, detail="equipment not found")
    registered = active_model(db, payload.task_type)
    if registered is None:
        raise HTTPException(
            status_code=409,
            detail="no production ML model for this task; operational rules remain available",
        )
    try:
        artifact = load_artifact_bundle(
            Path(registered.artifact_path),
            expected_sha256=registered.artifact_sha256,
            expected_model_version=registered.version,
            expected_feature_schema_version=registered.feature_schema_version,
        )
        vector = extract_features(
            TelemetryWindow(
                equipment_id=str(payload.equipment_id),
                bearing_id=payload.bearing_id,
                signal=tuple(payload.signal),
                sampling_rate_hz=payload.sampling_rate_hz,
                started_at=payload.started_at,
                ended_at=payload.ended_at,
                unit=payload.unit,
                operating_condition=payload.operating_condition,
                context=payload.context,
            )
        )
        result = predict(artifact, vector)
    except (FileNotFoundError, SignalValidationError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    top_features: list[dict[str, str | float]] = [
        {"name": name, "contribution": contribution}
        for name, contribution in result.top_features
    ]
    record = PredictionRecord(
        equipment_id=equipment.id,
        model_version_id=registered.id,
        prediction_type=result.prediction_type,
        prediction=str(result.prediction),
        prediction_value=float(result.prediction)
        if isinstance(result.prediction, float)
        else None,
        probability=result.probability,
        confidence=result.confidence,
        prediction_horizon=artifact.metadata.get("prediction_horizon"),
        rul_hours=result.rul_hours,
        degradation_index=result.degradation_index,
        feature_timestamp_start=result.feature_timestamp_start,
        feature_timestamp_end=result.feature_timestamp_end,
        feature_schema_version=result.feature_schema_version,
        probabilities=result.probabilities or None,
        top_contributing_features=top_features or None,
    )
    db.add(record)
    if result.prediction_type != "rul" and result.probability is not None:
        db.add(
            RiskPrediction(
                equipment_id=equipment.id,
                risk_level=_risk_level(result.probability),
                failure_mode=str(result.prediction),
                probability=result.probability,
                factors=[str(item["name"]) for item in top_features],
                model_version=registered.version,
                is_mock=False,
            )
        )
    db.commit()
    db.refresh(record)
    return PredictionOut(
        prediction_record_id=record.id,
        prediction_type=result.prediction_type,
        prediction=result.prediction,
        probability=result.probability,
        confidence=result.confidence,
        prediction_horizon=record.prediction_horizon,
        rul_hours=result.rul_hours,
        degradation_index=result.degradation_index,
        probabilities=result.probabilities,
        top_contributing_features=top_features,
        model_version=result.model_version,
        feature_schema_version=result.feature_schema_version,
        feature_timestamp_start=result.feature_timestamp_start,
        feature_timestamp_end=result.feature_timestamp_end,
    )


@router.get("/predictions", response_model=None)
def list_ml_predictions(
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[PredictionRecord]:
    return (
        db.query(PredictionRecord)
        .order_by(PredictionRecord.created_at.desc())
        .limit(limit)
        .all()
    )


def _risk_level(probability: float) -> RiskLevelEnum:
    if probability >= 0.85:
        return RiskLevelEnum.critical
    if probability >= 0.65:
        return RiskLevelEnum.high
    if probability >= 0.4:
        return RiskLevelEnum.medium
    return RiskLevelEnum.low
