"""Model registry and online inference invariants."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from app.ml.artifacts import save_artifact_bundle
from app.ml.features import FEATURE_SCHEMA_VERSION, extract_features
from app.ml.registry import promote_model, rollback_model
from app.ml.types import TelemetryWindow
from app.models.intelligence import RiskPrediction
from app.models.ml import DatasetVersion, ModelVersion, PredictionRecord, TrainingRun


def _registered_model(
    db, name: str, task: str, dataset_id: int, run_id: int
) -> ModelVersion:
    now = datetime.now(UTC)
    model = ModelVersion(
        name=name,
        task_type=task,
        algorithm="logistic_regression",
        version=name,
        dataset_version_id=dataset_id,
        training_run_id=run_id,
        feature_schema_version="bearing-features-v1",
        git_commit_sha="a" * 40,
        training_started_at=now,
        training_finished_at=now,
        artifact_path="artifacts/test",
        artifact_sha256="b" * 64,
        hyperparameters={},
        metrics={"promotion": {"eligible": True}},
        status="candidate",
        is_production=False,
    )
    db.add(model)
    db.commit()
    db.refresh(model)
    return model


def test_promote_and_rollback_keep_one_production_model_per_task(db):
    now = datetime.now(UTC)
    dataset = DatasetVersion(
        name="synthetic",
        version="ci-only",
        source_url="local",
        license_name="generated",
        citation="synthetic test fixture",
        manifest_path="tests",
        manifest_sha256="c" * 64,
        processed_version="v1",
        feature_schema_version="bearing-features-v1",
    )
    db.add(dataset)
    db.commit()
    run = TrainingRun(
        run_name="synthetic-run",
        task_type="failure_risk",
        dataset_version_id=dataset.id,
        feature_schema_version="bearing-features-v1",
        config_path="tests",
        config_sha256="d" * 64,
        git_commit_sha="a" * 40,
        seed=1,
        train_samples=10,
        validation_samples=4,
        test_samples=4,
        group_count=4,
        status="completed",
        started_at=now,
        finished_at=now,
    )
    db.add(run)
    db.commit()
    first = _registered_model(db, "model-1", "failure_risk", dataset.id, run.id)
    second = _registered_model(db, "model-2", "failure_risk", dataset.id, run.id)
    first.metrics = {"promotion": {"eligible": False}}
    db.commit()
    with pytest.raises(ValueError, match="promotion decision"):
        promote_model(db, first.id, "production")
    with pytest.raises(ValueError, match="promotion decision"):
        promote_model(db, first.id, "staging")
    first.metrics = {"promotion": {"passed": True}}
    db.commit()
    promote_model(db, first.id, "staging")
    assert first.status == "staging"
    assert not first.is_production
    first.metrics = {"promotion": {"eligible": True}}
    db.commit()
    promote_model(db, first.id, "production")
    promote_model(db, second.id, "production")
    db.refresh(first)
    assert not first.is_production
    assert first.status == "archived"
    assert second.is_production
    rollback_model(db, "failure_risk", first.id)
    db.refresh(first)
    db.refresh(second)
    assert first.is_production
    assert not second.is_production


def test_online_inference_uses_verified_production_model_and_records_lineage(
    tmp_path: Path, db, equipment, auth_supervisor, client
):
    now = datetime.now(UTC)
    signal = np.sin(np.linspace(0, 20 * np.pi, 256))
    vector = extract_features(
        TelemetryWindow(
            equipment_id=str(equipment.id),
            bearing_id="synthetic-bearing",
            signal=tuple(signal.tolist()),
            sampling_rate_hz=256,
            started_at=now,
            ended_at=now + timedelta(seconds=1),
            context={"speed_rpm": 1500.0},
        )
    )
    names = sorted(vector.values)
    row = np.asarray([[vector.values[name] for name in names]])
    matrix = np.vstack([row * 0.5, row * 0.8, row * 1.2, row * 1.5])
    targets = np.asarray([0, 0, 1, 1])
    scaler = StandardScaler().fit(matrix)
    classifier = LogisticRegression(random_state=1).fit(
        scaler.transform(matrix), targets
    )
    artifact_dir = tmp_path / "online-model-v1"
    digest = save_artifact_bundle(
        artifact_dir,
        model=classifier,
        preprocessor=scaler,
        feature_names=names,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        model_version="online-model-v1",
        metadata={
            "task_type": "failure_risk",
            "prediction_horizon": "next 3 samples",
        },
        metrics={"test": {}},
    )
    dataset = DatasetVersion(
        name="synthetic",
        version="ci-only",
        source_url="local",
        license_name="generated",
        citation="synthetic test fixture",
        manifest_path="tests",
        manifest_sha256="e" * 64,
        processed_version="v1",
        feature_schema_version=FEATURE_SCHEMA_VERSION,
    )
    db.add(dataset)
    db.flush()
    run = TrainingRun(
        run_name="online-synthetic-run",
        task_type="failure_risk",
        dataset_version_id=dataset.id,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        config_path="tests",
        config_sha256="f" * 64,
        git_commit_sha="a" * 40,
        seed=1,
        train_samples=4,
        validation_samples=2,
        test_samples=2,
        group_count=4,
        status="completed",
        started_at=now,
        finished_at=now,
    )
    db.add(run)
    db.flush()
    model = ModelVersion(
        name="online model",
        task_type="failure_risk",
        algorithm="logistic_regression",
        version="online-model-v1",
        dataset_version_id=dataset.id,
        training_run_id=run.id,
        feature_schema_version=FEATURE_SCHEMA_VERSION,
        git_commit_sha="a" * 40,
        training_started_at=now,
        training_finished_at=now,
        artifact_path=str(artifact_dir),
        artifact_sha256=digest,
        hyperparameters={},
        metrics={"promotion": {"eligible": True}},
        status="production",
        is_production=True,
    )
    db.add(model)
    db.commit()

    response = client.post(
        "/api/v1/ml/inference",
        headers=auth_supervisor,
        json={
            "equipment_id": equipment.id,
            "bearing_id": "synthetic-bearing",
            "task_type": "failure_risk",
            "signal": signal.tolist(),
            "sampling_rate_hz": 256,
            "started_at": now.isoformat(),
            "ended_at": (now + timedelta(seconds=1)).isoformat(),
            "context": {"speed_rpm": 1500.0},
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["model_version"] == "online-model-v1"
    assert body["probability"] == body["probabilities"]["1"]
    assert body["top_contributing_features"]
    risk = db.query(RiskPrediction).one()
    assert risk.model_version == "online-model-v1"
    assert risk.is_mock is False

    model.status = "staging"
    model.is_production = False
    db.commit()
    staging_payload = {
        "equipment_id": equipment.id,
        "bearing_id": "synthetic-bearing",
        "task_type": "failure_risk",
        "model_version_id": model.id,
        "signal": signal.tolist(),
        "sampling_rate_hz": 256,
        "started_at": now.isoformat(),
        "ended_at": (now + timedelta(seconds=1)).isoformat(),
        "context": {"speed_rpm": 1500.0},
    }
    staging_response = client.post(
        "/api/v1/ml/inference", headers=auth_supervisor, json=staging_payload
    )
    assert staging_response.status_code == 200, staging_response.text
    assert db.query(PredictionRecord).count() == 2
    assert db.query(RiskPrediction).count() == 1
