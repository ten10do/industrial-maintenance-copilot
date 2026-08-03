"""Leakage-resistant training orchestration for prepared bearing features."""

from __future__ import annotations

import hashlib
import json
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, cast

import numpy as np
import yaml
from numpy.typing import NDArray
from sklearn.base import BaseEstimator
from sklearn.ensemble import (
    HistGradientBoostingClassifier,
    HistGradientBoostingRegressor,
    RandomForestClassifier,
    RandomForestRegressor,
)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.preprocessing import StandardScaler

from app.ml.artifacts import save_artifact_bundle
from app.ml.evaluation import (
    evaluate_binary_classification,
    evaluate_multiclass_classification,
    evaluate_rul,
)
from app.ml.selection import CandidateMetrics, select_failure_model, select_rul_model
from app.ml.splitting import (
    GroupedSplit,
    group_split_audit,
    grouped_train_validation_test_split,
)

TaskType = Literal["failure_risk", "fault_classification", "rul"]


@dataclass(frozen=True)
class PreparedDataset:
    features: NDArray[np.float64]
    targets: NDArray[Any]
    groups: list[str]
    feature_names: list[str]
    dataset_name: str
    dataset_version: str
    feature_schema_version: str
    processed_sha256: str


@dataclass(frozen=True)
class TrainingOutcome:
    model_version: str
    algorithm: str
    artifact_path: Path
    artifact_sha256: str
    validation_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    split: GroupedSplit
    leakage_audit: dict[str, object]


def load_prepared_dataset(path: Path, expected_dataset: str) -> PreparedDataset:
    if not path.is_file():
        raise FileNotFoundError(
            f"processed dataset not found: {path}; follow data/README.md first"
        )
    with np.load(path, allow_pickle=False) as payload:
        required = {
            "features",
            "targets",
            "groups",
            "feature_names",
            "dataset_name",
            "dataset_version",
            "feature_schema_version",
        }
        missing = required - set(payload.files)
        if missing:
            raise ValueError(f"prepared dataset missing arrays: {sorted(missing)}")
        dataset_name = str(payload["dataset_name"].item())
        if dataset_name != expected_dataset:
            raise ValueError(
                f"expected dataset {expected_dataset}, found {dataset_name}"
            )
        features = np.asarray(payload["features"], dtype=np.float64)
        targets = np.asarray(payload["targets"])
        groups = [str(value) for value in payload["groups"].tolist()]
        names = [str(value) for value in payload["feature_names"].tolist()]
        if features.ndim != 2 or features.shape[0] != len(groups):
            raise ValueError("features must be a 2D array aligned with groups")
        if features.shape[1] != len(names) or len(targets) != len(groups):
            raise ValueError("targets or feature names are not aligned")
        if not np.isfinite(features).all():
            raise ValueError("prepared feature matrix contains NaN or Inf")
        return PreparedDataset(
            features=features,
            targets=targets,
            groups=groups,
            feature_names=names,
            dataset_name=dataset_name,
            dataset_version=str(payload["dataset_version"].item()),
            feature_schema_version=str(payload["feature_schema_version"].item()),
            processed_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        )


