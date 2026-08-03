"""Safety-oriented model metrics for classification and RUL regression."""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    median_absolute_error,
    precision_recall_curve,
    precision_score,
    r2_score,
    recall_score,
    roc_auc_score,
    roc_curve,
)


def evaluate_binary_classification(
    truth: NDArray[np.int_],
    predicted: NDArray[np.int_],
    failure_probability: NDArray[np.float64],
) -> dict[str, Any]:
    matrix = confusion_matrix(truth, predicted, labels=[0, 1])
    true_negative, false_positive, false_negative, true_positive = matrix.ravel()
    negative_count = true_negative + false_positive
    positive_count = true_positive + false_negative
    return {
        "accuracy": float(accuracy_score(truth, predicted)),
        "precision": float(precision_score(truth, predicted, zero_division=0)),
        "recall": float(recall_score(truth, predicted, zero_division=0)),
        "f1": float(f1_score(truth, predicted, zero_division=0)),
        "roc_auc": _safe_auc(roc_auc_score, truth, failure_probability),
        "pr_auc": _safe_auc(average_precision_score, truth, failure_probability),
        "confusion_matrix": matrix.tolist(),
        "false_negative_rate": float(false_negative / max(positive_count, 1)),
        "false_positive_rate": float(false_positive / max(negative_count, 1)),
        "brier_score": float(brier_score_loss(truth, failure_probability)),
        "calibration_curve": _calibration_curve(truth, failure_probability),
        "pr_curve": _curve_points(
            *precision_recall_curve(truth, failure_probability)[:2],
            x_name="recall",
            y_name="precision",
            reverse=True,
        ),
        "roc_curve": _curve_points(
            *roc_curve(truth, failure_probability)[:2],
            x_name="false_positive_rate",
            y_name="true_positive_rate",
        ),
    }


def evaluate_multiclass_classification(
    truth: NDArray[np.str_],
    predicted: NDArray[np.str_],
    probabilities: NDArray[np.float64],
    classes: NDArray[np.str_],
) -> dict[str, Any]:
    encoded = np.column_stack([(truth == name).astype(int) for name in classes])
    matrix = confusion_matrix(truth, predicted, labels=classes)
    false_negatives = matrix.sum(axis=1) - np.diag(matrix)
    false_positives = matrix.sum(axis=0) - np.diag(matrix)
    positives = matrix.sum(axis=1)
    negatives = matrix.sum() - positives
    per_class = {
        str(name): {
            "precision": float(
                precision_score(
                    truth, predicted, labels=[name], average=None, zero_division=0
                )[0]
            ),
            "recall": float(
                recall_score(
                    truth, predicted, labels=[name], average=None, zero_division=0
                )[0]
            ),
            "f1": float(
                f1_score(
                    truth, predicted, labels=[name], average=None, zero_division=0
                )[0]
            ),
            "support": int(np.sum(truth == name)),
        }
        for name in classes
    }
    calibration = {
        str(name): _calibration_curve(encoded[:, index], probabilities[:, index])
        for index, name in enumerate(classes)
    }
    pr_curves: dict[str, list[dict[str, float]]] = {}
    roc_curves: dict[str, list[dict[str, float]]] = {}
    for index, name in enumerate(classes):
        precision, recall, _ = precision_recall_curve(
            encoded[:, index], probabilities[:, index]
        )
        pr_curves[str(name)] = _curve_points(
            recall,
            precision,
            x_name="recall",
            y_name="precision",
            reverse=True,
        )
        false_positive, true_positive, _ = roc_curve(
            encoded[:, index], probabilities[:, index]
        )
        roc_curves[str(name)] = _curve_points(
            false_positive,
            true_positive,
            x_name="false_positive_rate",
            y_name="true_positive_rate",
        )
    return {
        "accuracy": float(accuracy_score(truth, predicted)),
        "precision": float(
            precision_score(truth, predicted, average="macro", zero_division=0)
        ),
        "recall": float(
            recall_score(truth, predicted, average="macro", zero_division=0)
        ),
        "f1": float(f1_score(truth, predicted, average="macro", zero_division=0)),
        "weighted_precision": float(
            precision_score(truth, predicted, average="weighted", zero_division=0)
        ),
        "weighted_recall": float(
            recall_score(truth, predicted, average="weighted", zero_division=0)
        ),
        "weighted_f1": float(
            f1_score(truth, predicted, average="weighted", zero_division=0)
        ),
        "roc_auc": _safe_auc(roc_auc_score, encoded, probabilities, average="macro"),
        "pr_auc": _safe_auc(
            average_precision_score, encoded, probabilities, average="macro"
        ),
        "confusion_matrix": matrix.tolist(),
        "false_negative_rate": float(
            np.mean(false_negatives / np.maximum(positives, 1))
        ),
        "false_positive_rate": float(
            np.mean(false_positives / np.maximum(negatives, 1))
        ),
        "brier_score": float(np.mean(np.square(encoded - probabilities))),
        "per_class": per_class,
        "calibration_curve": calibration,
        "pr_curve": pr_curves,
        "roc_curve": roc_curves,
    }


def evaluate_rul(
    truth: NDArray[np.float64], predicted: NDArray[np.float64]
) -> dict[str, float]:
    error = predicted - truth
    late = np.maximum(error, 0.0)
    early = np.maximum(-error, 0.0)
    relative = np.abs(error) / np.maximum(np.abs(truth), 1.0)
    return {
        "mae": float(mean_absolute_error(truth, predicted)),
        "rmse": float(math.sqrt(mean_squared_error(truth, predicted))),
        "median_absolute_error": float(median_absolute_error(truth, predicted)),
        "r2": float(r2_score(truth, predicted)),
        "relative_error": float(np.mean(relative)),
        "early_prediction_error": float(np.mean(early)),
        "late_prediction_error": float(np.mean(late)),
    }


def _safe_auc(metric: Any, truth: Any, probability: Any, **kwargs: Any) -> float | None:
    try:
        return float(metric(truth, probability, **kwargs))
    except ValueError:
        return None


def _calibration_curve(
    truth: NDArray[np.int_], probability: NDArray[np.float64], bins: int = 10
) -> list[dict[str, float | int]]:
    edges = np.linspace(0.0, 1.0, bins + 1)
    result: list[dict[str, float | int]] = []
    for index in range(bins):
        upper_inclusive = index == bins - 1
        mask = (probability >= edges[index]) & (
            probability <= edges[index + 1]
            if upper_inclusive
            else probability < edges[index + 1]
        )
        if not np.any(mask):
            continue
        result.append(
            {
                "mean_predicted_probability": float(np.mean(probability[mask])),
                "observed_frequency": float(np.mean(truth[mask])),
                "count": int(np.sum(mask)),
            }
        )
    return result


def _curve_points(
    x: NDArray[np.float64],
    y: NDArray[np.float64],
    *,
    x_name: str,
    y_name: str,
    reverse: bool = False,
    maximum_points: int = 200,
) -> list[dict[str, float]]:
    if reverse:
        x = x[::-1]
        y = y[::-1]
    if len(x) > maximum_points:
        selected = np.linspace(0, len(x) - 1, maximum_points, dtype=int)
        x = x[selected]
        y = y[selected]
    return [
        {x_name: float(x_value), y_name: float(y_value)}
        for x_value, y_value in zip(x, y, strict=True)
    ]
