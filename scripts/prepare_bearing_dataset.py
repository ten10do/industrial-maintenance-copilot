"""Stream authorized bearing signals into traceable processed feature matrices."""

from __future__ import annotations

import argparse
import csv
import gc
import hashlib
import io
import json
import struct
import sys
import zlib
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, BinaryIO

import numpy as np
from scipy.io import loadmat

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.ml.features import FEATURE_SCHEMA_VERSION, extract_features
from app.ml.types import FeatureVector, TelemetryWindow

_STRING_DTYPES = {
    "target": "<U64",
    "group": "<U32",
    "sample_id": "<U64",
    "source_file": "<U256",
    "split": "<U10",
    "feature_version": "<U64",
    "operating_condition": "<U32",
}


@dataclass(frozen=True, slots=True)
class ProcessedRow:
    values: dict[str, float]
    target: str | float
    sample_id: str
    bearing_id: str
    source_file: str
    window_index: int
    split: str
    operating_condition: str
    rul_measurements: int
    rul_hours: float


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("dataset", choices=["paderborn", "xjtu-sy"])
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dataset-manifest", type=Path, required=True)
    parser.add_argument("--split-manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path)
    parser.add_argument("--signal-key", default="vibration_1")
    parser.add_argument("--signal-unit")
    parser.add_argument("--window-size", type=int, default=4096)
    parser.add_argument("--stride", type=int, default=4096)
    parser.add_argument("--chunk-rows", type=int, default=1024)
    parser.add_argument(
        "--task",
        choices=["fault_classification", "failure_risk", "rul"],
        default="fault_classification",
    )
    parser.add_argument("--failure-horizon-samples", type=int, default=30)
    args = parser.parse_args()
    dataset_manifest = _read_json(args.dataset_manifest)
    split_by_bearing = _load_split_map(args.split_manifest)
    signal_unit = args.signal_unit or ("m/s2" if args.dataset == "paderborn" else "g")
    if args.dataset == "paderborn":
        if args.task != "fault_classification" or args.labels is None:
            parser.error(
                "Paderborn preparation requires --labels and fault_classification"
            )
        rows = prepare_paderborn(
            args.raw_dir,
            args.labels,
            split_by_bearing,
            args.signal_key,
            signal_unit,
            args.window_size,
            args.stride,
        )
    else:
        if args.task not in {"rul", "failure_risk"}:
            parser.error("XJTU-SY preparation supports rul or failure_risk")
        rows = prepare_xjtu(
            args.raw_dir,
            split_by_bearing,
            args.task,
            args.failure_horizon_samples,
            signal_unit,
        )
    write_processed(
        rows,
        args.output,
        args.dataset,
        args.task,
        dataset_version=str(dataset_manifest["version"]),
        dataset_manifest=args.dataset_manifest,
        split_manifest=args.split_manifest,
        chunk_rows=args.chunk_rows,
        processing_config={
            "signal_key": args.signal_key,
            "signal_unit": signal_unit,
            "window_size": args.window_size if args.dataset == "paderborn" else 32768,
            "stride": args.stride if args.dataset == "paderborn" else 32768,
            "failure_horizon_samples": args.failure_horizon_samples,
            "trend_policy": "backward_only",
            "feature_channel": "vibration_1"
            if args.dataset == "paderborn"
            else "horizontal_vibration",
            "matlab_reader": (
                "scipy.io.loadmat with strict MAT-v5 named-channel fallback"
                if args.dataset == "paderborn"
                else None
            ),
        },
    )


def prepare_paderborn(
    raw_dir: Path,
    labels_path: Path,
    split_by_bearing: dict[str, str],
    signal_key: str,
    signal_unit: str,
    window_size: int,
    stride: int,
) -> Iterator[ProcessedRow]:
    labels = _read_labels(labels_path)
    histories: dict[tuple[str, str], list[FeatureVector]] = {}
    found = False
    for path in sorted(raw_dir.rglob("*.mat"), key=_paderborn_name):
        parts = path.stem.split("_")
        if len(parts) < 5:
            raise ValueError(
                f"cannot derive bearing ID from official filename: {path.name}"
            )
        bearing_id = parts[-2]
        if bearing_id not in labels:
            raise ValueError(f"missing official label mapping for bearing {bearing_id}")
        split = _required_split(split_by_bearing, bearing_id)
        condition = "_".join(parts[:3])
        measurement_number = int(parts[-1])
        signal = _load_paderborn_channel(path, signal_key)
        source_file = path.relative_to(raw_dir).as_posix()
        history = histories.setdefault((bearing_id, condition), [])
        measurement_start = datetime(2000, 1, 1, tzinfo=UTC) + timedelta(
            seconds=4 * (measurement_number - 1)
        )
        for window_index, start in enumerate(
            range(0, len(signal) - window_size + 1, stride)
        ):
            window_signal = signal[start : start + window_size]
            started = measurement_start + timedelta(seconds=start / 64000)
            vector = extract_features(
                TelemetryWindow(
                    equipment_id="paderborn-test-rig",
                    bearing_id=bearing_id,
                    signal=tuple(float(value) for value in window_signal),
                    sampling_rate_hz=64000,
                    started_at=started,
                    ended_at=started + timedelta(seconds=window_size / 64000),
                    unit=signal_unit,
                    operating_condition=condition,
                    context=_paderborn_context(parts[:3]),
                ),
                history=history,
            )
            _append_bounded_history(history, vector)
            yield ProcessedRow(
                values=vector.values,
                target=labels[bearing_id],
                sample_id=_sample_id("paderborn", source_file, window_index),
                bearing_id=bearing_id,
                source_file=source_file,
                window_index=window_index,
                split=split,
                operating_condition=condition,
                rul_measurements=-1,
                rul_hours=float("nan"),
            )
            found = True
    if not found:
        raise ValueError("no Paderborn MATLAB files found")


def prepare_xjtu(
    raw_dir: Path,
    split_by_bearing: dict[str, str],
    task: str,
    failure_horizon_samples: int,
    signal_unit: str,
) -> Iterator[ProcessedRow]:
    found = False
    bearing_dirs = sorted({path.parent for path in raw_dir.rglob("*.csv")})
    for bearing_dir in bearing_dirs:
        files = sorted(bearing_dir.glob("*.csv"), key=_numeric_name)
        if not files:
            continue
        bearing_id = bearing_dir.name
        split = _required_split(split_by_bearing, bearing_id)
        history: list[FeatureVector] = []
        context = _xjtu_context(bearing_dir)
        for index, path in enumerate(files):
            raw = _load_xjtu_csv(path)
            if raw.ndim != 2 or raw.shape[1] != 2:
                raise ValueError(f"expected exactly two vibration columns in {path}")
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
            _append_bounded_history(history, vector)
            remaining = len(files) - index - 1
            target: str | float = (
                remaining / 60.0
                if task == "rul"
                else ("1" if remaining <= failure_horizon_samples else "0")
            )
            source_file = path.relative_to(raw_dir).as_posix()
            yield ProcessedRow(
                values=vector.values,
                target=target,
                sample_id=_sample_id("xjtu-sy", source_file, 0),
                bearing_id=bearing_id,
                source_file=source_file,
                window_index=index,
                split=split,
                operating_condition=bearing_dir.parent.name,
                rul_measurements=remaining,
                rul_hours=remaining / 60.0,
            )
            found = True
    if not found:
        raise ValueError("no XJTU-SY CSV acquisitions found")


def write_processed(
    rows: Iterable[ProcessedRow],
    output: Path,
    dataset: str,
    task: str,
    *,
    dataset_version: str,
    dataset_manifest: Path,
    split_manifest: Path,
    chunk_rows: int,
    processing_config: dict[str, Any],
) -> None:
    if chunk_rows <= 0:
        raise ValueError("chunk_rows must be positive")
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=f".{output.stem}-", dir=output.parent) as name:
        workspace = Path(name)
        chunks: list[Path] = []
        feature_names: list[str] | None = None
        buffer: list[ProcessedRow] = []
        total_rows = 0
        for row in rows:
            names = sorted(row.values)
            if feature_names is None:
                feature_names = names
            elif names != feature_names:
                raise ValueError("feature schema differs between rows")
            buffer.append(row)
            if len(buffer) >= chunk_rows:
                chunks.append(
                    _write_chunk(workspace, len(chunks), buffer, feature_names)
                )
                total_rows += len(buffer)
                buffer.clear()
        if buffer:
            if feature_names is None:
                raise ValueError("no processed rows were generated")
            chunks.append(_write_chunk(workspace, len(chunks), buffer, feature_names))
            total_rows += len(buffer)
            buffer.clear()
        if not chunks or feature_names is None:
            raise ValueError("no processed rows were generated")
        arrays = _consolidate_chunks(
            workspace, chunks, total_rows, len(feature_names), task
        )
        temporary_output = output.with_suffix(f"{output.suffix}.tmp")
        with temporary_output.open("wb") as stream:
            np.savez_compressed(
                stream,
                **arrays,
                feature_names=np.asarray(feature_names),
                dataset_name=np.asarray(dataset),
                dataset_version=np.asarray(dataset_version),
                feature_schema_version=np.asarray(FEATURE_SCHEMA_VERSION),
            )
        temporary_output.replace(output)
        for value in arrays.values():
            if isinstance(value, np.memmap):
                value.flush()
                if value._mmap is not None:
                    value._mmap.close()
        arrays.clear()
        del value
        gc.collect()
    receipt = {
        "dataset_name": dataset,
        "dataset_version": dataset_version,
        "task_type": task,
        "processed_version": "bearing-processed-v1",
        "feature_schema_version": FEATURE_SCHEMA_VERSION,
        "rows": total_rows,
        "bearing_groups": len(_load_split_map(split_manifest)),
        "processing_config": processing_config,
        "dataset_manifest_sha256": _sha256(dataset_manifest),
        "split_manifest": split_manifest.as_posix(),
        "split_manifest_sha256": _sha256(split_manifest),
        "sha256": _sha256(output),
        "memory_strategy": f"streaming extraction; {chunk_rows}-row disk chunks; memmap consolidation",
        "created_at": datetime.now(UTC).isoformat(),
    }
    output.with_suffix(".metadata.json").write_text(
        json.dumps(receipt, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {total_rows} rows from {receipt['bearing_groups']} bearing groups to {output}"
    )


def _write_chunk(
    workspace: Path,
    index: int,
    rows: list[ProcessedRow],
    feature_names: list[str],
) -> Path:
    path = workspace / f"chunk-{index:05d}.npz"
    np.savez(
        path,
        features=np.asarray(
            [[row.values[name] for name in feature_names] for row in rows],
            dtype=np.float64,
        ),
        targets=np.asarray([row.target for row in rows]),
        groups=np.asarray(
            [row.bearing_id for row in rows], dtype=_STRING_DTYPES["group"]
        ),
        sample_ids=np.asarray(
            [row.sample_id for row in rows], dtype=_STRING_DTYPES["sample_id"]
        ),
        source_files=np.asarray(
            [row.source_file for row in rows], dtype=_STRING_DTYPES["source_file"]
        ),
        window_indices=np.asarray([row.window_index for row in rows], dtype=np.int32),
        splits=np.asarray([row.split for row in rows], dtype=_STRING_DTYPES["split"]),
        feature_versions=np.asarray(
            [FEATURE_SCHEMA_VERSION] * len(rows),
            dtype=_STRING_DTYPES["feature_version"],
        ),
        operating_conditions=np.asarray(
            [row.operating_condition for row in rows],
            dtype=_STRING_DTYPES["operating_condition"],
        ),
        rul_measurements=np.asarray(
            [row.rul_measurements for row in rows], dtype=np.int32
        ),
        rul_hours=np.asarray([row.rul_hours for row in rows], dtype=np.float64),
    )
    return path


def _consolidate_chunks(
    workspace: Path,
    chunks: list[Path],
    total_rows: int,
    feature_count: int,
    task: str,
) -> dict[str, np.memmap[Any, Any]]:
    specifications: dict[str, tuple[Any, tuple[int, ...]]] = {
        "features": (np.float64, (total_rows, feature_count)),
        "targets": (
            np.float64 if task == "rul" else _STRING_DTYPES["target"],
            (total_rows,),
        ),
        "groups": (_STRING_DTYPES["group"], (total_rows,)),
        "sample_ids": (_STRING_DTYPES["sample_id"], (total_rows,)),
        "source_files": (_STRING_DTYPES["source_file"], (total_rows,)),
        "window_indices": (np.int32, (total_rows,)),
        "splits": (_STRING_DTYPES["split"], (total_rows,)),
        "feature_versions": (_STRING_DTYPES["feature_version"], (total_rows,)),
        "operating_conditions": (
            _STRING_DTYPES["operating_condition"],
            (total_rows,),
        ),
        "rul_measurements": (np.int32, (total_rows,)),
        "rul_hours": (np.float64, (total_rows,)),
    }
    arrays = {
        key: np.lib.format.open_memmap(
            workspace / f"{key}.npy", mode="w+", dtype=dtype, shape=shape
        )
        for key, (dtype, shape) in specifications.items()
    }
    offset = 0
    for path in chunks:
        with np.load(path, allow_pickle=False) as payload:
            size = len(payload["groups"])
            for key, destination in arrays.items():
                destination[offset : offset + size] = payload[key]
        offset += size
    if offset != total_rows:
        raise AssertionError("processed chunk row count changed during consolidation")
    return arrays


def _read_labels(path: Path) -> dict[str, str]:
    with path.open(encoding="utf-8", newline="") as stream:
        reader = csv.DictReader(stream)
        labels = {
            row["bearing_id"].strip(): row["fault_class"].strip() for row in reader
        }
    if not labels:
        raise ValueError("label mapping is empty; populate it from official metadata")
    return labels


def _load_paderborn_channel(path: Path, signal_key: str) -> np.ndarray[Any, Any]:
    try:
        payload = loadmat(path, squeeze_me=True, struct_as_record=False)
    except (OSError, TypeError, ValueError) as scipy_error:
        try:
            signal = _load_mat5_named_y_channel(path, signal_key)
        except (OSError, TypeError, ValueError, zlib.error) as fallback_error:
            raise ValueError(
                f"cannot decode official MATLAB channel {signal_key!r} from "
                f"{path.name}; scipy={scipy_error}; fallback={fallback_error}"
            ) from fallback_error
        print(
            f"compatibility fallback decoded {signal_key!r} from {path.name} "
            f"after scipy.io.loadmat failed: {scipy_error}",
            file=sys.stderr,
        )
        return _validate_signal(signal, path, signal_key)
    root = payload.get(path.stem)
    if root is None or not hasattr(root, "Y"):
        raise ValueError(f"MATLAB payload has no official Y channel collection: {path}")
    matches: list[np.ndarray[Any, Any]] = []
    requested = signal_key.lower()
    for item in np.atleast_1d(root.Y):
        name = str(getattr(item, "Name", "")).lower()
        if name == requested or (
            requested == "vibration" and name.startswith("vibration_")
        ):
            matches.append(np.asarray(item.Data, dtype=np.float64).reshape(-1))
    if len(matches) != 1:
        raise ValueError(
            f"expected one official channel {signal_key!r} in {path.name}, found {len(matches)}"
        )
    return _validate_signal(matches[0], path, signal_key)


@dataclass(frozen=True, slots=True)
class _Mat5Matrix:
    stream: BinaryIO
    next_position: int
    matrix_class: int
    dimensions: tuple[int, ...]
    name: str


def _load_mat5_named_y_channel(path: Path, signal_key: str) -> np.ndarray[Any, Any]:
    """Read only Y.Name/Data from a MATLAB v5 struct after a general decode fails."""
    with path.open("rb") as stream:
        stream.seek(124)
        marker = stream.read(4)
        if len(marker) != 4 or marker[2:4] not in {b"IM", b"MI"}:
            raise ValueError("not a MATLAB v5 file")
        endian = "<" if marker[2:4] == b"IM" else ">"
        stream.seek(128)
        root = _open_mat5_matrix(stream, endian)
        if root.matrix_class != 2 or root.name != path.stem:
            raise ValueError("top-level MATLAB value is not the expected struct")
        root_fields = _read_mat5_struct_fields(root.stream, endian)
        y_matrix: _Mat5Matrix | None = None
        for field in root_fields:
            child = _open_mat5_matrix(root.stream, endian)
            if field == "Y":
                y_matrix = child
                break
            root.stream.seek(child.next_position)
        if y_matrix is None or y_matrix.matrix_class != 2:
            raise ValueError("MATLAB payload has no Y struct")

        fields = _read_mat5_struct_fields(y_matrix.stream, endian)
        entry_count = int(np.prod(y_matrix.dimensions))
        for _ in range(entry_count):
            channel_name = ""
            for field in fields:
                child = _open_mat5_matrix(y_matrix.stream, endian)
                if field == "Name":
                    channel_name = _read_mat5_char(child, endian)
                elif field == "Data" and _channel_matches(channel_name, signal_key):
                    # Return the complete, exactly named channel before parsing
                    # unrelated trailing optional metadata. One official KA08
                    # file has zero-filled tail metadata after otherwise intact
                    # high-rate vibration and phase-current arrays.
                    return _read_mat5_numeric(child, endian)
                y_matrix.stream.seek(child.next_position)
        raise ValueError(f"channel {signal_key!r} was not found")


def _open_mat5_matrix(stream: BinaryIO, endian: str) -> _Mat5Matrix:
    start = stream.tell()
    tag = stream.read(8)
    if len(tag) != 8:
        raise ValueError("truncated MATLAB matrix tag")
    data_type, size = struct.unpack(f"{endian}II", tag)
    next_position = start + 8 + size
    if data_type == 15:
        compressed = stream.read(size)
        if len(compressed) != size:
            raise ValueError("truncated compressed MATLAB matrix")
        payload = io.BytesIO(zlib.decompress(compressed))
        inner = payload.read(8)
        if len(inner) != 8:
            raise ValueError("truncated inner MATLAB matrix tag")
        data_type, _ = struct.unpack(f"{endian}II", inner)
        matrix_stream: BinaryIO = payload
    else:
        matrix_stream = stream
    if data_type != 14:
        raise TypeError(f"expected MATLAB matrix type 14, found {data_type}")

    flags_type, flags = _read_mat5_element(matrix_stream, endian)
    dims_type, dims = _read_mat5_element(matrix_stream, endian)
    name_type, name = _read_mat5_element(matrix_stream, endian)
    if flags_type != 6 or len(flags) < 4 or dims_type != 5 or name_type != 1:
        raise ValueError("invalid MATLAB matrix header")
    matrix_class = struct.unpack(f"{endian}I", flags[:4])[0] & 0xFF
    if len(dims) % 4:
        raise ValueError("invalid MATLAB dimensions")
    dimensions = struct.unpack(f"{endian}{len(dims) // 4}i", dims)
    return _Mat5Matrix(
        stream=matrix_stream,
        next_position=next_position,
        matrix_class=matrix_class,
        dimensions=tuple(int(value) for value in dimensions),
        name=name.rstrip(b"\0").decode("latin1"),
    )


def _read_mat5_element(stream: BinaryIO, endian: str) -> tuple[int, bytes]:
    tag = stream.read(8)
    if len(tag) != 8:
        raise ValueError("truncated MATLAB data element")
    packed_type = struct.unpack(f"{endian}I", tag[:4])[0]
    small_size = packed_type >> 16
    if small_size:
        if small_size > 4:
            raise ValueError("invalid small MATLAB data element")
        return packed_type & 0xFFFF, tag[4 : 4 + small_size]
    size = struct.unpack(f"{endian}I", tag[4:])[0]
    data = stream.read(size)
    if len(data) != size:
        raise ValueError("truncated MATLAB data element payload")
    padding = (-size) % 8
    if padding:
        stream.seek(padding, 1)
    return packed_type, data


def _read_mat5_struct_fields(stream: BinaryIO, endian: str) -> list[str]:
    length_type, length_data = _read_mat5_element(stream, endian)
    names_type, names_data = _read_mat5_element(stream, endian)
    if length_type != 5 or len(length_data) != 4 or names_type != 1:
        raise ValueError("invalid MATLAB struct field table")
    width = struct.unpack(f"{endian}i", length_data)[0]
    if width <= 0 or len(names_data) % width:
        raise ValueError("invalid MATLAB struct field width")
    return [
        names_data[index : index + width].split(b"\0", 1)[0].decode("latin1")
        for index in range(0, len(names_data), width)
    ]


def _read_mat5_char(matrix: _Mat5Matrix, endian: str) -> str:
    data_type, data = _read_mat5_element(matrix.stream, endian)
    if data_type in {4, 17}:
        if len(data) % 2:
            raise ValueError("invalid UTF-16 MATLAB character data")
        values = np.frombuffer(data, dtype=f"{endian}u2")
        return "".join(chr(int(value)) for value in values if value)
    if data_type in {1, 2, 16}:
        return data.rstrip(b"\0").decode("utf-8")
    raise TypeError(f"unsupported MATLAB character type {data_type}")


def _read_mat5_numeric(matrix: _Mat5Matrix, endian: str) -> np.ndarray[Any, Any]:
    data_type, data = _read_mat5_element(matrix.stream, endian)
    dtypes = {
        1: "i1",
        2: "u1",
        3: "i2",
        4: "u2",
        5: "i4",
        6: "u4",
        7: "f4",
        9: "f8",
        12: "i8",
        13: "u8",
    }
    try:
        dtype = np.dtype(f"{endian}{dtypes[data_type]}")
    except KeyError:
        raise TypeError(f"unsupported MATLAB numeric type {data_type}") from None
    expected = int(np.prod(matrix.dimensions))
    values = np.frombuffer(data, dtype=dtype)
    if len(values) != expected:
        raise ValueError(
            f"MATLAB numeric length mismatch: expected {expected}, found {len(values)}"
        )
    return values.astype(np.float64, copy=True)


def _channel_matches(channel_name: str, signal_key: str) -> bool:
    name = channel_name.lower()
    requested = signal_key.lower()
    return name == requested or (
        requested == "vibration" and name.startswith("vibration_")
    )


def _validate_signal(
    signal: np.ndarray[Any, Any], path: Path, signal_key: str
) -> np.ndarray[Any, Any]:
    result = np.asarray(signal, dtype=np.float64).reshape(-1)
    if not len(result) or not np.isfinite(result).all():
        raise ValueError(
            f"channel {signal_key!r} in {path.name} is empty or non-finite"
        )
    return result


def _load_split_map(path: Path) -> dict[str, str]:
    manifest = _read_json(path)
    result: dict[str, str] = {}
    for split in ("train", "validation", "test"):
        groups = manifest.get(split)
        if not isinstance(groups, list) or not groups:
            raise ValueError(f"split manifest has no {split} groups")
        for group in groups:
            name = str(group)
            if name in result:
                raise ValueError(f"bearing appears in multiple splits: {name}")
            result[name] = split
    return result


def _required_split(mapping: dict[str, str], bearing_id: str) -> str:
    try:
        return mapping[bearing_id]
    except KeyError:
        raise ValueError(
            f"bearing is absent from locked split manifest: {bearing_id}"
        ) from None


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _sample_id(dataset: str, source_file: str, window_index: int) -> str:
    value = f"{dataset}|{source_file}|{window_index}".encode()
    return hashlib.sha256(value).hexdigest()


def _append_bounded_history(
    history: list[FeatureVector], vector: FeatureVector
) -> None:
    if not history:
        history.append(vector)
        return
    history.append(vector)
    if len(history) > 10:
        del history[1]


def _paderborn_name(path: Path) -> tuple[str, str, int]:
    parts = path.stem.split("_")
    measurement = int(parts[-1]) if parts[-1].isdigit() else sys.maxsize
    return path.parent.name, "_".join(parts[:3]), measurement


def _numeric_name(path: Path) -> tuple[int, str]:
    try:
        return int(path.stem), path.name
    except ValueError:
        return sys.maxsize, path.name


def _xjtu_context(bearing_dir: Path) -> dict[str, float]:
    conditions = {
        "35hz12kn": {"speed_rpm": 2100.0, "radial_force_kn": 12.0},
        "37.5hz11kn": {"speed_rpm": 2250.0, "radial_force_kn": 11.0},
        "40hz10kn": {"speed_rpm": 2400.0, "radial_force_kn": 10.0},
    }
    return conditions.get(bearing_dir.parent.name.lower(), {})


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
        return np.loadtxt(path, delimiter=",", dtype=np.float64, skiprows=1)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
