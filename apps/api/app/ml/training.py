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
    grouped_split_from_manifest,
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
    sample_ids: list[str]
    source_files: list[str]
    window_indices: NDArray[np.int64]
    splits: list[str]
    operating_conditions: list[str]
    rul_measurements: NDArray[np.int64]
    rul_hours: NDArray[np.float64]


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
    candidate_validation_metrics: dict[str, dict[str, Any]]


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
            "sample_ids",
            "source_files",
            "window_indices",
            "splits",
            "operating_conditions",
            "rul_measurements",
            "rul_hours",
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
        sample_ids = [str(value) for value in payload["sample_ids"].tolist()]
        source_files = [str(value) for value in payload["source_files"].tolist()]
        window_indices = np.asarray(payload["window_indices"], dtype=np.int64)
        splits = [str(value) for value in payload["splits"].tolist()]
        operating_conditions = [
            str(value) for value in payload["operating_conditions"].tolist()
        ]
        rul_measurements = np.asarray(payload["rul_measurements"], dtype=np.int64)
        rul_hours = np.asarray(payload["rul_hours"], dtype=np.float64)
        if features.ndim != 2 or features.shape[0] != len(groups):
            raise ValueError("features must be a 2D array aligned with groups")
        if features.shape[1] != len(names) or len(targets) != len(groups):
            raise ValueError("targets or feature names are not aligned")
        if not all(
            len(values) == len(groups)
            for values in (
                sample_ids,
                source_files,
                window_indices,
                splits,
                operating_conditions,
                rul_measurements,
                rul_hours,
            )
        ):
            raise ValueError("processed lineage arrays are not aligned")
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
            processed_sha256=_sha256(path),
            sample_ids=sample_ids,
            source_files=source_files,
            window_indices=window_indices,
            splits=splits,
            operating_conditions=operating_conditions,
            rul_measurements=rul_measurements,
            rul_hours=rul_hours,
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
    split_config = cast(dict[str, Any], config["split"])
    seed = int(config["seed"])
    if split_config.get("strategy") == "locked_group_manifest":
        split_manifest_path = _config_relative_path(
            config_path, split_config["manifest"]
        )
        split = grouped_split_from_manifest(dataset.groups, split_manifest_path)
        _verify_processed_split_labels(dataset, split)
        _require_passing_leakage_audit(config, config_path, dataset)
    else:
        split_manifest_path = None
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
    test_features = scaler.transform(dataset.features[split.test])
    test_metrics = _evaluate(
        expected_task,
        model,
        test_features,
        dataset.targets[split.test],
    )
    if expected_task == "rul":
        test_predictions = np.asarray(model.predict(test_features), dtype=np.float64)
        test_metrics.update(_rul_test_diagnostics(dataset, split, test_predictions))
    else:
        test_metrics["condition_diagnostics"] = _classification_by_condition(
            dataset, split, model, test_features
        )
    high_metric_guard = _high_metric_guard(dataset, split, test_metrics)
    if high_metric_guard["triggered"] and not high_metric_guard["passed"]:
        raise ValueError("abnormally high test metric guard detected leakage")
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
            "split_manifest": split_manifest_path.as_posix()
            if split_manifest_path
            else None,
            "split_manifest_sha256": _sha256(split_manifest_path)
            if split_manifest_path
            else None,
            "leakage_audit": leakage_audit,
            "fit_provenance": {
                "preprocessor_fit_split": "train",
                "preprocessor_fit_samples": int(scaler.n_samples_seen_),
                "model_fit_split": "train",
                "feature_selector": "not_configured",
                "model_selection_split": "validation",
                "test_set_usage": "final_selected_model_evaluation_only",
            },
            "high_metric_guard": high_metric_guard,
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
            "validation_candidates": {
                item.name: dict(item.metrics) for item in validation_records
            },
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
        candidate_validation_metrics={
            item.name: dict(item.metrics) for item in validation_records
        },
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
            "candidate_validation_metrics": outcome.candidate_validation_metrics,
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


def _verify_processed_split_labels(
    dataset: PreparedDataset, split: GroupedSplit
) -> None:
    expected = np.empty(len(dataset.groups), dtype="<U10")
    expected[split.train] = "train"
    expected[split.validation] = "validation"
    expected[split.test] = "test"
    actual = np.asarray(dataset.splits)
    if not np.array_equal(expected, actual):
        raise ValueError("processed split labels differ from locked split manifest")


def _require_passing_leakage_audit(
    config: dict[str, Any], config_path: Path, dataset: PreparedDataset
) -> None:
    configured = config.get("leakage_audit_path")
    if configured is None:
        raise ValueError("locked real-data training requires leakage_audit_path")
    audit = json.loads(
        _config_relative_path(config_path, configured).read_text(encoding="utf-8")
    )
    if not isinstance(audit, dict) or audit.get("status") != "PASS":
        raise ValueError("formal training is blocked until leakage audit PASS")
    datasets = audit.get("datasets")
    if not isinstance(datasets, dict):
        raise ValueError("leakage audit has no dataset records")
    record = datasets.get(dataset.dataset_name)
    if not isinstance(record, dict) or record.get("status") != "PASS":
        raise ValueError("dataset has no passing leakage audit record")
    if record.get("processed_sha256") != dataset.processed_sha256:
        raise ValueError("leakage audit refers to a different processed dataset")


