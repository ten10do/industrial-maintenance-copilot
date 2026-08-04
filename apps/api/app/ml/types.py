"""Typed values shared by offline training and online inference."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Literal


@dataclass(frozen=True)
class TelemetryWindow:
    equipment_id: str
    bearing_id: str
    signal: tuple[float, ...]
    sampling_rate_hz: float
    started_at: datetime
    ended_at: datetime
    channel: str = "vibration"
    unit: str = "m/s2"
    operating_condition: str | None = None
    context: dict[str, float] = field(default_factory=dict)
    sample_timestamps: tuple[float, ...] | None = None


@dataclass(frozen=True)
class FeatureDefinition:
    name: str
    version: str
    unit: str
    description: str
    source: Literal["time", "frequency", "trend", "context"]


@dataclass(frozen=True)
class FeatureVector:
    bearing_id: str
    window_started_at: datetime
    window_ended_at: datetime
    schema_version: str
    values: dict[str, float]
    operating_condition: str | None = None
    quality_score: float = 1.0


@dataclass(frozen=True)
class TrainingSample:
    features: FeatureVector
    target: str | float
    group: str


@dataclass(frozen=True)
class DatasetDescriptor:
    name: str
    version: str
    manifest_path: str
    feature_schema_version: str


@dataclass(frozen=True)
class PredictionResult:
    prediction_type: str
    prediction: str | float
    probability: float | None
    confidence: float
    rul_hours: float | None
    degradation_index: float | None
    probabilities: dict[str, float]
    top_features: tuple[tuple[str, float], ...]
    model_version: str
    feature_schema_version: str
    feature_timestamp_start: datetime
    feature_timestamp_end: datetime


JsonObject = dict[str, Any]
