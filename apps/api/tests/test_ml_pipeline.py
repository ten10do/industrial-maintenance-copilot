"""Synthetic-only tests for the ML pipeline; no external dataset samples are used."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.ml.artifacts import load_artifact_bundle, save_artifact_bundle
from app.ml.features import (
    FEATURE_SCHEMA_VERSION,
    extract_features,
    feature_definitions,
)
from app.ml.inference import predict
from app.ml.selection import CandidateMetrics, select_failure_model, select_rul_model
from app.ml.splitting import (
    grouped_split_from_manifest,
    grouped_train_validation_test_split,
)
from app.ml.training import train_from_config
from app.ml.types import TelemetryWindow
from app.ml.validation import SignalValidationError, split_windows, validated_signal


def synthetic_window(*, missing: bool = False) -> TelemetryWindow:
    values = np.sin(np.linspace(0, 20 * np.pi, 256))
    if missing:
        values[10] = np.nan
    started = datetime(2026, 1, 1, tzinfo=UTC)
    return TelemetryWindow(
        equipment_id="synthetic-equipment",
        bearing_id="synthetic-bearing",
        signal=tuple(values.tolist()),
        sampling_rate_hz=256,
        started_at=started,
        ended_at=started + timedelta(seconds=1),
        unit="m/s2",
        context={"speed_rpm": 1500.0},
    )


def test_shared_features_are_finite_reproducible_and_complete():
    first = extract_features(synthetic_window())
    second = extract_features(synthetic_window())
    assert first == second
    expected = {
        "mean",
        "std",
        "variance",
        "rms",
        "max",
        "min",
        "peak_to_peak",
        "absolute_mean",
        "skewness",
        "kurtosis",
        "crest_factor",
        "shape_factor",
        "impulse_factor",
        "clearance_factor",
        "dominant_frequency_hz",
        "spectral_centroid_hz",
        "spectral_rms_hz",
        "spectral_entropy",
        "rms_slope",
        "kurtosis_slope",
        "envelope_energy_slope",
        "degradation_rate",
        "recent_vs_baseline_delta",
        "context_speed_rpm",
    }
    assert expected <= first.values.keys()
    assert all(np.isfinite(value) for value in first.values.values())
    assert {item.source for item in feature_definitions(["speed_rpm"])} == {
        "time",
        "frequency",
        "trend",
        "context",
    }
    assert not any(
        name.startswith(("bpfo", "bpfi", "bsf", "ftf")) for name in first.values
    )


def test_validation_interpolates_small_gap_and_rejects_inf_and_duplicates():
    _, signal, quality = validated_signal(synthetic_window(missing=True))
    assert np.isfinite(signal).all()
    assert quality < 1.0
    invalid = synthetic_window()
    invalid = TelemetryWindow(
        **{**invalid.__dict__, "signal": (float("inf"), *invalid.signal[1:])}
    )
    with pytest.raises(SignalValidationError, match="infinite"):
        validated_signal(invalid)
    duplicate_times = TelemetryWindow(
        **{**synthetic_window().__dict__, "sample_timestamps": tuple([0.0] * 256)}
    )
    with pytest.raises(SignalValidationError, match="unique"):
        validated_signal(duplicate_times)


def test_windowing_is_deterministic():
    windows = split_windows(synthetic_window(), window_size=64, stride=32)
    assert len(windows) == 7
    assert all(len(window.signal) == 64 for window in windows)
    assert windows[0].started_at < windows[-1].started_at


def test_group_split_never_leaks_bearings():
    groups = [f"bearing-{index // 5}" for index in range(30)]
    split = grouped_train_validation_test_split(
        groups, test_size=0.2, validation_size=0.2, seed=7
    )
    group_array = np.asarray(groups)
    train = set(group_array[split.train])
    validation = set(group_array[split.validation])
    test = set(group_array[split.test])
    assert not train & validation
    assert not train & test
    assert not validation & test


def test_locked_group_manifest_is_materialized_without_overlap(tmp_path: Path):
    groups = ["bearing-a", "bearing-a", "bearing-b", "bearing-c"]
    manifest = tmp_path / "split.json"
    manifest.write_text(
        json.dumps(
            {
                "train": ["bearing-a"],
                "validation": ["bearing-b"],
                "test": ["bearing-c"],
            }
        ),
        encoding="utf-8",
    )

    split = grouped_split_from_manifest(groups, manifest)

    assert split.train.tolist() == [0, 1]
    assert split.validation.tolist() == [2]
    assert split.test.tolist() == [3]


def test_safety_selection_policies_enforce_recall_and_late_error():
    chosen = select_failure_model(
        [
            CandidateMetrics(
                "unsafe",
                {"pr_auc": 0.99, "recall": 0.5, "f1": 0.8, "false_negative_rate": 0.5},
            ),
            CandidateMetrics(
                "safe",
                {"pr_auc": 0.85, "recall": 0.9, "f1": 0.82, "false_negative_rate": 0.1},
            ),
        ],
        minimum_recall=0.8,
    )
    assert chosen.name == "safe"
    rul = select_rul_model(
        [
            CandidateMetrics(
                "late", {"mae": 1.0, "rmse": 1.2, "late_prediction_error": 8.0}
            ),
            CandidateMetrics(
                "safe", {"mae": 1.5, "rmse": 1.7, "late_prediction_error": 1.0}
            ),
        ],
        maximum_late_error=3.0,
    )
    assert rul.name == "safe"


def test_artifact_integrity_and_deterministic_inference(tmp_path: Path):
    vector = extract_features(synthetic_window())
    names = sorted(vector.values)
    row = np.asarray([[vector.values[name] for name in names]], dtype=np.float64)
    features = np.vstack([row * 0.5, row * 0.8, row * 1.2, row * 1.5])
    targets = np.asarray([0, 0, 1, 1])
    scaler = StandardScaler().fit(features)
    model = LogisticRegression(random_state=1).fit(scaler.transform(features), targets)
    artifact_dir = tmp_path / "model-v1"
    digest = save_artifact_bundle(
        artifact_dir,
        model=model,
        preprocessor=scaler,
        feature_names=names,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        model_version="model-v1",
        metadata={"task_type": "failure_risk", "prediction_horizon": "next 3 samples"},
        metrics={"test": {"relative_error": 0.1}},
    )
    loaded = load_artifact_bundle(
        artifact_dir,
        expected_sha256=digest,
        expected_model_version="model-v1",
        expected_feature_schema_version=FEATURE_SCHEMA_VERSION,
    )
    result = predict(loaded, vector)
    assert result.model_version == "model-v1"
    assert result.probability is not None
    assert result.top_features
    (artifact_dir / "metadata.json").write_text("{}", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA256"):
        load_artifact_bundle(
            artifact_dir,
            expected_sha256=digest,
            expected_model_version="model-v1",
            expected_feature_schema_version=FEATURE_SCHEMA_VERSION,
        )


def test_tiny_synthetic_training_runs_without_test_set_selection(tmp_path: Path):
    rng = np.random.default_rng(42)
    features: list[list[float]] = []
    targets: list[str] = []
    groups: list[str] = []
    for group_index in range(8):
        for row_index in range(12):
            target = row_index % 2
            features.append((rng.normal(size=5) + target * 1.5).tolist())
            targets.append(str(target))
            groups.append(f"synthetic-bearing-{group_index}")
    processed = tmp_path / "synthetic.npz"
    np.savez_compressed(
        processed,
        features=np.asarray(features),
        targets=np.asarray(targets),
        groups=np.asarray(groups),
        sample_ids=np.asarray(
            [f"synthetic-sample-{index}" for index in range(len(groups))]
        ),
        source_files=np.asarray(
            [f"synthetic/source-{index}.csv" for index in range(len(groups))]
        ),
        window_indices=np.asarray(
            [index % 12 for index in range(len(groups))], dtype=np.int64
        ),
        splits=np.asarray(["unassigned"] * len(groups)),
        feature_versions=np.asarray([FEATURE_SCHEMA_VERSION] * len(groups)),
        operating_conditions=np.asarray(["synthetic"] * len(groups)),
        rul_measurements=np.asarray([-1] * len(groups), dtype=np.int64),
        rul_hours=np.asarray([np.nan] * len(groups), dtype=np.float64),
        feature_names=np.asarray([f"f{index}" for index in range(5)]),
        dataset_name=np.asarray("xjtu-sy"),
        dataset_version=np.asarray("synthetic-ci-only"),
        feature_schema_version=np.asarray(FEATURE_SCHEMA_VERSION),
    )
    config = tmp_path / "config.yaml"
    config.write_text(
        f"""dataset: xjtu-sy
