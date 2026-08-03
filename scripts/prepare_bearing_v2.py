"""Build resumable V2 feature caches without opening Paderborn frozen test data."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import prepare_bearing_dataset as v1_preparation
from app.ml.features import extract_features
from app.ml.types import FeatureVector, TelemetryWindow
from app.ml.v2_features import (
    FEATURE_SCHEMA_VERSION_V2,
    causal_multiscale_context,
    extract_dual_channel_features,
    extract_envelope_features,
    extract_spectral_features_v2,
)
from app.ml.v2_governance import PaderbornAccessPolicy

_STRING_WIDTHS = {
    "target": 64,
    "group": 32,
    "condition": 32,
    "sample_id": 64,
    "source_file": 256,
}


@dataclass(frozen=True, slots=True)
class V2Row:
    values: Mapping[str, float]
    target: str | float
    group: str
    condition: str
    sequence_index: int
    sample_id: str
    source_file: str


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=("paderborn", "xjtu-sy"))
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cache-root", type=Path, default=REPO_ROOT / "data" / "interim" / "v2-cache"
    )
    parser.add_argument("--fold-manifest", type=Path)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--window-size", type=int, default=4096)
    parser.add_argument("--stride", type=int, default=4096)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    dataset_manifest = _read_json(args.dataset_manifest)
    dataset_version = str(dataset_manifest["version"])
    processing_config = {
        "dataset": args.dataset,
        "dataset_version": dataset_version,
        "feature_version": FEATURE_SCHEMA_VERSION_V2,
    }
    if args.dataset == "paderborn":
        processing_config.update(
            {
                "window_size": args.window_size,
                "stride": args.stride,
                "channels": [
                    "vibration_1",
                    "phase_current_1",
                    "phase_current_2",
                ],
            }
        )
    else:
        processing_config.update(
            {
                "window_size": 32768,
                "stride": 32768,
                "channels": ["horizontal", "vertical"],
                "causal_horizons_minutes": [5, 15, 30, 60],
            }
        )
    config_sha = _json_sha256(processing_config)
    cache_dir = args.cache_root / args.dataset / config_sha[:16]
    if args.dataset == "paderborn":
        if args.fold_manifest is None or args.labels is None:
            parser.error("Paderborn V2 requires --fold-manifest and --labels")
        policy = PaderbornAccessPolicy.from_manifest(args.fold_manifest)
        labels = _read_paderborn_labels(args.labels, policy)
        bearing_ids = sorted(policy.development)
        for bearing_id in bearing_ids:
            policy.require_development(bearing_id)
            _prepare_cached_group(
                cache_dir,
                bearing_id,
                lambda bearing_id=bearing_id: prepare_paderborn_bearing(
                    args.raw_dir,
                    bearing_id,
                    labels[bearing_id],
                    args.window_size,
                    args.stride,
                ),
                config_sha,
                force=args.force,
            )
    else:
        bearing_dirs = _xjtu_bearing_dirs(args.raw_dir)
        bearing_ids = [path.name for path in bearing_dirs]
        if len(bearing_ids) != 15 or len(set(bearing_ids)) != 15:
            raise ValueError("XJTU V2 requires the 15 official bearing runs")
        for bearing_dir in bearing_dirs:
            _prepare_cached_group(
                cache_dir,
                bearing_dir.name,
                lambda bearing_dir=bearing_dir: prepare_xjtu_bearing(
                    args.raw_dir, bearing_dir
                ),
                config_sha,
                force=args.force,
            )
    _consolidate_cache(
        cache_dir,
        bearing_ids,
        args.output,
        dataset=args.dataset,
        dataset_version=dataset_version,
        config=processing_config,
        config_sha=config_sha,
    )


def prepare_paderborn_bearing(
    raw_dir: Path,
    bearing_id: str,
    fault_class: str,
    window_size: int,
    stride: int,
) -> list[V2Row]:
    bearing_dir = raw_dir / bearing_id
    if not bearing_dir.is_dir():
        raise FileNotFoundError(f"Paderborn development bearing missing: {bearing_id}")
    files = sorted(bearing_dir.glob("*.mat"), key=v1_preparation._paderborn_name)
    if not files:
        raise ValueError(f"no Paderborn MAT files for {bearing_id}")
    histories: dict[str, list[FeatureVector]] = {}
    rows: list[V2Row] = []
    sequence_index = 0
    for path in files:
        parts = path.stem.split("_")
        if len(parts) < 5 or parts[-2] != bearing_id:
            raise ValueError(f"unexpected Paderborn filename: {path.name}")
        condition = "_".join(parts[:3])
        measurement = int(parts[-1])
        signal = v1_preparation._load_paderborn_channel(path, "vibration_1")
        phase_current_1 = v1_preparation._load_paderborn_channel(
            path, "phase_current_1"
        )
        phase_current_2 = v1_preparation._load_paderborn_channel(
            path, "phase_current_2"
        )
        if not (len(signal) == len(phase_current_1) == len(phase_current_2)):
            raise ValueError(f"Paderborn high-rate channels do not align: {path}")
        history = histories.setdefault(condition, [])
        measurement_start = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(
            seconds=4 * (measurement - 1)
        )
        for window_index, start in enumerate(
            range(0, len(signal) - window_size + 1, stride)
        ):
            window_signal = signal[start : start + window_size]
            started = measurement_start + timedelta(seconds=start / 64_000)
            vector = extract_features(
                TelemetryWindow(
                    equipment_id="paderborn-test-rig",
                    bearing_id=bearing_id,
                    signal=tuple(float(value) for value in window_signal),
                    sampling_rate_hz=64_000,
                    started_at=started,
                    ended_at=started + timedelta(seconds=window_size / 64_000),
                    unit="m/s2",
                    operating_condition=condition,
                    context=v1_preparation._paderborn_context(parts[:3]),
                ),
                history=history,
            )
            v1_preparation._append_bounded_history(history, vector)
            values = dict(vector.values)
            values.update(extract_envelope_features(window_signal, 64_000))
            values.update(extract_spectral_features_v2(window_signal, 64_000))
            values.update(
                extract_dual_channel_features(
                    phase_current_1[start : start + window_size],
                    phase_current_2[start : start + window_size],
                    64_000,
                    first_name="phase_current_1",
                    second_name="phase_current_2",
                    cross_prefix="current_cross",
                )
            )
            source_file = path.relative_to(raw_dir).as_posix()
            rows.append(
                V2Row(
                    values=values,
                    target=fault_class,
                    group=bearing_id,
                    condition=condition,
                    sequence_index=sequence_index,
                    sample_id=_sample_id("paderborn-v2", source_file, window_index),
                    source_file=source_file,
                )
            )
            sequence_index += 1
    return rows


def prepare_xjtu_bearing(raw_dir: Path, bearing_dir: Path) -> list[V2Row]:
    files = sorted(bearing_dir.glob("*.csv"), key=v1_preparation._numeric_name)
    if not files:
        raise ValueError(f"no XJTU acquisitions for {bearing_dir.name}")
    history: list[FeatureVector] = []
    current_rows: list[V2Row] = []
    condition = bearing_dir.parent.name
    context = v1_preparation._xjtu_context(bearing_dir)
    for index, path in enumerate(files):
        raw = v1_preparation._load_xjtu_csv(path)
        if raw.ndim != 2 or raw.shape[1] != 2:
            raise ValueError(f"expected horizontal and vertical columns in {path}")
        horizontal = np.asarray(raw[:, 0], dtype=np.float64)
        vertical = np.asarray(raw[:, 1], dtype=np.float64)
        started = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(minutes=index)
        vector = extract_features(
            TelemetryWindow(
                equipment_id="xjtu-sy-test-rig",
                bearing_id=bearing_dir.name,
                signal=tuple(float(value) for value in horizontal),
                sampling_rate_hz=25_600,
                started_at=started,
                ended_at=started + timedelta(seconds=len(horizontal) / 25_600),
                unit="g",
                operating_condition=condition,
                context=context,
            ),
            history=history,
        )
        v1_preparation._append_bounded_history(history, vector)
        values = dict(vector.values)
        values.update(extract_dual_channel_features(horizontal, vertical, 25_600))
        remaining = len(files) - index - 1
        source_file = path.relative_to(raw_dir).as_posix()
        current_rows.append(
            V2Row(
                values=values,
                target=remaining / 60.0,
                group=bearing_dir.name,
                condition=condition,
                sequence_index=index,
                sample_id=_sample_id("xjtu-sy-v2", source_file, 0),
                source_file=source_file,
            )
        )
    causal = causal_multiscale_context([row.values for row in current_rows])
    return [
        V2Row(
            values={**row.values, **causal_values},
            target=row.target,
            group=row.group,
            condition=row.condition,
            sequence_index=row.sequence_index,
            sample_id=row.sample_id,
            source_file=row.source_file,
        )
        for row, causal_values in zip(current_rows, causal, strict=True)
    ]


def _prepare_cached_group(
    cache_dir: Path,
    group: str,
    prepare: Any,
    config_sha: str,
    *,
    force: bool,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    output = cache_dir / f"{group}.npz"
    if output.is_file() and not force:
        with np.load(output, allow_pickle=False) as payload:
            if str(payload["config_sha"].item()) == config_sha:
                print(f"cache hit: {group}")
                return
        raise ValueError(f"stale cache has unexpected config hash: {output}")
    rows = list(prepare())
    if not rows:
        raise ValueError(f"no rows generated for {group}")
    _write_rows(rows, output, config_sha)
    print(f"cached {group}: {len(rows)} rows")


def _write_rows(rows: Sequence[V2Row], path: Path, config_sha: str) -> None:
    feature_names = sorted(rows[0].values)
    if any(sorted(row.values) != feature_names for row in rows):
        raise ValueError("V2 feature schema changed within a bearing")
    targets = (
        np.asarray([float(row.target) for row in rows], dtype=np.float64)
        if isinstance(rows[0].target, float)
        else np.asarray(
            [str(row.target) for row in rows], dtype=f"<U{_STRING_WIDTHS['target']}"
        )
    )
    temporary = path.with_suffix(".npz.partial")
    with temporary.open("wb") as stream:
        np.savez_compressed(
            stream,
            features=np.asarray(
                [[row.values[name] for name in feature_names] for row in rows],
                dtype=np.float64,
            ),
            targets=targets,
            groups=np.asarray(
                [row.group for row in rows], dtype=f"<U{_STRING_WIDTHS['group']}"
            ),
            conditions=np.asarray(
                [row.condition for row in rows],
                dtype=f"<U{_STRING_WIDTHS['condition']}",
            ),
            sequence_indices=np.asarray(
                [row.sequence_index for row in rows], dtype=np.int64
            ),
            sample_ids=np.asarray(
                [row.sample_id for row in rows],
                dtype=f"<U{_STRING_WIDTHS['sample_id']}",
            ),
            source_files=np.asarray(
                [row.source_file for row in rows],
                dtype=f"<U{_STRING_WIDTHS['source_file']}",
            ),
            feature_names=np.asarray(feature_names),
            config_sha=np.asarray(config_sha),
        )
    temporary.replace(path)


def _consolidate_cache(
    cache_dir: Path,
    groups: Iterable[str],
    output: Path,
    *,
    dataset: str,
    dataset_version: str,
    config: dict[str, Any],
    config_sha: str,
) -> None:
    payloads: list[dict[str, NDArray[Any]]] = []
    expected_names: list[str] | None = None
    for group in groups:
        path = cache_dir / f"{group}.npz"
        if not path.is_file():
            raise FileNotFoundError(f"missing V2 bearing cache: {path}")
        with np.load(path, allow_pickle=False) as payload:
            if str(payload["config_sha"].item()) != config_sha:
                raise ValueError(f"V2 cache config hash mismatch: {path}")
            names = [str(value) for value in payload["feature_names"].tolist()]
            if expected_names is None:
                expected_names = names
            elif names != expected_names:
                raise ValueError("V2 feature schema differs between bearing caches")
            payloads.append(
                {
                    key: np.asarray(payload[key])
                    for key in (
                        "features",
                        "targets",
                        "groups",
                        "conditions",
                        "sequence_indices",
                        "sample_ids",
                        "source_files",
                    )
                }
            )
    if expected_names is None:
        raise ValueError("no V2 bearing caches found")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".npz.partial")
    with temporary.open("wb") as stream:
        np.savez_compressed(
            stream,
            **{
                key: np.concatenate([payload[key] for payload in payloads])
                for key in payloads[0]
            },
            feature_names=np.asarray(expected_names),
            dataset_name=np.asarray(dataset),
            dataset_version=np.asarray(dataset_version),
            feature_schema_version=np.asarray(FEATURE_SCHEMA_VERSION_V2),
            config_sha=np.asarray(config_sha),
        )
    temporary.replace(output)
    receipt = {
        "dataset_name": dataset,
        "dataset_version": dataset_version,
        "feature_schema_version": FEATURE_SCHEMA_VERSION_V2,
        "config": config,
        "config_sha": config_sha,
        "groups": len(payloads),
        "rows": int(sum(len(payload["groups"]) for payload in payloads)),
        "sha256": _sha256(output),
        "cache_directory": cache_dir.relative_to(REPO_ROOT).as_posix(),
        "git_sha": _git_sha(),
        "created_at": datetime.now(UTC).isoformat(),
    }
    output.with_suffix(".metadata.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {receipt['rows']} rows from {receipt['groups']} groups to {output}")


def _read_paderborn_labels(path: Path, policy: PaderbornAccessPolicy) -> dict[str, str]:
    import csv

    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    labels = {
        row["bearing_id"]: row["fault_class"]
        for row in rows
        if row["bearing_id"] in policy.development
    }
    if set(labels) != policy.development:
        raise ValueError("official labels do not cover all development bearings")
    return labels


def _xjtu_bearing_dirs(raw_dir: Path) -> list[Path]:
    roots = [path for path in raw_dir.rglob("Bearing*_*") if path.is_dir()]
    return sorted(roots, key=lambda path: (path.parent.name, path.name))


def _sample_id(dataset: str, source_file: str, index: int) -> str:
    return hashlib.sha256(f"{dataset}|{source_file}|{index}".encode()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _json_sha256(value: dict[str, Any]) -> str:
    serialized = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(serialized).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


if __name__ == "__main__":
    main()
