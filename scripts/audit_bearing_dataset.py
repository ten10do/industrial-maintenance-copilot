"""Audit authorized Paderborn and XJTU-SY files before feature preparation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from download_paderborn_dataset import EXPECTED_BEARINGS
from scipy.io import whosmat

EXPECTED_XJTU_BEARINGS = tuple(
    [f"Bearing1_{index}" for index in range(1, 6)]
    + [f"Bearing2_{index}" for index in range(1, 6)]
    + [f"Bearing3_{index}" for index in range(1, 6)]
)
EXPECTED_XJTU_CONDITIONS = ("35Hz12kN", "37.5Hz11kN", "40Hz10kN")
EXPECTED_PADERBORN_CONDITIONS = (
    "N09_M07_F10",
    "N15_M01_F10",
    "N15_M07_F04",
    "N15_M07_F10",
)
REQUIRED_LABEL_COLUMNS = {
    "bearing_id",
    "condition_group",
    "damage_origin",
    "fault_location",
    "fault_type",
    "damage_level",
    "source_document",
    "source_table",
    "notes",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def audit_paderborn(
    raw_dir: Path,
    labels_path: Path,
    manifest_path: Path,
    *,
    expected_bearings: tuple[str, ...] = EXPECTED_BEARINGS,
    expected_files_per_bearing: int = 80,
    expected_conditions: tuple[str, ...] = EXPECTED_PADERBORN_CONDITIONS,
) -> dict[str, Any]:
    errors: list[str] = []
    labels, label_errors = _read_labels(labels_path)
    errors.extend(label_errors)
    mat_files = sorted(raw_dir.rglob("*.mat")) if raw_dir.exists() else []
    partial_files = sorted(raw_dir.rglob("*.partial")) if raw_dir.exists() else []
    corrupted: list[str] = []
    bearing_files: dict[str, list[Path]] = {}
    operating_conditions: set[str] = set()
    for path in mat_files:
        match = re.match(
            r"^(N\d+_M\d+_F\d+)_([A-Z0-9]+)_\d+$", path.stem, re.IGNORECASE
        )
        bearing_id = (
            match.group(2).upper()
            if match
            else _bearing_from_parent(path, set(expected_bearings))
        )
        if bearing_id is None:
            errors.append(f"cannot derive official bearing ID: {path.as_posix()}")
            continue
        bearing_files.setdefault(bearing_id, []).append(path)
        if match:
            operating_conditions.add(match.group(1).upper())
        try:
            if not whosmat(path):
                corrupted.append(path.as_posix())
        except (OSError, ValueError, TypeError) as exc:
            corrupted.append(f"{path.as_posix()}: {exc}")
    found_bearings = set(bearing_files)
    expected = set(expected_bearings)
    missing = sorted(expected - found_bearings)
    unexpected = sorted(found_bearings - expected)
    duplicate_names = sorted(
        name
        for name, count in Counter(path.name for path in mat_files).items()
        if count > 1
    )
    label_ids = set(labels)
    missing_labels = sorted(found_bearings - label_ids)
    missing_expected_labels = sorted(expected - label_ids)
    file_count_mismatches = {
        bearing_id: len(files)
        for bearing_id, files in bearing_files.items()
        if len(files) != expected_files_per_bearing
    }
    condition_mismatch = sorted(set(expected_conditions) ^ operating_conditions)
    origins = Counter(row.get("damage_origin", "unknown") for row in labels.values())
    manifest = _load_manifest(manifest_path, errors)
    archive_status = _audit_paderborn_archives(raw_dir, manifest, expected_bearings)
    errors.extend(archive_status.pop("errors"))
    if missing:
        errors.append(f"missing bearing directories/data: {missing}")
    if unexpected:
        errors.append(f"unexpected bearing IDs: {unexpected}")
    if corrupted:
        errors.append(f"corrupted MATLAB files: {len(corrupted)}")
    if duplicate_names:
        errors.append(f"duplicate MATLAB basenames: {duplicate_names[:10]}")
    if missing_labels:
        errors.append(f"bearings without labels: {missing_labels}")
    if missing_expected_labels:
        errors.append(
            f"expected bearings absent from label mapping: {missing_expected_labels}"
        )
    if file_count_mismatches:
        errors.append(
            "unexpected MATLAB file count per bearing: "
            f"{dict(sorted(file_count_mismatches.items()))}"
        )
    if condition_mismatch:
        errors.append(f"operating condition mismatch: {condition_mismatch}")
    if partial_files:
        errors.append(f"partial downloads remain: {len(partial_files)}")
    total_bytes = (
        sum(path.stat().st_size for path in raw_dir.rglob("*") if path.is_file())
        if raw_dir.exists()
        else 0
    )
    return {
        "dataset": "paderborn",
        "status": "PASS" if not errors else "FAIL",
        "dataset_files": len(mat_files),
        "total_bytes": total_bytes,
        "bearing_count": len(found_bearings),
        "bearing_ids": sorted(found_bearings),
        "healthy_bearing_count": origins.get("healthy", 0),
        "artificial_damage_bearing_count": origins.get("artificial", 0),
        "real_damage_bearing_count": origins.get("real", 0),
        "operating_conditions": sorted(operating_conditions),
        "channels": ["motor_current", "vibration"],
        "sampling": {
            "frequency_hz": 64000,
            "measurement_seconds": 4,
            "measurements_per_condition": 20,
        },
        "label_distribution": dict(
            sorted(
                Counter(
                    row.get("fault_class", "unknown") for row in labels.values()
                ).items()
            )
        ),
        "missing_bearings": missing,
        "mat_files_per_bearing": {
            bearing_id: len(files)
            for bearing_id, files in sorted(bearing_files.items())
        },
        "mat_file_count_mismatches": dict(sorted(file_count_mismatches.items())),
        "duplicate_files": duplicate_names,
        "corrupted_mat": corrupted,
        "partial_files": [path.as_posix() for path in partial_files],
        "label_mapping_count": len(labels),
        "bearings_without_labels": missing_labels,
        "archive_validation": archive_status,
        "errors": errors,
    }


def audit_xjtu(
    raw_dir: Path,
    manifest_path: Path,
    *,
    expected_bearings: tuple[str, ...] = EXPECTED_XJTU_BEARINGS,
    expected_samples: int = 32768,
) -> dict[str, Any]:
    errors: list[str] = []
    csv_files = sorted(raw_dir.rglob("*.csv")) if raw_dir.exists() else []
    partial_files = sorted(raw_dir.rglob("*.partial")) if raw_dir.exists() else []
    bearing_dirs = {
        path.parent.name: path.parent
        for path in csv_files
        if path.parent.name.lower().startswith("bearing")
    }
    found = set(bearing_dirs)
    expected = set(expected_bearings)
    missing = sorted(expected - found)
    unexpected = sorted(found - expected)
    condition_mapping_errors: list[str] = []
    malformed: list[str] = []
    sequence_errors: list[str] = []
    csv_per_bearing: dict[str, int] = {}
    run_lengths: dict[str, dict[str, float | int | str | None]] = {}
    observed_sample_counts: Counter[int] = Counter()
    observed_channel_counts: Counter[int] = Counter()
    for bearing_id, directory in sorted(bearing_dirs.items()):
        expected_condition = _expected_xjtu_condition(bearing_id)
        if (
            expected_condition is not None
            and directory.parent.name != expected_condition
        ):
            condition_mapping_errors.append(
                f"{bearing_id}: expected {expected_condition}, found {directory.parent.name}"
            )
        files = sorted(directory.glob("*.csv"), key=_numeric_csv_name)
        csv_per_bearing[bearing_id] = len(files)
        numeric_stems = [_optional_int(path.stem) for path in files]
        if any(value is None for value in numeric_stems):
            sequence_errors.append(f"{bearing_id}: non-numeric acquisition filename")
        else:
            values = [value for value in numeric_stems if value is not None]
            if values and values != list(range(values[0], values[0] + len(values))):
                sequence_errors.append(f"{bearing_id}: acquisition sequence has gaps")
        for path in files:
            try:
                samples, channels = _audit_csv(path)
                observed_sample_counts[samples] += 1
                observed_channel_counts[channels] += 1
                if samples != expected_samples or channels != 2:
                    malformed.append(
                        f"{path.as_posix()}: samples={samples}, channels={channels}"
                    )
            except (OSError, UnicodeError, ValueError) as exc:
                malformed.append(f"{path.as_posix()}: {exc}")
        run_lengths[bearing_id] = {
            "measurement_files": len(files),
            "hours_to_observed_endpoint": max(len(files) - 1, 0) / 60.0,
            "failure_endpoint": files[-1].name if files else None,
            "operating_condition": directory.parent.name,
        }
    manifest = _load_manifest(manifest_path, errors)
    archive_status = _audit_xjtu_archive(raw_dir, manifest)
    errors.extend(archive_status.pop("errors"))
    conditions = sorted({directory.parent.name for directory in bearing_dirs.values()})
    if missing:
        errors.append(f"missing bearing runs: {missing}")
    if unexpected:
        errors.append(f"unexpected bearing runs: {unexpected}")
    if sequence_errors:
        errors.append(f"sequence ordering failures: {len(sequence_errors)}")
    if malformed:
        errors.append(f"malformed CSV acquisitions: {len(malformed)}")
    if condition_mapping_errors:
        errors.append(
            f"operating condition mapping failures: {condition_mapping_errors}"
        )
    if partial_files:
        errors.append(f"partial downloads remain: {len(partial_files)}")
    total_bytes = (
        sum(path.stat().st_size for path in raw_dir.rglob("*") if path.is_file())
        if raw_dir.exists()
        else 0
    )
    return {
        "dataset": "xjtu-sy",
        "status": "PASS" if not errors else "FAIL",
        "total_bearings": len(found),
        "bearing_ids": sorted(found),
        "operating_conditions": conditions,
        "run_lengths": run_lengths,
        "measurement_files": len(csv_files),
        "csv_per_bearing": csv_per_bearing,
        "sampling_frequency_hz": 25600,
        "samples_per_measurement": dict(sorted(observed_sample_counts.items())),
        "channels": dict(sorted(observed_channel_counts.items())),
        "failure_endpoint_definition": "last observable acquisition in each complete run",
        "missing_bearings": missing,
        "malformed_csv": malformed,
        "sequence_ordering": sequence_errors,
        "condition_mapping_errors": condition_mapping_errors,
        "partial_files": [path.as_posix() for path in partial_files],
        "total_bytes": total_bytes,
        "archive_validation": archive_status,
        "errors": errors,
    }


def _read_labels(path: Path) -> tuple[dict[str, dict[str, str]], list[str]]:
    errors: list[str] = []
    if not path.is_file():
        return {}, [f"label mapping not found: {path.as_posix()}"]
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        columns = set(reader.fieldnames or [])
        missing_columns = sorted(REQUIRED_LABEL_COLUMNS - columns)
        if missing_columns:
            errors.append(f"label schema missing columns: {missing_columns}")
        rows = list(reader)
    labels: dict[str, dict[str, str]] = {}
    for row in rows:
        bearing_id = row.get("bearing_id", "").strip().upper()
        if not bearing_id:
            errors.append("label row has empty bearing_id")
            continue
        if bearing_id in labels:
            errors.append(f"duplicate label mapping: {bearing_id}")
        labels[bearing_id] = {key: (value or "").strip() for key, value in row.items()}
        for field in REQUIRED_LABEL_COLUMNS - {"notes"}:
            if not labels[bearing_id].get(field):
                errors.append(f"label {bearing_id} has empty {field}")
    return labels, errors


def _audit_paderborn_archives(
    raw_dir: Path, manifest: dict[str, Any], expected_bearings: tuple[str, ...]
) -> dict[str, Any]:
    errors: list[str] = []
    archive_dir = raw_dir / "_archives"
    archives = sorted(archive_dir.glob("*.rar")) if archive_dir.exists() else []
    records = {
        str(item.get("bearing_id")): item
        for item in manifest.get("archives", [])
        if isinstance(item, dict)
    }
    checksum_mismatches: list[str] = []
    for path in archives:
        bearing_id = path.stem.upper()
        record = records.get(bearing_id)
        if record is None:
            checksum_mismatches.append(f"{bearing_id}: missing manifest record")
            continue
        actual_hash = sha256(path)
        if actual_hash != record.get("sha256") or path.stat().st_size != record.get(
            "size_bytes"
        ):
            checksum_mismatches.append(f"{bearing_id}: size/SHA256 mismatch")
    missing_archives = sorted(
        set(expected_bearings) - {path.stem.upper() for path in archives}
    )
    if missing_archives:
        errors.append(f"missing archives: {missing_archives}")
    if checksum_mismatches:
        errors.append(f"archive checksum failures: {checksum_mismatches}")
    if not manifest.get("download_verified", False):
        errors.append("download manifest is not verified")
    return {
        "archive_count": len(archives),
        "missing_archives": missing_archives,
        "checksum_mismatches": checksum_mismatches,
        "checksum_status": "PASS"
        if not checksum_mismatches and not missing_archives
        else "FAIL",
        "errors": errors,
    }


def _audit_xjtu_archive(raw_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    archive_name = str(manifest.get("archive_name", "XJTU-SY_Bearing_Datasets.zip"))
    archive = raw_dir / "_archives" / archive_name
    mismatches: list[str] = []
    if not archive.is_file():
        errors.append(f"archive not found: _archives/{archive_name}")
    else:
        expected_hash = manifest.get("sha256")
        expected_size = manifest.get("archive_size_bytes")
        if not expected_hash or sha256(archive) != expected_hash:
            mismatches.append("SHA256 mismatch or absent")
        if (
            not isinstance(expected_size, int)
            or archive.stat().st_size != expected_size
        ):
            mismatches.append("archive size mismatch or absent")
    if mismatches:
        errors.append(f"archive validation failures: {mismatches}")
    if not manifest.get("download_verified", False):
        errors.append("download manifest is not verified")
    return {
        "archive_name": archive_name,
        "archive_size_bytes": archive.stat().st_size if archive.is_file() else 0,
        "checksum_status": "PASS" if not errors else "FAIL",
        "checksum_mismatches": mismatches,
        "errors": errors,
    }


def _audit_csv(path: Path) -> tuple[int, int]:
    samples = 0
    channels: int | None = None
    skipped_header = False
    with path.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.reader(stream):
            if not row or all(not value.strip() for value in row):
                continue
            try:
                values = [float(value) for value in row]
            except ValueError:
                if samples == 0 and not skipped_header:
                    skipped_header = True
                    continue
                raise ValueError(
                    f"non-numeric row after data begins: {row[:3]}"
                ) from None
            if channels is None:
                channels = len(values)
            elif len(values) != channels:
                raise ValueError("inconsistent channel count")
            samples += 1
    if channels is None:
        raise ValueError("empty CSV acquisition")
    return samples, channels


def _load_manifest(path: Path, errors: list[str]) -> dict[str, Any]:
    if not path.is_file():
        errors.append(f"manifest not found: {path.as_posix()}")
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"manifest cannot be read: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append("manifest root must be an object")
        return {}
    return value


def _bearing_from_parent(path: Path, expected: set[str]) -> str | None:
    for parent in path.parents:
        candidate = parent.name.upper()
        if candidate in expected:
            return candidate
    return None


def _optional_int(value: str) -> int | None:
    try:
        return int(value)
    except ValueError:
        return None


def _expected_xjtu_condition(bearing_id: str) -> str | None:
    match = re.fullmatch(r"Bearing([123])_[1-5]", bearing_id)
    if match is None:
        return None
    return EXPECTED_XJTU_CONDITIONS[int(match.group(1)) - 1]


def _numeric_csv_name(path: Path) -> tuple[int, str]:
    value = _optional_int(path.stem)
    return (value if value is not None else sys.maxsize, path.name)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=["paderborn", "xjtu-sy"])
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.dataset == "paderborn":
        if args.labels is None:
            parser.error("Paderborn audit requires --labels")
        result = audit_paderborn(
            args.raw_dir,
            args.labels,
            args.manifest or Path("data/manifests/paderborn-real-download.json"),
        )
    else:
        result = audit_xjtu(
            args.raw_dir,
            args.manifest or Path("data/manifests/xjtu-sy-real-download.json"),
        )
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    raise SystemExit(0 if result["status"] == "PASS" else 1)


if __name__ == "__main__":
    main()
