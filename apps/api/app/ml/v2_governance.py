"""Frozen-test, experiment-tracking, and V2 promotion governance."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray


@dataclass(frozen=True, slots=True)
class PaderbornAccessPolicy:
    development: frozenset[str]
    frozen_test: frozenset[str]

    @classmethod
    def from_manifest(cls, path: Path) -> PaderbornAccessPolicy:
        manifest = _read_json(path)
        if (
            not manifest.get("locked")
            or manifest.get("frozen_test_accessed") is not False
        ):
            raise ValueError("Paderborn V2 manifest is not locked before test access")
        development = frozenset(str(item) for item in manifest["development_bearings"])
        frozen = frozenset(str(item) for item in manifest["frozen_test_bearings"])
        if not development or not frozen or development & frozen:
            raise ValueError("invalid development/frozen-test partition")
        return cls(development=development, frozen_test=frozen)

    def require_development(self, bearing_id: str) -> None:
        if bearing_id in self.frozen_test:
            raise PermissionError(f"frozen Paderborn test access denied: {bearing_id}")
        if bearing_id not in self.development:
            raise ValueError(f"unknown Paderborn bearing: {bearing_id}")

    def validate_development_groups(self, groups: list[str]) -> None:
        for bearing_id in groups:
            self.require_development(bearing_id)
        if set(groups) != self.development:
            missing = sorted(self.development - set(groups))
            raise ValueError(f"development dataset is incomplete: {missing}")


def hierarchical_fault_targets(
    fault_classes: list[str],
    subtype_labels: list[str] | None = None,
    *,
    minimum_bearings_per_subtype: int = 5,
) -> tuple[NDArray[np.int_], bool]:
    stage_one = np.asarray(
        [0 if value == "healthy" else 1 for value in fault_classes], dtype=np.int_
    )
    if subtype_labels is None:
        return stage_one, False
    damaged_subtypes = [
        subtype
        for subtype, damaged in zip(subtype_labels, stage_one, strict=True)
        if damaged
    ]
    counts = {value: damaged_subtypes.count(value) for value in set(damaged_subtypes)}
    eligible = bool(counts) and min(counts.values()) >= minimum_bearings_per_subtype
    return stage_one, eligible


def trajectory_metrics(
    predictions_by_bearing: dict[str, NDArray[np.float64]],
    *,
    significant_jump_hours: float = 0.5,
) -> dict[str, Any]:
    per_bearing: dict[str, dict[str, float | int]] = {}
    all_positive: list[float] = []
    rates: list[float] = []
    total_count = 0
    for bearing_id, values in sorted(predictions_by_bearing.items()):
        predictions = np.asarray(values, dtype=np.float64)
        if predictions.ndim != 1 or not len(predictions):
            raise ValueError("each RUL trajectory must be a non-empty vector")
        jumps = np.maximum(np.diff(predictions), 0.0)
        positive = jumps[jumps > 0]
        count = int(np.sum(jumps > significant_jump_hours))
        rate = count / max(len(predictions) - 1, 1)
        all_positive.extend(float(value) for value in positive)
        rates.append(rate)
        total_count += count
        per_bearing[bearing_id] = {
            "oscillation_count": count,
            "oscillation_rate": float(rate),
            "mean_positive_jump": float(np.mean(positive)) if len(positive) else 0.0,
            "max_positive_jump": float(np.max(positive)) if len(positive) else 0.0,
        }
    return {
        "oscillation_count": total_count,
        "mean_per_bearing_oscillation_rate": float(np.mean(rates)),
        "mean_positive_jump": float(np.mean(all_positive)) if all_positive else 0.0,
        "max_positive_jump": float(np.max(all_positive)) if all_positive else 0.0,
        "significant_jump_hours": significant_jump_hours,
        "per_bearing": per_bearing,
    }


def causal_ewma(
    values: NDArray[np.float64], *, alpha: float = 0.20
) -> NDArray[np.float64]:
    predictions = np.asarray(values, dtype=np.float64)
    if predictions.ndim != 1 or not len(predictions):
        raise ValueError("EWMA requires a non-empty vector")
    if not 0 < alpha <= 1:
        raise ValueError("alpha must be in (0, 1]")
    smoothed = np.empty_like(predictions)
    smoothed[0] = predictions[0]
    for index in range(1, len(predictions)):
        smoothed[index] = alpha * predictions[index] + (1 - alpha) * smoothed[index - 1]
    return smoothed


def fault_promotion(metrics: dict[str, float]) -> dict[str, Any]:
    checks = {
        "macro_recall_at_least_0_70": metrics["macro_recall"] >= 0.70,
        "healthy_recall_at_least_0_60": metrics["healthy_recall"] >= 0.60,
    }
    return {"passed": all(checks.values()), "checks": checks}


def rul_promotion(metrics: dict[str, float]) -> dict[str, Any]:
    checks = {
        "mae_at_most_5h": metrics["mae"] <= 5.0,
        "r2_above_zero": metrics["r2"] > 0.0,
        "late_error_at_most_3h": metrics["late_prediction_error"] <= 3.0,
        "oscillation_rate_at_most_0_10": metrics["mean_per_bearing_oscillation_rate"]
        <= 0.10,
    }
    return {"passed": all(checks.values()), "checks": checks}


@dataclass(slots=True)
class ExperimentRun:
    experiment_id: str
    dataset_version: str
    feature_version: str
    fold_manifest: str
    algorithm: str
    hyperparameters: dict[str, Any]
    seed: int
    git_sha: str
    started_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    finished_at: str | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    artifact_hash: str | None = None

    def finish(
        self, metrics: dict[str, Any], *, artifact_path: Path | None = None
    ) -> None:
        self.metrics = metrics
        self.finished_at = datetime.now(UTC).isoformat()
        self.artifact_hash = _sha256(artifact_path) if artifact_path else None

    def write(self, path: Path) -> None:
        if self.finished_at is None:
            raise ValueError("cannot write an unfinished experiment run")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
