"""Register a verified local artifact bundle in the lightweight registry."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from app.db.session import SessionLocal
from app.ml.artifacts import load_artifact_bundle
from app.ml.features import feature_definitions
from app.models.ml import (
    DatasetVersion,
    MLFeatureDefinition,
    ModelMetric,
    ModelVersion,
    TrainingRun,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument(
        "--status", choices=["registered", "candidate"], default="candidate"
    )
    args = parser.parse_args()
    artifact_dir = cast(Path, args.artifact)
    manifest_path = cast(Path, args.manifest)
    integrity = _read_json(artifact_dir / "integrity.json")
    metadata = _read_json(artifact_dir / "metadata.json")
    bundle = load_artifact_bundle(
        artifact_dir,
        expected_sha256=str(integrity["sha256"]),
        expected_model_version=str(metadata["model_version"]),
        expected_feature_schema_version=str(metadata["feature_schema_version"]),
    )
    manifest = _read_json(manifest_path)
    counts = cast(dict[str, Any], metadata["sample_counts"])
    with SessionLocal() as db:
        dataset = (
            db.query(DatasetVersion)
            .filter(DatasetVersion.manifest_sha256 == _sha256(manifest_path))
            .first()
        )
        if dataset is None:
            dataset = DatasetVersion(
                name=str(manifest["dataset_name"]),
                version=str(manifest["version"]),
                source_url=str(manifest["source_url"]),
                license_name=str(manifest["license"]),
                citation=str(manifest["citation"]),
                manifest_path=str(manifest_path),
                manifest_sha256=_sha256(manifest_path),
                raw_sha256=_optional_string(manifest.get("sha256")),
                raw_file_count=int(manifest["raw_files"]),
                processed_version=str(manifest["processed_version"]),
                processed_sha256=str(metadata["processed_sha256"]),
                feature_schema_version=str(manifest["feature_schema_version"]),
                downloaded_at=_optional_datetime(manifest.get("downloaded_at")),
            )
            db.add(dataset)
            db.flush()
        _register_feature_definitions(
            db,
            str(metadata["feature_schema_version"]),
            bundle.feature_names,
        )
        run = TrainingRun(
            run_name=f"{metadata['run_name']}-{metadata['model_version']}",
            task_type=str(metadata["task_type"]),
            dataset_version_id=dataset.id,
            feature_schema_version=str(metadata["feature_schema_version"]),
            config_path=str(metadata["config_path"]),
            config_sha256=str(metadata["config_sha256"]),
            git_commit_sha=str(metadata["git_commit_sha"]),
            seed=int(metadata["seed"]),
            train_samples=int(counts["train"]),
            validation_samples=int(counts["validation"]),
            test_samples=int(counts["test"]),
            group_count=int(counts["groups"]),
            status="completed",
            started_at=datetime.fromisoformat(str(metadata["training_started_at"])),
            finished_at=datetime.fromisoformat(str(metadata["training_finished_at"])),
        )
        db.add(run)
        db.flush()
        model = ModelVersion(
            name=str(metadata["run_name"]),
            task_type=str(metadata["task_type"]),
            algorithm=str(metadata["algorithm"]),
            version=str(metadata["model_version"]),
            dataset_version_id=dataset.id,
            training_run_id=run.id,
            feature_schema_version=str(metadata["feature_schema_version"]),
            git_commit_sha=str(metadata["git_commit_sha"]),
            training_started_at=run.started_at,
            training_finished_at=cast(datetime, run.finished_at),
            artifact_path=str(artifact_dir.resolve()),
            artifact_sha256=str(integrity["sha256"]),
            hyperparameters=cast(dict[str, Any], metadata["hyperparameters"]),
            metrics=bundle.metrics,
            status=str(args.status),
            is_production=False,
        )
        db.add(model)
        db.flush()
        for split, values in bundle.metrics.items():
            if not isinstance(values, dict):
                continue
            for name, value in values.items():
                scalar = float(value) if isinstance(value, (int, float)) else None
                structured = None if scalar is not None else value
                db.add(
                    ModelMetric(
                        model_version_id=model.id,
                        split=str(split),
                        metric_name=str(name),
                        metric_value=scalar,
                        structured_value=structured,
                    )
                )
        db.commit()
        print(
            json.dumps(
                {"model_id": model.id, "version": model.version, "status": model.status}
            )
        )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return cast(dict[str, Any], value)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _optional_string(value: Any) -> str | None:
    return None if value is None else str(value)


def _optional_datetime(value: Any) -> datetime | None:
    return None if value is None else datetime.fromisoformat(str(value))


def _register_feature_definitions(
    db: Any, schema_version: str, feature_names: tuple[str, ...]
) -> None:
    known = {
        item.name: item
        for item in feature_definitions(
            [
                name.removeprefix("context_")
                for name in feature_names
                if name.startswith("context_")
            ]
        )
    }
    existing = {
        name
        for (name,) in db.query(MLFeatureDefinition.name)
        .filter(MLFeatureDefinition.schema_version == schema_version)
        .all()
    }
    for name in feature_names:
        if name in existing:
            continue
        definition = known.get(name)
        db.add(
            MLFeatureDefinition(
                schema_version=schema_version,
                name=name,
                source=definition.source if definition else "context",
                unit=definition.unit if definition else "dataset",
                description=definition.description
                if definition
                else name.replace("_", " "),
            )
        )


if __name__ == "__main__":
    main()
