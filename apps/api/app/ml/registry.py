"""Transactional lightweight model-registry promotion and rollback."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.ml import ModelVersion

VALID_STATUSES = {"registered", "candidate", "staging", "production", "archived"}


def promote_model(db: Session, model_id: int, target_status: str) -> ModelVersion:
    if target_status not in VALID_STATUSES:
        raise ValueError(f"unsupported registry status: {target_status}")
    model = db.get(ModelVersion, model_id)
    if model is None:
        raise LookupError("model version not found")
    if target_status in {"staging", "production"}:
        promotion = model.metrics.get("promotion")
        if not isinstance(promotion, dict) or not (
            promotion.get("eligible") is True or promotion.get("passed") is True
        ):
            raise ValueError("model has no passing, code-generated promotion decision")
    if target_status == "production":
        active = (
            db.query(ModelVersion)
            .filter(
                ModelVersion.task_type == model.task_type,
                ModelVersion.is_production.is_(True),
                ModelVersion.id != model.id,
            )
            .with_for_update()
            .all()
        )
        for previous in active:
            previous.is_production = False
            previous.status = "archived"
        # Flush deactivations first so the database-level partial unique index
        # remains valid throughout promotion/rollback, including on SQLite.
        db.flush()
        model.is_production = True
    else:
        model.is_production = False
    model.status = target_status
    db.commit()
    db.refresh(model)
    return model


def rollback_model(db: Session, task_type: str, target_model_id: int) -> ModelVersion:
    target = db.get(ModelVersion, target_model_id)
    if target is None or target.task_type != task_type:
        raise LookupError("rollback target does not exist for this task")
    return promote_model(db, target_model_id, "production")


def active_model(db: Session, task_type: str) -> ModelVersion | None:
    return (
        db.query(ModelVersion)
        .filter(
            ModelVersion.task_type == task_type, ModelVersion.is_production.is_(True)
        )
        .order_by(ModelVersion.created_at.desc())
        .first()
    )
