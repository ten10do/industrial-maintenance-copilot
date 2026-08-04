"""Selection policies encode industrial false-negative and late-RUL costs."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CandidateMetrics:
    name: str
    metrics: Mapping[str, Any]


def select_failure_model(
    candidates: list[CandidateMetrics], *, minimum_recall: float
) -> CandidateMetrics:
    eligible = [
        item for item in candidates if _metric(item, "recall") >= minimum_recall
    ]
    if not eligible:
        raise ValueError("no failure model satisfies the minimum recall threshold")
    return max(
        eligible,
        key=lambda item: (
            _metric(item, "pr_auc"),
            _metric(item, "recall"),
            _metric(item, "f1"),
            -_metric(item, "false_negative_rate"),
        ),
    )


def select_rul_model(
    candidates: list[CandidateMetrics], *, maximum_late_error: float | None = None
) -> CandidateMetrics:
    eligible = candidates
    if maximum_late_error is not None:
        eligible = [
            item
            for item in candidates
            if _metric(item, "late_prediction_error") <= maximum_late_error
        ]
    if not eligible:
        raise ValueError("no RUL model satisfies the maximum late-error threshold")
    return min(
        eligible,
        key=lambda item: (
            _metric(item, "mae"),
            _metric(item, "rmse"),
            _metric(item, "late_prediction_error"),
        ),
    )


def _metric(candidate: CandidateMetrics, name: str) -> float:
    value = candidate.metrics.get(name)
    if value is None:
        return float("-inf") if name in {"pr_auc", "recall", "f1"} else float("inf")
    return float(value)
