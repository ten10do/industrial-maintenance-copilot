"""Versioned joblib artifact bundles with integrity and schema checks."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import joblib


@dataclass(frozen=True)
class LoadedArtifact:
    model: Any
    preprocessor: Any
    feature_names: tuple[str, ...]
    metadata: dict[str, Any]
    metrics: dict[str, Any]


def save_artifact_bundle(
    output_dir: Path,
    *,
    model: Any,
    preprocessor: Any,
    feature_names: list[str],
    feature_schema_version: str,
    model_version: str,
    metadata: dict[str, Any],
    metrics: dict[str, Any],
) -> str:
    output_dir.mkdir(parents=True, exist_ok=False)
    joblib.dump(model, output_dir / "model.joblib")
    joblib.dump(preprocessor, output_dir / "preprocessor.joblib")
    _write_json(
        output_dir / "feature_schema.json",
        {"version": feature_schema_version, "features": feature_names},
    )
    complete_metadata = {
        **metadata,
        "model_version": model_version,
        "feature_schema_version": feature_schema_version,
    }
    _write_json(output_dir / "metadata.json", complete_metadata)
    _write_json(output_dir / "metrics.json", metrics)
    digest = bundle_sha256(output_dir)
    _write_json(output_dir / "integrity.json", {"sha256": digest})
    return digest


def load_artifact_bundle(
    artifact_dir: Path,
    *,
    expected_sha256: str,
    expected_model_version: str,
    expected_feature_schema_version: str,
) -> LoadedArtifact:
    required = (
        "model.joblib",
        "preprocessor.joblib",
        "feature_schema.json",
        "metadata.json",
        "metrics.json",
        "integrity.json",
    )
    missing = [name for name in required if not (artifact_dir / name).is_file()]
    if missing:
        raise FileNotFoundError(f"artifact bundle missing: {', '.join(missing)}")
    actual_hash = bundle_sha256(artifact_dir)
    stored_hash = _read_json(artifact_dir / "integrity.json").get("sha256")
    if actual_hash != expected_sha256 or actual_hash != stored_hash:
        raise ValueError("artifact SHA256 does not match registry metadata")
    metadata = _read_json(artifact_dir / "metadata.json")
    schema = _read_json(artifact_dir / "feature_schema.json")
    if metadata.get("model_version") != expected_model_version:
        raise ValueError("artifact model version mismatch")
    if (
        schema.get("version") != expected_feature_schema_version
        or metadata.get("feature_schema_version") != expected_feature_schema_version
    ):
        raise ValueError("artifact feature schema version mismatch")
    return LoadedArtifact(
        model=joblib.load(artifact_dir / "model.joblib"),
        preprocessor=joblib.load(artifact_dir / "preprocessor.joblib"),
        feature_names=tuple(str(name) for name in schema["features"]),
        metadata=metadata,
        metrics=_read_json(artifact_dir / "metrics.json"),
    )


def bundle_sha256(artifact_dir: Path) -> str:
    digest = hashlib.sha256()
    for name in (
        "model.joblib",
        "preprocessor.joblib",
        "feature_schema.json",
        "metadata.json",
        "metrics.json",
    ):
        path = artifact_dir / name
        if not path.is_file():
            raise FileNotFoundError(path)
        digest.update(name.encode())
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object in {path.name}")
    return value
