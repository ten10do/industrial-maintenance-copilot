"""Run the single governed Paderborn V2 frozen-test evaluation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

import numpy as np
import yaml
from sklearn.metrics import brier_score_loss

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from prepare_bearing_v2 import V2Row, prepare_paderborn_bearing
from run_fault_v2 import Candidate, _binary_metrics, _classifier

from app.ml.artifacts import save_artifact_bundle
from app.ml.v2_governance import PaderbornAccessPolicy
from app.ml.v2_research import (
    FaultFamily,
    PaderbornFaultV2Preprocessor,
    V2Dataset,
)

SEED = 20260803


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--development-summary", type=Path, required=True)
    parser.add_argument("--development-processed", type=Path, required=True)
    parser.add_argument("--fold-manifest", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--access-ledger", type=Path, required=True)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError("final-test output already exists; replay is forbidden")
    if args.access_ledger.exists():
        raise FileExistsError("frozen-test access ledger already exists; replay denied")

    config = _read_yaml(args.config)
    summary = _read_json(args.development_summary)
    policy = PaderbornAccessPolicy.from_manifest(args.fold_manifest)
    config_sha = _sha256(args.config)
    summary_sha = _sha256(args.development_summary)
    config_commit = _validate_committed_config(
        args.config, config, summary, summary_sha, policy
    )
    selected = summary["selected"]
    started_at = datetime.now(UTC).isoformat()
    development = V2Dataset.load(
        args.development_processed, expected_dataset="paderborn"
    )
    policy.validate_development_groups(development.groups.tolist())
    dataset_manifest = _read_json(args.dataset_manifest)
    if (
        config.get("dataset_version") != development.dataset_version
        or dataset_manifest.get("version") != development.dataset_version
        or config.get("feature_version") != "bearing-features-v2"
        or config.get("dataset_manifest_sha256") != _sha256(args.dataset_manifest)
        or config.get("fold_manifest_sha256") != _sha256(args.fold_manifest)
        or config.get("development_processed_sha256") != development.processed_sha256
        or config.get("feature_cache_config_sha256") != development.config_sha
    ):
        raise ValueError("final config dataset/feature lineage does not match inputs")
    labels = _labels(args.labels)
    missing_sources = sorted(
        bearing_id
        for bearing_id in policy.frozen_test
        if bearing_id not in labels or not (args.raw_dir / bearing_id).is_dir()
    )
    if missing_sources:
        raise FileNotFoundError(f"frozen-test inputs are missing: {missing_sources}")

    args.access_ledger.parent.mkdir(parents=True, exist_ok=True)
    _write_json(
        args.access_ledger,
        {
            "status": "started",
            "started_at": started_at,
            "config_sha256": config_sha,
            "config_commit": config_commit,
            "frozen_bearings": sorted(policy.frozen_test),
        },
    )

    test_rows: list[V2Row] = []
    for bearing_id in sorted(policy.frozen_test):
        test_rows.extend(
            prepare_paderborn_bearing(
                args.raw_dir,
                bearing_id,
                labels[bearing_id],
                int(config["window_size"]),
                int(config["stride"]),
            )
        )
    combined, test_feature_sha = _combined_dataset(development, test_rows)
    train_indices = np.arange(len(development.groups), dtype=np.int_)
    test_indices = np.arange(
        len(development.groups), len(combined.groups), dtype=np.int_
    )
    damaged = np.asarray(combined.targets != "healthy", dtype=np.int_)
    family = cast(FaultFamily, str(selected["family"]))
    preprocessor = PaderbornFaultV2Preprocessor.fit(
        combined, family, train_indices, damaged
    )
    model = _classifier(
        Candidate(str(selected["algorithm"]), dict(selected["hyperparameters"])),
        args.jobs,
    )
    model.fit(preprocessor.transform(combined, train_indices), damaged[train_indices])
    probability = np.asarray(
        model.predict_proba(preprocessor.transform(combined, test_indices))[:, 1],
        dtype=np.float64,
    )
    metrics = _binary_metrics(damaged[test_indices], probability)
    metrics["brier"] = float(brier_score_loss(damaged[test_indices], probability))
    final_checks = {
        "macro_recall_at_least_0_70": metrics["macro_recall"] >= 0.70,
        "healthy_recall_at_least_0_60": metrics["healthy_recall"] >= 0.60,
    }
    final_passed = all(final_checks.values())
    finished_at = datetime.now(UTC).isoformat()
    artifact_sha: str | None = None
    artifact_relative_path: str | None = None
    if final_passed:
        model_version = f"paderborn-fault-v2-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
        artifact_dir = args.artifact_root.resolve() / model_version
        artifact_sha = save_artifact_bundle(
            artifact_dir,
            model=model,
            preprocessor=preprocessor,
            feature_names=list(preprocessor.output_feature_names),
            feature_schema_version="bearing-features-v2",
            model_version=model_version,
            metadata={
                "run_name": "paderborn-fault-v2-final",
                "task_type": "fault_classification",
                "algorithm": str(selected["algorithm"]),
                "hyperparameters": dict(selected["hyperparameters"]),
                "dataset_version": development.dataset_version,
                "dataset_manifest_sha256": _sha256(args.dataset_manifest),
                "processed_sha256": development.processed_sha256,
                "config_path": args.config.as_posix(),
                "config_sha256": config_sha,
                "git_commit_sha": config_commit,
                "seed": SEED,
                "sample_counts": {
                    "train": len(train_indices),
                    "validation": 0,
                    "test": len(test_indices),
                    "groups": len(set(combined.groups.tolist())),
                },
                "training_started_at": started_at,
                "training_finished_at": finished_at,
                "frozen_test_usage": "single final evaluation",
            },
            metrics={
                "development": dict(selected["metrics"]),
                "final_test": metrics,
                "promotion": {"passed": final_passed, "checks": final_checks},
            },
        )
        artifact_relative_path = artifact_dir.relative_to(REPO_ROOT).as_posix()

    result = {
        "experiment_id": "paderborn-fault-v2-single-final-test",
        "dataset_version": development.dataset_version,
        "dataset_manifest_sha256": _sha256(args.dataset_manifest),
        "feature_version": "bearing-features-v2",
        "development_processed_sha256": development.processed_sha256,
        "frozen_test_feature_sha256": test_feature_sha,
        "fold_manifest": args.fold_manifest.as_posix(),
        "development_summary": args.development_summary.as_posix(),
        "development_summary_sha256": summary_sha,
        "config": args.config.as_posix(),
        "config_sha256": config_sha,
        "config_commit": config_commit,
        "algorithm": str(selected["algorithm"]),
        "hyperparameters": dict(selected["hyperparameters"]),
        "feature_family": family,
        "threshold": 0.50,
        "seed": SEED,
        "started_at": started_at,
        "finished_at": finished_at,
        "frozen_test_accessed": True,
        "frozen_test_bearings": sorted(policy.frozen_test),
        "frozen_test_rows": len(test_indices),
        "metrics": metrics,
        "promotion": {"passed": final_passed, "checks": final_checks},
        "prediction_artifact_hash": hashlib.sha256(probability.tobytes()).hexdigest(),
        "model_artifact_path": artifact_relative_path,
        "model_artifact_sha256": artifact_sha,
        "registry_status": "eligible_for_candidate_registration"
        if final_passed
        else "rejected; no candidate or staging registration",
        "replay_policy": "forbidden",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    _write_json(args.output, result)
    _write_json(args.access_ledger, {**result, "status": "completed"})
    print(
        f"final macro_recall={metrics['macro_recall']:.4f}; "
        f"healthy_recall={metrics['healthy_recall']:.4f}; passed={final_passed}"
    )


def _validate_committed_config(
    path: Path,
    config: dict[str, Any],
    summary: dict[str, Any],
    summary_sha: str,
    policy: PaderbornAccessPolicy,
) -> str:
    selected = summary.get("selected")
    if not isinstance(selected, dict) or not selected.get("promotion", {}).get(
        "passed"
    ):
        raise ValueError("Development candidate did not pass promotion gates")
    if (
        config.get("locked") is not True
        or config.get("frozen_test_accessed") is not False
    ):
        raise ValueError("final config must be locked before frozen-test access")
    if config.get("development_summary_sha256") != summary_sha:
        raise ValueError("final config does not pin the Development summary")
    expected = {
        "feature_family": selected["family"],
        "algorithm": selected["algorithm"],
        "hyperparameters": selected["hyperparameters"],
        "threshold": 0.50,
        "development_bearings": sorted(policy.development),
        "frozen_test_bearings": sorted(policy.frozen_test),
    }
    for key, value in expected.items():
        if config.get(key) != value:
            raise ValueError(f"final config does not match selected {key}")
    relative = path.resolve().relative_to(REPO_ROOT).as_posix()
    subprocess.run(
        ["git", "ls-files", "--error-unmatch", relative],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
    )
    if subprocess.run(
        ["git", "diff", "--quiet", "HEAD", "--", relative],
        cwd=REPO_ROOT,
        check=False,
    ).returncode:
        raise ValueError("final config has uncommitted changes")
    return subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", relative],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _combined_dataset(
    development: V2Dataset, rows: list[V2Row]
) -> tuple[V2Dataset, str]:
    if not rows:
        raise ValueError("frozen test extraction produced no rows")
    feature_names = tuple(sorted(rows[0].values))
    if feature_names != development.feature_names:
        raise ValueError("frozen-test feature schema differs from Development")
    if any(tuple(sorted(row.values)) != feature_names for row in rows):
        raise ValueError("frozen-test feature schema changed between rows")
    test_features = np.asarray(
        [[row.values[name] for name in feature_names] for row in rows],
        dtype=np.float64,
    )
    combined = V2Dataset(
        features=np.vstack([development.features, test_features]),
        targets=np.concatenate(
            [development.targets, np.asarray([str(row.target) for row in rows])]
        ),
        groups=np.concatenate(
            [development.groups, np.asarray([row.group for row in rows])]
        ),
        conditions=np.concatenate(
            [development.conditions, np.asarray([row.condition for row in rows])]
        ),
        sequence_indices=np.concatenate(
            [
                development.sequence_indices,
                np.asarray([row.sequence_index for row in rows], dtype=np.int64),
            ]
        ),
        feature_names=development.feature_names,
        dataset_name=development.dataset_name,
        dataset_version=development.dataset_version,
        config_sha=development.config_sha,
        processed_sha256=development.processed_sha256,
    )
    return combined, hashlib.sha256(test_features.tobytes()).hexdigest()


def _labels(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result = {row["bearing_id"]: row["fault_class"] for row in rows}
    if len(result) != len(rows):
        raise ValueError("official labels contain duplicate bearing IDs")
    return result


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected YAML mapping: {path}")
    return value


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    main()
