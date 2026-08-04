"""Persistent ML lineage, registry, metrics, and prediction records."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.models.base import TimestampMixin


class DatasetVersion(TimestampMixin, Base):
    __tablename__ = "ml_dataset_versions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(96), index=True)
    version: Mapped[str] = mapped_column(String(64), index=True)
    source_url: Mapped[str] = mapped_column(Text)
    license_name: Mapped[str] = mapped_column(String(160))
    citation: Mapped[str] = mapped_column(Text)
    manifest_path: Mapped[str] = mapped_column(String(512))
    manifest_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    raw_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_file_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_version: Mapped[str] = mapped_column(String(64))
    processed_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    feature_schema_version: Mapped[str] = mapped_column(String(64))
    downloaded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class MLFeatureDefinition(TimestampMixin, Base):
    __tablename__ = "ml_feature_definitions"
    __table_args__ = (
        Index("uq_ml_feature_schema_name", "schema_version", "name", unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[str] = mapped_column(String(64), index=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    source: Mapped[str] = mapped_column(String(24))
    unit: Mapped[str] = mapped_column(String(48))
    description: Mapped[str] = mapped_column(Text)


class TrainingRun(TimestampMixin, Base):
    __tablename__ = "ml_training_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_name: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    dataset_version_id: Mapped[int] = mapped_column(
        ForeignKey("ml_dataset_versions.id"), index=True
    )
    feature_schema_version: Mapped[str] = mapped_column(String(64))
    config_path: Mapped[str] = mapped_column(String(512))
    config_sha256: Mapped[str] = mapped_column(String(64))
    git_commit_sha: Mapped[str] = mapped_column(String(40))
    seed: Mapped[int] = mapped_column(Integer)
    train_samples: Mapped[int] = mapped_column(Integer)
    validation_samples: Mapped[int] = mapped_column(Integer)
    test_samples: Mapped[int] = mapped_column(Integer)
    group_count: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(24), default="running", index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ModelVersion(TimestampMixin, Base):
    __tablename__ = "ml_model_versions"
    __table_args__ = (
        Index(
            "uq_ml_model_active_production_task",
            "task_type",
            unique=True,
            sqlite_where=text("is_production = 1"),
            postgresql_where=text("is_production"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), index=True)
    task_type: Mapped[str] = mapped_column(String(32), index=True)
    algorithm: Mapped[str] = mapped_column(String(96))
    version: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    dataset_version_id: Mapped[int] = mapped_column(
        ForeignKey("ml_dataset_versions.id"), index=True
    )
    training_run_id: Mapped[int] = mapped_column(
        ForeignKey("ml_training_runs.id"), index=True
    )
    feature_schema_version: Mapped[str] = mapped_column(String(64))
    git_commit_sha: Mapped[str] = mapped_column(String(40))
    training_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    training_finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    artifact_path: Mapped[str] = mapped_column(String(512))
    artifact_sha256: Mapped[str] = mapped_column(String(64))
    hyperparameters: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(24), default="registered", index=True)
    is_production: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class ModelMetric(TimestampMixin, Base):
    __tablename__ = "ml_model_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("ml_model_versions.id", ondelete="CASCADE"), index=True
    )
    split: Mapped[str] = mapped_column(String(24), index=True)
    metric_name: Mapped[str] = mapped_column(String(96), index=True)
    metric_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    structured_value: Mapped[dict[str, Any] | list[Any] | None] = mapped_column(
        JSON, nullable=True
    )


class PredictionRecord(TimestampMixin, Base):
    __tablename__ = "ml_prediction_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    equipment_id: Mapped[int] = mapped_column(
        ForeignKey("equipment.id", ondelete="CASCADE"), index=True
    )
    model_version_id: Mapped[int] = mapped_column(
        ForeignKey("ml_model_versions.id"), index=True
    )
    prediction_type: Mapped[str] = mapped_column(String(32), index=True)
    prediction: Mapped[str] = mapped_column(String(128))
    prediction_value: Mapped[float | None] = mapped_column(Float, nullable=True)
    probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[float] = mapped_column(Float)
    prediction_horizon: Mapped[str | None] = mapped_column(String(128), nullable=True)
    rul_hours: Mapped[float | None] = mapped_column(Float, nullable=True)
    degradation_index: Mapped[float | None] = mapped_column(Float, nullable=True)
    feature_timestamp_start: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    feature_timestamp_end: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), index=True
    )
    feature_schema_version: Mapped[str] = mapped_column(String(64))
    probabilities: Mapped[dict[str, float] | None] = mapped_column(JSON, nullable=True)
    top_contributing_features: Mapped[list[dict[str, Any]] | None] = mapped_column(
        JSON, nullable=True
    )