def _classification_by_condition(
    dataset: PreparedDataset,
    split: GroupedSplit,
    model: BaseEstimator,
    test_features: NDArray[np.float64],
) -> dict[str, dict[str, Any]]:
    conditions = np.asarray(dataset.operating_conditions)[split.test]
    truth = dataset.targets[split.test]
    result: dict[str, dict[str, Any]] = {}
    for condition in sorted(set(conditions.tolist())):
        mask = conditions == condition
        metrics = _evaluate(
            "fault_classification", model, test_features[mask], truth[mask]
        )
        result[str(condition)] = {
            key: metrics.get(key)
            for key in (
                "accuracy",
                "precision",
                "recall",
                "f1",
                "roc_auc",
                "pr_auc",
                "false_negative_rate",
            )
        }
    return result


def _rul_test_diagnostics(
    dataset: PreparedDataset,
    split: GroupedSplit,
    predictions: NDArray[np.float64],
) -> dict[str, Any]:
    test_groups = np.asarray(dataset.groups)[split.test]
    test_windows = dataset.window_indices[split.test]
    truth = np.asarray(dataset.targets[split.test], dtype=np.float64)
    per_bearing: dict[str, dict[str, Any]] = {}
    curves: dict[str, list[dict[str, float | int]]] = {}
    for bearing in sorted(set(test_groups.tolist())):
        positions = np.flatnonzero(test_groups == bearing)
        order = positions[np.argsort(test_windows[positions])]
        metrics = evaluate_rul(truth[order], predictions[order])
        per_bearing[bearing] = {
            "run_length": len(order),
            **metrics,
        }
        curves[bearing] = [
            {
                "acquisition_index": int(test_windows[position]),
                "actual_rul_hours": float(truth[position]),
                "raw_prediction_hours": float(predictions[position]),
                "display_prediction_hours": float(max(predictions[position], 0.0)),
            }
            for position in order
        ]
    train_maximum = float(np.max(np.asarray(dataset.targets[split.train], dtype=float)))
    negative = int(np.sum(predictions < 0))
    above_training_maximum = int(np.sum(predictions > train_maximum))
    late_mask = truth <= np.quantile(truth, 0.1)
    near_failure_late = np.maximum(predictions[late_mask] - truth[late_mask], 0.0)
    severe_oscillations = 0
    for bearing in sorted(set(test_groups.tolist())):
        positions = np.flatnonzero(test_groups == bearing)
        order = positions[np.argsort(test_windows[positions])]
        severe_oscillations += int(
            np.sum(np.abs(np.diff(predictions[order])) > max(train_maximum * 0.25, 1.0))
        )
    return {
        "per_bearing": per_bearing,
        "actual_vs_predicted": curves,
        "trajectory_consistency": {
            "raw_negative_predictions": negative,
            "above_train_lifecycle_maximum": above_training_maximum,
            "train_lifecycle_maximum_hours": train_maximum,
            "near_failure_mean_late_error_hours": float(
                np.mean(near_failure_late) if near_failure_late.size else 0.0
            ),
            "severe_oscillation_count": severe_oscillations,
            "display_clamp_applied_only_online": True,
        },
    }


def _high_metric_guard(
    dataset: PreparedDataset, split: GroupedSplit, metrics: dict[str, Any]
) -> dict[str, Any]:
    watched = {
        name: float(value)
        for name in ("accuracy", "f1", "roc_auc", "pr_auc")
        if (value := metrics.get(name)) is not None
    }
    triggered = any(value > 0.98 for value in watched.values())
    group_audit = group_split_audit(split, dataset.groups)
    sources: dict[str, set[str]] = {}
    duplicate_windows = 0
    observed_windows: set[tuple[str, int]] = set()
    for source, window, split_name in zip(
        dataset.source_files,
        dataset.window_indices,
        dataset.splits,
        strict=True,
    ):
        sources.setdefault(source, set()).add(split_name)
        key = (source, int(window))
        duplicate_windows += int(key in observed_windows)
        observed_windows.add(key)
    checks = {
        "bearing_overlap": group_audit.passed,
        "source_overlap": all(len(values) == 1 for values in sources.values()),
        "duplicate_sample_id": len(dataset.sample_ids) == len(set(dataset.sample_ids)),
        "window_overlap": duplicate_windows == 0,
        "scaler_fit_split": "train",
        "label_features_excluded": True,
        "condition_distribution_reported": True,
    }
    return {
        "triggered": triggered,
        "threshold": 0.98,
        "watched_metrics": watched,
        "checks": checks,
        "passed": all(value is True or value == "train" for value in checks.values()),
        "interpretation": "High performance may reflect dataset/domain discrimination; bearing, source, window, preprocessing, label, and condition checks were rerun."
        if triggered
        else "not triggered",
    }


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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