task_type: failure_risk
processed_path: {processed.as_posix()}
output_dir: {(tmp_path / "artifacts").as_posix()}
seed: 42
split:
  test_size: 0.25
  validation_size: 0.25
models:
  - algorithm: logistic_regression
    hyperparameters: {{}}
  - algorithm: random_forest
    hyperparameters:
      n_estimators: 10
minimum_recall: 0.1
prediction_horizon: synthetic test horizon
""",
        encoding="utf-8",
    )
    outcome = train_from_config(
        dataset_name="xjtu-sy", config_path=config, expected_task="failure_risk"
    )
    metadata = json.loads((outcome.artifact_path / "metadata.json").read_text())
    group_sets = [set(items) for items in metadata["split_groups"].values()]
    assert not group_sets[0] & group_sets[1]
    assert not group_sets[0] & group_sets[2]
    assert metadata["leakage_audit"]["passed"] is True
    assert metadata["leakage_audit"]["train_validation_intersection"] == []
    assert metadata["leakage_audit"]["train_test_intersection"] == []
    assert metadata["leakage_audit"]["validation_test_intersection"] == []
    assert metadata["fit_provenance"] == {
        "feature_selector": "not_configured",
        "model_fit_split": "train",
        "model_selection_split": "validation",
        "preprocessor_fit_samples": len(outcome.split.train),
        "preprocessor_fit_split": "train",
        "test_set_usage": "final_selected_model_evaluation_only",
    }
    assert "test" in json.loads((outcome.artifact_path / "metrics.json").read_text())
