"""Predictive V2 feature and governance tests use only synthetic fixtures."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest

from app.ml.features import FEATURE_SCHEMA_VERSION
from app.ml.v2_features import (
    FEATURE_SCHEMA_VERSION_V2,
    ConditionBaseline,
    FoldLocalDegradationIndicator,
    causal_multiscale_context,
    extract_dual_channel_features,
    extract_envelope_features,
)
from app.ml.v2_governance import (
    ExperimentRun,
    PaderbornAccessPolicy,
    causal_ewma,
    fault_promotion,
    hierarchical_fault_targets,
    rul_promotion,
    trajectory_metrics,
)
from app.ml.v2_research import grouped_condition_folds

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPOSITORY_ROOT / "scripts"))

from prepare_bearing_v2 import prepare_xjtu_bearing  # noqa: E402
from run_fault_v2 import _candidates as fault_candidates  # noqa: E402
from run_rul_v2 import _candidates as rul_candidates  # noqa: E402


def test_v1_and_v2_feature_schema_are_isolated() -> None:
    assert FEATURE_SCHEMA_VERSION == "bearing-features-v1"
    assert FEATURE_SCHEMA_VERSION_V2 == "bearing-features-v2"
    assert FEATURE_SCHEMA_VERSION != FEATURE_SCHEMA_VERSION_V2


def test_envelope_features_are_finite_and_respond_to_impulses() -> None:
    normal = np.sin(np.linspace(0, 16 * np.pi, 1024))
    impulsive = normal.copy()
    impulsive[::64] += 5.0

    normal_features = extract_envelope_features(normal, 25_600)
    impulsive_features = extract_envelope_features(impulsive, 25_600)

    assert set(normal_features) == set(impulsive_features)
    assert all(np.isfinite(list(impulsive_features.values())))
    assert impulsive_features["envelope_peak"] > normal_features["envelope_peak"]


def test_dual_channel_features_include_real_cross_channel_statistics() -> None:
    horizontal = np.sin(np.linspace(0, 20 * np.pi, 512))
    vertical = horizontal * 2.0

    features = extract_dual_channel_features(horizontal, vertical, 25_600)

    assert features["cross_channel_correlation"] == pytest.approx(1.0)
    assert features["cross_rms_ratio_first_over_second"] == pytest.approx(0.5)
    assert "horizontal_envelope_kurtosis" in features
    assert "vertical_spectral_entropy" in features

    current = extract_dual_channel_features(
        horizontal,
        vertical,
        25_600,
        first_name="phase_current_1",
        second_name="phase_current_2",
        cross_prefix="current_cross",
    )
    assert "phase_current_1_rms" in current
    assert current["current_cross_channel_correlation"] == pytest.approx(1.0)


def test_condition_baseline_uses_only_rows_passed_to_fit() -> None:
    train = [
        {"rms": 1.0, "kurtosis": 3.0},
        {"rms": 2.0, "kurtosis": 4.0},
        {"rms": 20.0, "kurtosis": 10.0},
    ]
    baseline = ConditionBaseline.fit(
        train,
        ["A", "A", "A"],
        [False, False, True],
        feature_names=("rms", "kurtosis"),
    )

    before = baseline.transform([{"rms": 3.0, "kurtosis": 5.0}], ["A"])
    validation_outlier = {"rms": 1_000_000.0, "kurtosis": 1_000_000.0}
    after = baseline.transform([validation_outlier], ["A"])

    assert before[0]["condition_normalized_rms"] == pytest.approx(3.0)
    assert after[0]["condition_normalized_rms"] > 1_000_000
    assert baseline.pooled["rms"] == pytest.approx((1.5, 0.5))


def test_causal_multiscale_context_cannot_see_future_values() -> None:
    prefix = [{"horizontal_rms": float(index)} for index in range(20)]
    original = causal_multiscale_context(prefix)
    extended = causal_multiscale_context([*prefix, {"horizontal_rms": 1_000_000.0}])

    assert original == extended[:-1]
    assert original[5]["horizontal_rms_causal_5m_mean"] == pytest.approx(2.5)
    assert all("center" not in key for row in original for key in row)


def test_fold_local_degradation_fit_does_not_use_validation() -> None:
    train = [
        {"horizontal_rms": float(index + 1), "vertical_rms": float(index + 2)}
        for index in range(10)
    ]
    indicator = FoldLocalDegradationIndicator.fit(train, ["A"] * 10, list(range(10)))
    validation = [{"horizontal_rms": 100.0, "vertical_rms": 200.0}]

    distance = indicator.transform(validation)

    assert distance.shape == (1,)
    assert distance[0] > 10
    assert indicator.median[0] == pytest.approx(3.0)


def test_frozen_test_policy_denies_access(tmp_path: Path) -> None:
    manifest = tmp_path / "folds.json"
    manifest.write_text(
        json.dumps(
            {
                "locked": True,
                "frozen_test_accessed": False,
                "development_bearings": ["D1", "D2"],
                "frozen_test_bearings": ["T1"],
            }
        ),
        encoding="utf-8",
    )
    policy = PaderbornAccessPolicy.from_manifest(manifest)

    policy.require_development("D1")
    with pytest.raises(PermissionError, match="frozen Paderborn test access denied"):
        policy.require_development("T1")
    with pytest.raises(ValueError, match="incomplete"):
        policy.validate_development_groups(["D1"])


def test_hierarchical_classifier_eligibility_uses_official_subtype_counts() -> None:
    stage_one, eligible = hierarchical_fault_targets(
        ["healthy", "outer_ring", "inner_ring"],
        ["none", "outer", "inner"],
    )

    np.testing.assert_array_equal(stage_one, [0, 1, 1])
    assert eligible is False


def test_rul_trajectory_reports_raw_and_causal_smoothed_oscillation() -> None:
    raw = np.asarray([10.0, 9.0, 10.0, 8.0, 8.2])
    smoothed = causal_ewma(raw)
    raw_metrics = trajectory_metrics({"B1": raw})
    smoothed_metrics = trajectory_metrics({"B1": smoothed})

    assert raw_metrics["oscillation_count"] == 1
    assert raw_metrics["max_positive_jump"] == pytest.approx(1.0)
    assert smoothed[0] == raw[0]
    assert smoothed_metrics["oscillation_count"] <= raw_metrics["oscillation_count"]


def test_v2_promotion_policies_do_not_lower_safety_thresholds() -> None:
    assert fault_promotion({"macro_recall": 0.70, "healthy_recall": 0.60})["passed"]
    assert not fault_promotion({"macro_recall": 0.699, "healthy_recall": 1.0})["passed"]
    passing_rul = {
        "mae": 5.0,
        "r2": 0.01,
        "late_prediction_error": 3.0,
        "mean_per_bearing_oscillation_rate": 0.10,
    }
    assert rul_promotion(passing_rul)["passed"]
    assert not rul_promotion({**passing_rul, "r2": 0.0})["passed"]


def test_experiment_run_requires_completion_and_records_artifact_hash(
    tmp_path: Path,
) -> None:
    run = ExperimentRun(
        experiment_id="fixture",
        dataset_version="dataset-v1",
        feature_version=FEATURE_SCHEMA_VERSION_V2,
        fold_manifest="folds.json",
        algorithm="ridge",
        hyperparameters={"alpha": 1.0},
        seed=20260803,
        git_sha="a" * 40,
    )
    output = tmp_path / "run.json"
    with pytest.raises(ValueError, match="unfinished"):
        run.write(output)
    artifact = tmp_path / "artifact.bin"
    artifact.write_bytes(b"fixture")

    run.finish({"mae": 1.0}, artifact_path=artifact)
    run.write(output)

    recorded = json.loads(output.read_text(encoding="utf-8"))
    assert recorded["metrics"] == {"mae": 1.0}
    assert len(recorded["artifact_hash"]) == 64


def test_xjtu_v2_preparation_uses_both_channels_and_causal_history(
    tmp_path: Path,
) -> None:
    bearing_dir = tmp_path / "35Hz12kN" / "Bearing1_1"
    bearing_dir.mkdir(parents=True)
    for index in range(1, 8):
        horizontal = np.sin(np.linspace(0, 8 * np.pi, 128)) * index
        vertical = np.cos(np.linspace(0, 8 * np.pi, 128)) * (index + 1)
        matrix = np.column_stack([horizontal, vertical])
        np.savetxt(bearing_dir / f"{index}.csv", matrix, delimiter=",")

    rows = prepare_xjtu_bearing(tmp_path, bearing_dir)

    assert len(rows) == 7
    assert rows[0].target == pytest.approx(0.1)
    assert rows[-1].target == 0.0
    assert "horizontal_rms" in rows[0].values
    assert "vertical_rms" in rows[0].values
    assert "cross_channel_correlation" in rows[0].values
    assert "horizontal_rms_causal_5m_mean" in rows[0].values
    assert (
        rows[0].values["horizontal_rms_causal_5m_mean"]
        == rows[0].values["horizontal_rms"]
    )


def test_grouped_condition_folds_are_deterministic_and_group_safe() -> None:
    groups = np.asarray([f"B{index}" for index in range(9) for _ in range(2)])
    conditions = np.asarray([f"C{index // 3}" for index in range(9) for _ in range(2)])

    first = grouped_condition_folds(groups, conditions)
    second = grouped_condition_folds(groups, conditions)

    for (train, validation), duplicate in zip(first, second, strict=True):
        np.testing.assert_array_equal(train, duplicate[0])
        np.testing.assert_array_equal(validation, duplicate[1])
        assert not set(groups[train]) & set(groups[validation])
        assert set(conditions[validation]) == {"C0", "C1", "C2"}


def test_v2_candidate_grids_match_preregistration() -> None:
    fault = fault_candidates()
    rul = rul_candidates()

    assert len(fault) == 24
    assert {candidate.algorithm for candidate in fault} == {
        "logistic_regression",
        "random_forest",
        "hist_gradient_boosting",
    }
    assert len(rul) == 23
    assert {candidate.algorithm for candidate in rul} == {
        "ridge",
        "random_forest",
        "extra_trees",
        "gradient_boosting",
        "hist_gradient_boosting",
    }
