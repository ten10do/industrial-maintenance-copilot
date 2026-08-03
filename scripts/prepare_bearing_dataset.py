"""Convert authorized Paderborn/XJTU-SY files into shared feature matrices."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.ml.features import FEATURE_SCHEMA_VERSION, extract_features  # noqa: E402
from app.ml.types import FeatureVector, TelemetryWindow  # noqa: E402
from app.ml.validation import split_windows  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=["paderborn", "xjtu-sy"])
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--signal-key", default="vibration")
    parser.add_argument("--signal-unit")
    parser.add_argument("--window-size", type=int, default=4096)
    parser.add_argument("--stride", type=int, default=4096)
    parser.add_argument(
        "--task",
        choices=["fault_classification", "failure_risk", "rul"],
        default="fault_classification",
    )
    parser.add_argument("--failure-horizon-samples", type=int, default=30)
    args = parser.parse_args()
    if args.dataset == "paderborn":
        if args.task != "fault_classification" or args.labels is None:
            parser.error(
                "Paderborn preparation requires --labels and fault_classification"
            )
        rows = prepare_paderborn(
            args.raw_dir,
            args.labels,
            args.signal_key,
            args.signal_unit or "m/s2",
            args.window_size,
            args.stride,
        )
    else:
        if args.task not in {"rul", "failure_risk"}:
            parser.error("XJTU-SY preparation supports rul or failure_risk")
        rows = prepare_xjtu(
            args.raw_dir,
            args.task,
            args.failure_horizon_samples,
            args.signal_unit or "g",
        )
    write_processed(
        rows,
        args.output,
        args.dataset,
        args.task,
        processing_config={
            "signal_key": args.signal_key,
            "signal_unit": args.signal_unit
            or ("m/s2" if args.dataset == "paderborn" else "g"),
            "window_size": args.window_size,
            "stride": args.stride,
            "failure_horizon_samples": args.failure_horizon_samples,
        },
    )


def prepare_paderborn(
    raw_dir: Path,
    labels_path: Path,
    signal_key: str,
    signal_unit: str,
    window_size: int,
    stride: int,
) -> list[tuple[FeatureVector, str]]:
    labels = _read_labels(labels_path)
    rows: list[tuple[FeatureVector, str]] = []
    history: dict[str, list[FeatureVector]] = {}
    for index, path in enumerate(sorted(raw_dir.rglob("*.mat"))):
        parts = path.stem.split("_")
        if len(parts) < 2:
            raise ValueError(
                f"cannot derive bearing ID from official filename: {path.name}"
            )
        bearing_id = parts[-2]
        if bearing_id not in labels:
            raise ValueError(f"missing official label mapping for bearing {bearing_id}")
        signal = _find_mat_signal(loadmat(path), signal_key)
        started = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(seconds=4 * index)
        measurement = TelemetryWindow(
            equipment_id="paderborn-test-rig",
            bearing_id=bearing_id,
            signal=tuple(float(value) for value in signal),
            sampling_rate_hz=64000,
            started_at=started,
            ended_at=started + timedelta(seconds=len(signal) / 64000),
            unit=signal_unit,
            operating_condition="_".join(parts[:3]),
            context=_paderborn_context(parts[:3]),
        )
        for window in split_windows(
            measurement, window_size=window_size, stride=stride
        ):
            vector = extract_features(
                window, history=history.setdefault(bearing_id, [])
            )
            history[bearing_id].append(vector)
            rows.append((vector, labels[bearing_id]))
    if not rows:
        raise ValueError("no Paderborn MATLAB files found")
    return rows


def prepare_xjtu(
    raw_dir: Path, task: str, failure_horizon_samples: int, signal_unit: str
) -> list[tuple[FeatureVector, str | float]]:
    rows: list[tuple[FeatureVector, str | float]] = []
    bearing_dirs = sorted({path.parent for path in raw_dir.rglob("*.csv")})
    for bearing_dir in bearing_dirs:
        files = sorted(bearing_dir.glob("*.csv"), key=_numeric_name)
        if not files:
            continue
        bearing_id = bearing_dir.name
        history: list[FeatureVector] = []
        context = _xjtu_context(bearing_dir)
        for index, path in enumerate(files):
            raw = _load_xjtu_csv(path)
            if raw.ndim != 2 or raw.shape[1] < 2:
                raise ValueError(f"expected horizontal/vertical columns in {path}")
            signal = raw[:, 0]
            started = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
            vector = extract_features(
                TelemetryWindow(
                    equipment_id="xjtu-sy-test-rig",
                    bearing_id=bearing_id,
                    signal=tuple(float(value) for value in signal),
                    sampling_rate_hz=25600,
                    started_at=started,
                    ended_at=started + timedelta(seconds=len(signal) / 25600),
                    unit=signal_unit,
                    operating_condition=bearing_dir.parent.name,
                    context=context,
                ),
                history=history,
            )
            history.append(vector)
            samples_remaining = len(files) - index - 1
            target: str | float
            if task == "rul":
                target = samples_remaining / 60.0
            else:
                target = "1" if samples_remaining <= failure_horizon_samples else "0"
            rows.append((vector, target))
    if not rows:
        raise ValueError("no XJTU-SY CSV acquisitions found")
    return rows


def write_processed(
    rows: list[tuple[FeatureVector, str | float]],
    output: Path,
    dataset: str,
    task: str,
    processing_config: dict[str, Any],
) -> None:
    feature_names = sorted(rows[0][0].values)
    if any(sorted(vector.values) != feature_names for vector, _ in rows):
        raise ValueError("feature schema differs between rows")
    features = np.asarray(
        [[vector.values[name] for name in feature_names] for vector, _ in rows],
        dtype=np.float64,
    )
    targets = np.asarray(
        [target for _, target in rows], dtype=np.float64 if task == "rul" else str
    )
    groups = np.asarray([vector.bearing_id for vector, _ in rows], dtype=str)
    output.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        output,
        features=features,
        targets=targets,
        groups=groups,
        feature_names=np.asarray(feature_names),
        dataset_name=np.asarray(dataset),
        dataset_version=np.asarray("bearing-processed-v1"),
        feature_schema_version=np.asarray(FEATURE_SCHEMA_VERSION),
    )
    receipt = {
        "dataset_name": dataset,
        "task_type": task,
        "processed_version": "bearing-processed-v1",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "rows": len(rows),
        "bearing_groups": len(set(groups.tolist())),
        "processing_config": processing_config,
        "sha256": hashlib.sha256(output.read_bytes()).hexdigest(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    output.with_suffix(".metadata.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {len(rows)} rows from {len(set(groups.tolist()))} bearing groups to {output}"
    )


def _read_labels(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        labels = {
            row["bearing_id"].strip(): row["fault_class"].strip() for row in reader
        }
    if not labels:
        raise ValueError("label mapping is empty; populate it from official metadata")
    return labels


def _find_mat_signal(value: Any, signal_key: str) -> np.ndarray[Any, Any]:
    candidates = list(_walk_mat(value, signal_key.lower()))
    if not candidates:
        raise ValueError(
            f"MATLAB payload does not contain configured signal key {signal_key!r}"
        )
    return np.asarray(
        max(candidates, key=lambda item: item.size), dtype=np.float64
    ).reshape(-1)


def _walk_mat(
    value: Any, signal_key: str, path: str = ""
) -> Iterator[np.ndarray[Any, Any]]:
    if isinstance(value, dict):
        for key, child in value.items():
            yield from _walk_mat(child, signal_key, f"{path}.{key}")
    elif isinstance(value, np.ndarray):
        if value.dtype.names:
            for name in value.dtype.names:
                yield from _walk_mat(value[name], signal_key, f"{path}.{name}")
        elif value.dtype == object:
            for child in value.flat:
                yield from _walk_mat(child, signal_key, path)
        elif signal_key in path.lower() and np.issubdtype(value.dtype, np.number):
            yield value


def _numeric_name(path: Path) -> tuple[int, str]:
    try:
        return int(path.stem), path.name
    except ValueError:
        return sys.maxsize, path.name


def _xjtu_context(bearing_dir: Path) -> dict[str, float]:
    name = bearing_dir.parent.name.lower()
    conditions = {
        "35hz12kn": {"speed_rpm": 2100.0, "radial_force_kn": 12.0},
        "37.5hz11kn": {"speed_rpm": 2250.0, "radial_force_kn": 11.0},
        "40hz10kn": {"speed_rpm": 2400.0, "radial_force_kn": 10.0},
    }
    return conditions.get(name, {})


def _paderborn_context(codes: list[str]) -> dict[str, float]:
    if len(codes) != 3:
        return {}
    try:
        return {
            "speed_rpm": float(codes[0][1:]) * 100.0,
            "load_torque_nm": float(codes[1][1:]) / 10.0,
            "radial_force_n": float(codes[2][1:]) * 100.0,
        }
    except (ValueError, IndexError):
        return {}


def _load_xjtu_csv(path: Path) -> np.ndarray[Any, Any]:
    try:
        return np.loadtxt(path, delimiter=",", dtype=np.float64)
    except ValueError:
        # Official archives commonly include a single descriptive header row.
        return np.loadtxt(path, delimiter=",", dtype=np.float64, skiprows=1)


if __name__ == "__main__":
    main()
