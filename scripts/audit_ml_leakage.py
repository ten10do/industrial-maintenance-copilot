"""Audit processed real-bearing datasets before formal model training."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
import yaml

FORBIDDEN_FEATURE_TOKENS = (
    "bearing_id",
    "fault_label",
    "fault_class",
    "damage_code",
    "damage_origin",
    "remaining_life",
    "rul",
    "failure_timestamp",
    "future",
    "target",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paderborn-processed", type=Path, required=True)
    parser.add_argument("--paderborn-split", type=Path, required=True)
    parser.add_argument("--paderborn-config", type=Path, required=True)
    parser.add_argument("--xjtu-processed", type=Path, required=True)
    parser.add_argument("--xjtu-split", type=Path, required=True)
    parser.add_argument("--xjtu-config", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    results = {
        "paderborn": audit_processed_dataset(
            args.paderborn_processed,
            args.paderborn_split,
            args.paderborn_config,
            require_future_consistency=False,
        ),
        "xjtu-sy": audit_processed_dataset(
            args.xjtu_processed,
            args.xjtu_split,
            args.xjtu_config,
            require_future_consistency=True,
        ),
    }
    status = (
        "PASS" if all(item["status"] == "PASS" for item in results.values()) else "FAIL"
    )
    payload = {"status": status, "datasets": results}
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(_markdown(payload), encoding="utf-8")
    print(json.dumps(payload, indent=2))
    raise SystemExit(0 if status == "PASS" else 1)


def audit_processed_dataset(
    processed_path: Path,
    split_manifest_path: Path,
    config_path: Path,
    *,
    require_future_consistency: bool,
) -> dict[str, Any]:
    errors: list[str] = []
    split_manifest = _read_json(split_manifest_path)
    config = _read_yaml(config_path)
    mapping = _split_map(split_manifest, errors)
    _audit_training_policy(config, split_manifest_path, errors)
    with np.load(processed_path, allow_pickle=False) as payload:
        required = {
            "features",
            "targets",
            "groups",
            "feature_names",
            "sample_ids",
            "source_files",
            "window_indices",
            "splits",
            "feature_versions",
            "operating_conditions",
            "rul_measurements",
            "rul_hours",
            "dataset_name",
            "dataset_version",
            "feature_schema_version",
        }
        missing = required - set(payload.files)
        if missing:
            errors.append(f"processed arrays missing: {sorted(missing)}")
            return _failed_result(processed_path, errors)
        features = np.asarray(payload["features"])
        groups = np.asarray(payload["groups"]).astype(str)
        names = np.asarray(payload["feature_names"]).astype(str).tolist()
        samples = np.asarray(payload["sample_ids"]).astype(str)
        sources = np.asarray(payload["source_files"]).astype(str)
        windows = np.asarray(payload["window_indices"], dtype=np.int64)
        splits = np.asarray(payload["splits"]).astype(str)
        versions = np.asarray(payload["feature_versions"]).astype(str)
        conditions = np.asarray(payload["operating_conditions"]).astype(str)
        rul_measurements = np.asarray(payload["rul_measurements"], dtype=np.int64)
        rul_hours = np.asarray(payload["rul_hours"], dtype=np.float64)
        dataset_name = str(payload["dataset_name"].item())
        dataset_version = str(payload["dataset_version"].item())
        feature_version = str(payload["feature_schema_version"].item())
    row_count = len(groups)
    aligned = (
        all(
            len(value) == row_count
            for value in (samples, sources, windows, splits, versions, conditions)
        )
        and features.shape[0] == row_count
    )
    if not aligned:
        errors.append("processed metadata arrays are not row-aligned")
    if not np.isfinite(features).all():
        errors.append("processed features contain NaN or Inf")
    expected_splits = np.asarray([mapping.get(group, "missing") for group in groups])
    mismatched_rows = int(np.sum(expected_splits != splits))
    if mismatched_rows:
        errors.append(f"bearing split assignment mismatch: {mismatched_rows} rows")
    missing_groups = sorted(set(groups) - set(mapping))
    if missing_groups:
        errors.append(f"groups absent from split manifest: {missing_groups}")
    source_splits: dict[str, set[str]] = defaultdict(set)
    source_windows: set[tuple[str, int]] = set()
    duplicate_source_windows = 0
    for source, window, split in zip(sources, windows, splits, strict=True):
        source_splits[source].add(split)
        key = (source, int(window))
        duplicate_source_windows += int(key in source_windows)
        source_windows.add(key)
    cross_split_sources = sorted(
        source for source, values in source_splits.items() if len(values) > 1
    )
    if cross_split_sources:
        errors.append(f"source files cross splits: {len(cross_split_sources)}")
    if duplicate_source_windows:
        errors.append(f"duplicate source windows: {duplicate_source_windows}")
    duplicate_sample_ids = row_count - len(set(samples.tolist()))
    if duplicate_sample_ids:
        errors.append(f"duplicate sample IDs: {duplicate_sample_ids}")
    forbidden = sorted(
        name
        for name in names
        if any(token in name.lower() for token in FORBIDDEN_FEATURE_TOKENS)
    )
    if forbidden:
        errors.append(f"label/future leakage feature names: {forbidden}")
    if set(versions.tolist()) != {feature_version}:
        errors.append("row feature versions differ from dataset feature schema")
    future_checks: dict[str, Any] = {"required": require_future_consistency}
    if require_future_consistency:
        future_errors = _audit_rul_time(groups, windows, rul_measurements, rul_hours)
        errors.extend(future_errors)
        future_checks.update(
            {
                "policy": "backward_only",
                "sequence_errors": future_errors,
                "passed": not future_errors,
            }
        )
    condition_distribution = {
        split: dict(sorted(Counter(conditions[splits == split].tolist()).items()))
        for split in ("train", "validation", "test")
    }
    intersections = {
        "train_validation": sorted(
            set(groups[splits == "train"]) & set(groups[splits == "validation"])
        ),
        "train_test": sorted(
            set(groups[splits == "train"]) & set(groups[splits == "test"])
        ),
        "validation_test": sorted(
            set(groups[splits == "validation"]) & set(groups[splits == "test"])
        ),
    }
    if any(intersections.values()):
        errors.append("bearing identity overlap detected")
    return {
        "status": "PASS" if not errors else "FAIL",
        "dataset": dataset_name,
        "dataset_version": dataset_version,
        "processed_sha256": _sha256(processed_path),
        "rows": row_count,
        "bearings": len(set(groups.tolist())),
        "feature_schema_version": feature_version,
        "train_bearings": sorted(set(groups[splits == "train"].tolist())),
        "validation_bearings": sorted(set(groups[splits == "validation"].tolist())),
        "test_bearings": sorted(set(groups[splits == "test"].tolist())),
        "intersections": intersections,
        "identity_leakage_check_passed": not any(intersections.values()),
        "source_leakage_check_passed": not cross_split_sources,
        "adjacent_window_leakage_check_passed": duplicate_source_windows == 0,
        "label_leakage_check_passed": not forbidden,
        "preprocessing_leakage_check_passed": not any(
            "policy" in error or "config" in error for error in errors
        ),
        "future_leakage": future_checks,
        "duplicate_sample_ids": duplicate_sample_ids,
        "condition_distribution": condition_distribution,
        "errors": errors,
    }


def _audit_training_policy(
    config: dict[str, Any], split_manifest_path: Path, errors: list[str]
) -> None:
    split = config.get("split")
    preprocessing = config.get("preprocessing")
    if not isinstance(split, dict) or split.get("strategy") != "locked_group_manifest":
        errors.append("config policy: split strategy is not locked_group_manifest")
    elif Path(str(split.get("manifest", ""))).name != split_manifest_path.name:
        errors.append("config policy: split manifest differs from audited manifest")
    if not isinstance(preprocessing, dict) or preprocessing.get("fit_split") != "train":
        errors.append("config policy: learned preprocessing is not train-only")
    if config.get("selection_split") != "validation":
        errors.append("config policy: model selection is not validation-only")
    if config.get("test_usage") != "final_selected_model_evaluation_once":
        errors.append("config policy: test usage is not final-evaluation-only")


def _audit_rul_time(
    groups: np.ndarray[Any, Any],
    windows: np.ndarray[Any, Any],
    remaining: np.ndarray[Any, Any],
    hours: np.ndarray[Any, Any],
) -> list[str]:
    errors: list[str] = []
    for group in sorted(set(groups.tolist())):
        mask = groups == group
        order = np.argsort(windows[mask])
        group_windows = windows[mask][order]
        group_remaining = remaining[mask][order]
        group_hours = hours[mask][order]
        if not np.array_equal(group_windows, np.arange(len(group_windows))):
            errors.append(f"{group}: acquisition indices are not continuous")
        expected = np.arange(len(group_remaining) - 1, -1, -1)
        if not np.array_equal(group_remaining, expected):
            errors.append(f"{group}: RUL measurements do not decrease causally")
        if not np.allclose(group_hours, group_remaining / 60.0):
            errors.append(f"{group}: RUL hour conversion differs from measurements/60")
    return errors


def _split_map(manifest: dict[str, Any], errors: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for split in ("train", "validation", "test"):
        values = manifest.get(split)
        if not isinstance(values, list) or not values:
            errors.append(f"split manifest has no {split} groups")
            continue
        for value in values:
            group = str(value)
            if group in mapping:
                errors.append(f"bearing appears in multiple splits: {group}")
            mapping[group] = split
    return mapping


def _failed_result(path: Path, errors: list[str]) -> dict[str, Any]:
    return {
        "status": "FAIL",
        "processed_sha256": _sha256(path),
        "errors": errors,
    }


def _markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Real-bearing leakage audit v1",
        "",
        f"Leakage Audit: **{payload['status']}**",
        "",
        "This report was generated before formal model training. Test metrics were not inspected when the splits were designed or audited.",
        "",
    ]
    for name, title in (("paderborn", "Paderborn"), ("xjtu-sy", "XJTU-SY")):
        item = payload["datasets"][name]
        lines.extend(
            [
                f"## {title}",
                "",
                f"- Result: **{item['status']}**",
                f"- Dataset version: `{item.get('dataset_version', 'unavailable')}`",
                f"- Rows / bearings: {item.get('rows', 0)} / {item.get('bearings', 0)}",
                f"- Train bearings: `{item.get('train_bearings', [])}`",
                f"- Validation bearings: `{item.get('validation_bearings', [])}`",
                f"- Test bearings: `{item.get('test_bearings', [])}`",
                f"- Intersections: `{item.get('intersections', {})}`",
                f"- Identity leakage check: {'PASS' if item.get('identity_leakage_check_passed') else 'FAIL'}",
                f"- Source/window leakage check: {'PASS' if item.get('source_leakage_check_passed') and item.get('adjacent_window_leakage_check_passed') else 'FAIL'}",
                f"- Label leakage check: {'PASS' if item.get('label_leakage_check_passed') else 'FAIL'}",
                f"- Preprocessing policy: {'PASS' if item.get('preprocessing_leakage_check_passed') else 'FAIL'} (scaler/model train-only; selection validation-only; test final-only)",
                f"- Future leakage check: {'PASS' if item.get('future_leakage', {}).get('passed', True) else 'FAIL'}",
                f"- Condition distribution: `{item.get('condition_distribution', {})}`",
                f"- Errors: `{item.get('errors', [])}`",
                "",
            ]
        )
    return "\n".join(lines) + "\n"


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _read_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected YAML mapping: {path}")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