def train_from_config(
    *, dataset_name: str, config_path: Path, expected_task: TaskType
) -> TrainingOutcome:
    training_started_at = datetime.now(UTC)
    config = _load_config(config_path)
    if (
        config.get("dataset") != dataset_name
        or config.get("task_type") != expected_task
    ):
        raise ValueError("CLI dataset/task does not match experiment config")
    dataset = load_prepared_dataset(
        _config_relative_path(config_path, config["processed_path"]), dataset_name
    )
    seed = int(config["seed"])
    split_config = cast(dict[str, Any], config["split"])
    split = grouped_train_validation_test_split(
        dataset.groups,
        test_size=float(split_config["test_size"]),
        validation_size=float(split_config["validation_size"]),
        seed=seed,
    )
    leakage_audit = group_split_audit(split, dataset.groups).as_dict()
    candidates: list[tuple[str, BaseEstimator, StandardScaler, dict[str, Any]]] = []
    validation_records: list[CandidateMetrics] = []
    for model_config in cast(list[dict[str, Any]], config["models"]):
        name = str(model_config["algorithm"])
        estimator = _build_estimator(
            expected_task, name, model_config.get("hyperparameters", {}), seed
        )
        scaler = StandardScaler().fit(dataset.features[split.train])
        estimator.fit(
            scaler.transform(dataset.features[split.train]),
            dataset.targets[split.train],
        )
        metrics = _evaluate(
            expected_task,
            estimator,
            scaler.transform(dataset.features[split.validation]),
            dataset.targets[split.validation],
        )
        candidates.append(
            (name, estimator, scaler, dict(model_config.get("hyperparameters", {})))
        )
        validation_records.append(CandidateMetrics(name=name, metrics=metrics))
    if expected_task == "rul":
        selected = select_rul_model(
            validation_records,
            maximum_late_error=_optional_float(config.get("maximum_late_error")),
        )
    else:
        selected = select_failure_model(
            validation_records, minimum_recall=float(config["minimum_recall"])
        )
    name, model, scaler, hyperparameters = next(
        item for item in candidates if item[0] == selected.name
    )
    test_metrics = _evaluate(
        expected_task,
        model,
        scaler.transform(dataset.features[split.test]),
        dataset.targets[split.test],
    )
    importance = permutation_importance(
        model,
        scaler.transform(dataset.features[split.validation]),
        dataset.targets[split.validation],
        n_repeats=5,
        random_state=seed,
        scoring="neg_mean_absolute_error" if expected_task == "rul" else "f1_macro",
    )
    global_importance = sorted(
        zip(dataset.feature_names, importance.importances_mean.tolist(), strict=True),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    version = f"{expected_task}-{name}-{timestamp}"
    output_dir = _config_relative_path(config_path, config["output_dir"]) / version
    validation_metrics = dict(selected.metrics)
    validation_metrics["permutation_importance"] = [
        {"feature": feature, "importance": float(value)}
        for feature, value in global_importance
    ]
    promotion = _promotion_decision(
        expected_task,
        validation_metrics,
        cast(dict[str, Any], config.get("promotion_threshold", {})),
    )
    artifact_hash = save_artifact_bundle(
        output_dir,
        model=model,
        preprocessor=scaler,
        feature_names=dataset.feature_names,
        feature_schema_version=dataset.feature_schema_version,
        model_version=version,
        metadata={
            "task_type": expected_task,
            "algorithm": name,
            "dataset_name": dataset.dataset_name,
            "dataset_version": dataset.dataset_version,
            "processed_sha256": dataset.processed_sha256,
            "git_commit_sha": _git_commit(),
            "prediction_horizon": config.get("prediction_horizon"),
            "maximum_rul_hours": config.get("maximum_rul_hours"),
            "hyperparameters": hyperparameters,
            "split_groups": {
                "train": sorted({dataset.groups[index] for index in split.train}),
                "validation": sorted(
                    {dataset.groups[index] for index in split.validation}
                ),
                "test": sorted({dataset.groups[index] for index in split.test}),
            },
            "leakage_audit": leakage_audit,
            "fit_provenance": {
                "preprocessor_fit_split": "train",
                "preprocessor_fit_samples": int(scaler.n_samples_seen_),
                "model_fit_split": "train",
                "feature_selector": "not_configured",
                "model_selection_split": "validation",
                "test_set_usage": "final_selected_model_evaluation_only",
            },
            "config_sha256": hashlib.sha256(config_path.read_bytes()).hexdigest(),
            "config_path": str(config_path),
            "run_name": config.get("run_name", version),
            "seed": seed,
            "sample_counts": {
                "train": len(split.train),
                "validation": len(split.validation),
                "test": len(split.test),
                "groups": len(set(dataset.groups)),
            },
            "training_started_at": training_started_at.isoformat(),
            "training_finished_at": datetime.now(UTC).isoformat(),
        },
        metrics={
            "validation": validation_metrics,
            "test": test_metrics,
            "promotion": promotion,
        },
    )
    return TrainingOutcome(
        model_version=version,
        algorithm=name,
        artifact_path=output_dir,
        artifact_sha256=artifact_hash,
        validation_metrics=validation_metrics,
        test_metrics=test_metrics,
        split=split,
        leakage_audit=leakage_audit,
    )


def safe_summary(outcome: TrainingOutcome, dataset: str) -> str:
    return json.dumps(
        {
            "dataset": dataset,
            "train_samples": len(outcome.split.train),
            "validation_samples": len(outcome.split.validation),
            "test_samples": len(outcome.split.test),
            "leakage_audit": outcome.leakage_audit,
            "algorithm": outcome.algorithm,
            "validation_metrics": outcome.validation_metrics,
            "test_metrics": outcome.test_metrics,
            "artifact_path": str(outcome.artifact_path),
            "model_version": outcome.model_version,
        },
        indent=2,
        default=str,
    )


def _build_estimator(
    task: TaskType, algorithm: str, hyperparameters: Any, seed: int
) -> BaseEstimator:
    params = dict(cast(dict[str, Any], hyperparameters))
    if task in {"failure_risk", "fault_classification"}:
        if algorithm == "logistic_regression":
            return LogisticRegression(random_state=seed, max_iter=2000, **params)
        if algorithm == "random_forest":
            return RandomForestClassifier(random_state=seed, **params)
        if algorithm == "hist_gradient_boosting":
            return HistGradientBoostingClassifier(random_state=seed, **params)
    elif task == "rul":
        if algorithm == "ridge":
            return Ridge(**params)
        if algorithm == "random_forest":
            return RandomForestRegressor(random_state=seed, **params)
        if algorithm == "hist_gradient_boosting":
            return HistGradientBoostingRegressor(random_state=seed, **params)
    raise ValueError(f"unsupported {task} algorithm: {algorithm}")


def _evaluate(
    task: TaskType,
    model: BaseEstimator,
    features: NDArray[np.float64],
    targets: NDArray[Any],
) -> dict[str, Any]:
    predicted = model.predict(features)
    if task == "rul":
        return evaluate_rul(
            np.asarray(targets, dtype=np.float64),
            np.asarray(predicted, dtype=np.float64),
        )
    probabilities = cast(Any, model).predict_proba(features)
    classes = np.asarray(cast(Any, model).classes_)
    if task == "failure_risk":
        positive_indices = np.flatnonzero(classes.astype(str) == "1")
        positive_index = int(positive_indices[0]) if positive_indices.size else 1
        return evaluate_binary_classification(
            np.asarray(targets, dtype=int),
            np.asarray(predicted, dtype=int),
            np.asarray(probabilities[:, positive_index], dtype=np.float64),
        )
    return evaluate_multiclass_classification(
        np.asarray(targets, dtype=str),
        np.asarray(predicted, dtype=str),
        np.asarray(probabilities, dtype=np.float64),
        np.asarray(classes, dtype=str),
    )


def _load_config(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("experiment config must be a YAML mapping")
    return cast(dict[str, Any], value)


def _git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def _optional_float(value: Any) -> float | None:
    return None if value is None else float(value)


def _config_relative_path(config_path: Path, value: Any) -> Path:
    configured = Path(str(value))
    if configured.is_absolute():
        return configured
    return (config_path.resolve().parent / configured).resolve()


def _promotion_decision(
    task: TaskType, metrics: dict[str, Any], thresholds: dict[str, Any]
) -> dict[str, Any]:
    reasons: list[str] = []
    if task == "rul":
        maximum_mae = thresholds.get("maximum_mae_hours")
        maximum_late = thresholds.get("maximum_late_error_hours")
        if maximum_mae is not None and float(metrics["mae"]) > float(maximum_mae):
            reasons.append("validation MAE exceeds promotion threshold")
        if maximum_late is not None and float(metrics["late_prediction_error"]) > float(
            maximum_late
        ):
            reasons.append("validation late error exceeds promotion threshold")
    else:
        minimum_recall = thresholds.get("minimum_recall")
        minimum_pr_auc = thresholds.get("minimum_pr_auc")
        if minimum_recall is not None and float(metrics["recall"]) < float(
            minimum_recall
        ):
            reasons.append("validation recall is below promotion threshold")
        if minimum_pr_auc is not None and (
            metrics.get("pr_auc") is None
            or float(metrics["pr_auc"]) < float(minimum_pr_auc)
        ):
            reasons.append("validation PR-AUC is below promotion threshold")
    return {"eligible": not reasons, "thresholds": thresholds, "reasons": reasons}
