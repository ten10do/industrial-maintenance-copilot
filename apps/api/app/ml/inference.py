"""Deterministic inference and model-derived feature attribution."""

from __future__ import annotations

from typing import Any, cast

import numpy as np

from app.ml.artifacts import LoadedArtifact
from app.ml.types import FeatureVector, PredictionResult
from app.ml.v2_research import PaderbornFaultV2Preprocessor


def predict(artifact: LoadedArtifact, features: FeatureVector) -> PredictionResult:
    if features.schema_version != artifact.metadata["feature_schema_version"]:
        raise ValueError("online feature schema does not match model artifact")
    v2_preprocessor = (
        artifact.preprocessor
        if isinstance(artifact.preprocessor, PaderbornFaultV2Preprocessor)
        else None
    )
    if v2_preprocessor is not None:
        transformed = v2_preprocessor.transform_values(
            features.values, features.operating_condition
        )
    else:
        missing = [
            name for name in artifact.feature_names if name not in features.values
        ]
        if missing:
            raise ValueError(f"online feature vector is missing: {', '.join(missing)}")
        raw = np.asarray(
            [[features.values[name] for name in artifact.feature_names]],
            dtype=np.float64,
        )
        transformed = artifact.preprocessor.transform(raw)
    model = artifact.model
    task_type = str(artifact.metadata["task_type"])
    predicted_value = model.predict(transformed)[0]
    probabilities: dict[str, float] = {}
    probability: float | None = None
    rul_hours: float | None = None
    degradation_index: float | None = None
    if task_type == "rul":
        raw_rul_hours = float(predicted_value)
        rul_hours = max(0.0, raw_rul_hours)
        maximum_rul = artifact.metadata.get("maximum_rul_hours")
        if maximum_rul is not None and float(maximum_rul) > 0:
            degradation_index = float(
                np.clip(1.0 - rul_hours / float(maximum_rul), 0.0, 1.0)
            )
        confidence = _regression_confidence(artifact.metrics)
        prediction: str | float = raw_rul_hours
    else:
        probability_matrix = cast(Any, model).predict_proba(transformed)
        classes = [str(value) for value in cast(Any, model).classes_]
        raw_probabilities = {
            name: float(value)
            for name, value in zip(classes, probability_matrix[0], strict=True)
        }
        predicted_class = str(predicted_value)
        if v2_preprocessor is not None and task_type == "fault_classification":
            probabilities = {
                "healthy": raw_probabilities.get("0", 0.0),
                "damaged": raw_probabilities.get("1", 0.0),
            }
            probability = probabilities["damaged"]
            prediction = "damaged" if predicted_class == "1" else "healthy"
        elif task_type == "failure_risk":
            probabilities = raw_probabilities
            probability = probabilities.get("1")
            prediction = predicted_class
        elif "healthy" in raw_probabilities:
            probabilities = raw_probabilities
            probability = 1.0 - probabilities["healthy"]
            prediction = predicted_class
        else:
            probabilities = raw_probabilities
            probability = probabilities[predicted_class]
            prediction = predicted_class
        confidence = max(probabilities.values())
    top_features = (
        ()
        if v2_preprocessor is not None
        else _top_contributions(
            model, transformed[0], artifact.feature_names, str(predicted_value)
        )
    )
    return PredictionResult(
        prediction_type=task_type,
        prediction=prediction,
        probability=probability,
        confidence=confidence,
        rul_hours=rul_hours,
        degradation_index=degradation_index,
        probabilities=probabilities,
        top_features=top_features,
        model_version=str(artifact.metadata["model_version"]),
        feature_schema_version=features.schema_version,
        feature_timestamp_start=features.window_started_at,
        feature_timestamp_end=features.window_ended_at,
    )


def _top_contributions(
    model: Any,
    transformed: np.ndarray[Any, Any],
    feature_names: tuple[str, ...],
    predicted_class: str,
    limit: int = 5,
) -> tuple[tuple[str, float], ...]:
    if hasattr(model, "coef_"):
        coefficients = np.asarray(model.coef_)
        row = 0
        if (
            coefficients.ndim == 2
            and coefficients.shape[0] > 1
            and hasattr(model, "classes_")
        ):
            class_names = [str(value) for value in model.classes_]
            row = class_names.index(predicted_class)
        weights = coefficients[row] if coefficients.ndim == 2 else coefficients
        contributions = transformed * weights
    elif hasattr(model, "feature_importances_"):
        contributions = np.abs(transformed) * np.asarray(model.feature_importances_)
    else:
        return ()
    ranked = sorted(
        zip(feature_names, contributions.tolist(), strict=True),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    return tuple((name, float(value)) for name, value in ranked[:limit])


def _regression_confidence(metrics: dict[str, Any]) -> float:
    test = metrics.get("test", {})
    relative_error = test.get("relative_error") if isinstance(test, dict) else None
    if relative_error is None:
        return 0.0
    return float(np.clip(1.0 - float(relative_error), 0.0, 1.0))
