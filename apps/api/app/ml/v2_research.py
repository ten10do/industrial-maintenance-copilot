"""Typed dataset and split transforms for Predictive Model V2 research."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import numpy as np
from numpy.typing import NDArray

from app.ml.features import feature_definitions
from app.ml.v2_features import FEATURE_SCHEMA_VERSION_V2

FaultFamily = Literal["F0", "F1", "F2", "F3", "F4"]
RulFamily = Literal["R0", "R1", "R2", "R3"]
_EPSILON = 1e-12
_CONDITION_FEATURES = (
    "rms",
    "kurtosis",
    "crest_factor",
    "spectral_centroid_hz",
    "low_band_energy",
    "mid_band_energy",
    "high_band_energy",
    "low_energy_ratio",
    "mid_energy_ratio",
    "high_energy_ratio",
)
_DEGRADATION_FEATURES = (
    "horizontal_rms",
    "vertical_rms",
    "horizontal_kurtosis",
    "vertical_kurtosis",
    "horizontal_envelope_energy",
    "vertical_envelope_energy",
)


@dataclass(frozen=True, slots=True)
class V2Dataset:
    features: NDArray[np.float64]
    targets: NDArray[Any]
    groups: NDArray[np.str_]
    conditions: NDArray[np.str_]
    sequence_indices: NDArray[np.int64]
    feature_names: tuple[str, ...]
    dataset_name: str
    dataset_version: str
    config_sha: str
    processed_sha256: str

    @classmethod
    def load(cls, path: Path, *, expected_dataset: str) -> V2Dataset:
        with np.load(path, allow_pickle=False) as payload:
            required = {
                "features",
                "targets",
                "groups",
                "conditions",
                "sequence_indices",
                "feature_names",
                "dataset_name",
                "dataset_version",
                "feature_schema_version",
                "config_sha",
            }
            missing = required - set(payload.files)
            if missing:
                raise ValueError(f"V2 dataset arrays missing: {sorted(missing)}")
            dataset_name = str(payload["dataset_name"].item())
            feature_version = str(payload["feature_schema_version"].item())
            if dataset_name != expected_dataset:
                raise ValueError(f"expected {expected_dataset}, found {dataset_name}")
            if feature_version != FEATURE_SCHEMA_VERSION_V2:
                raise ValueError(
                    f"expected {FEATURE_SCHEMA_VERSION_V2}, found {feature_version}"
                )
            features = np.asarray(payload["features"], dtype=np.float64)
            targets = np.asarray(payload["targets"])
            groups = np.asarray(payload["groups"], dtype=np.str_)
            conditions = np.asarray(payload["conditions"], dtype=np.str_)
            sequence_indices = np.asarray(payload["sequence_indices"], dtype=np.int64)
            names = tuple(str(value) for value in payload["feature_names"].tolist())
            dataset_version = str(payload["dataset_version"].item())
            config_sha = str(payload["config_sha"].item())
        size = len(groups)
        if features.ndim != 2 or features.shape != (size, len(names)):
            raise ValueError("V2 feature matrix is not aligned")
        if any(
            len(values) != size for values in (targets, conditions, sequence_indices)
        ):
            raise ValueError("V2 lineage arrays are not aligned")
        if len(set(names)) != len(names) or not np.isfinite(features).all():
            raise ValueError("V2 features are duplicated or non-finite")
        return cls(
            features=features,
            targets=targets,
            groups=groups,
            conditions=conditions,
            sequence_indices=sequence_indices,
            feature_names=names,
            dataset_name=dataset_name,
            dataset_version=dataset_version,
            config_sha=config_sha,
            processed_sha256=_sha256(path),
        )

    def columns(self, names: tuple[str, ...]) -> NDArray[np.float64]:
        lookup = {name: index for index, name in enumerate(self.feature_names)}
        missing = sorted(set(names) - lookup.keys())
        if missing:
            raise ValueError(f"V2 feature columns missing: {missing}")
        return np.asarray(self.features[:, [lookup[name] for name in names]])


def fault_family_feature_names(
    dataset: V2Dataset, family: FaultFamily
) -> tuple[str, ...]:
    v1 = tuple(
        definition.name
        for definition in feature_definitions(
            ("load_torque_nm", "radial_force_n", "speed_rpm")
        )
        if definition.name in dataset.feature_names
    )
    envelope = tuple(
        name
        for name in dataset.feature_names
        if name.startswith("envelope_") and name not in v1
    )
    current = tuple(
        name
        for name in dataset.feature_names
        if name.startswith(("phase_current_", "current_cross_"))
    )
    if family in {"F0", "F2"}:
        return v1
    if family in {"F1", "F3"}:
        return tuple(dict.fromkeys((*v1, *envelope)))
    return tuple(dict.fromkeys((*v1, *envelope, *current)))


def fault_fold_matrices(
    dataset: V2Dataset,
    family: FaultFamily,
    train_indices: NDArray[np.int_],
    validation_indices: NDArray[np.int_],
    damaged: NDArray[np.int_],
) -> tuple[NDArray[np.float64], NDArray[np.float64], tuple[str, ...]]:
    names = fault_family_feature_names(dataset, family)
    base = dataset.columns(names)
    train = base[train_indices]
    validation = base[validation_indices]
    if family not in {"F2", "F3", "F4"}:
        return train, validation, names
    normalized_train, normalized_validation, normalized_names = (
        condition_normalized_matrices(
            dataset, train_indices, validation_indices, damaged
        )
    )
    return (
        np.column_stack([train, normalized_train]),
        np.column_stack([validation, normalized_validation]),
        (*names, *normalized_names),
    )


def condition_normalized_matrices(
    dataset: V2Dataset,
    train_indices: NDArray[np.int_],
    validation_indices: NDArray[np.int_],
    damaged: NDArray[np.int_],
) -> tuple[NDArray[np.float64], NDArray[np.float64], tuple[str, ...]]:
    names = tuple(name for name in _CONDITION_FEATURES if name in dataset.feature_names)
    values = dataset.columns(names)
    healthy_train = train_indices[damaged[train_indices] == 0]
    if not len(healthy_train):
        raise ValueError("fault train fold has no healthy rows")
    pooled = _median_iqr(values[healthy_train])
    by_condition: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
    for condition in np.unique(dataset.conditions[train_indices]):
        selected = healthy_train[dataset.conditions[healthy_train] == condition]
        if len(selected):
            by_condition[str(condition)] = _median_iqr(values[selected])

    def transform(indices: NDArray[np.int_]) -> NDArray[np.float64]:
        result = np.empty((len(indices), len(names)), dtype=np.float64)
        for condition in np.unique(dataset.conditions[indices]):
            positions = np.flatnonzero(dataset.conditions[indices] == condition)
            center, scale = by_condition.get(str(condition), pooled)
            result[positions] = (values[indices[positions]] - center) / scale
        return result

    normalized_names = tuple(f"condition_normalized_{name}" for name in names)
    return transform(train_indices), transform(validation_indices), normalized_names


def rul_family_feature_names(dataset: V2Dataset, family: RulFamily) -> tuple[str, ...]:
    v1 = tuple(
        definition.name
        for definition in feature_definitions(("radial_force_kn", "speed_rpm"))
        if definition.name in dataset.feature_names
    )
    dual = tuple(
        name
        for name in dataset.feature_names
        if name.startswith(("horizontal_", "vertical_", "cross_"))
        and "_causal_" not in name
        and "_lag_" not in name
    )
    causal = tuple(
        name for name in dataset.feature_names if "_causal_" in name or "_lag_" in name
    )
    if family == "R0":
        return v1
    if family == "R1":
        return tuple(dict.fromkeys((*v1, *dual)))
    return tuple(dict.fromkeys((*v1, *dual, *causal)))


def rul_fold_matrices(
    dataset: V2Dataset,
    family: RulFamily,
    train_indices: NDArray[np.int_],
    validation_indices: NDArray[np.int_],
) -> tuple[NDArray[np.float64], NDArray[np.float64], tuple[str, ...]]:
    names = rul_family_feature_names(dataset, family)
    base = dataset.columns(names)
    train = base[train_indices]
    validation = base[validation_indices]
    if family != "R3":
        return train, validation, names
    degradation_train, degradation_validation = degradation_matrices(
        dataset, train_indices, validation_indices
    )
    return (
        np.column_stack([train, degradation_train]),
        np.column_stack([validation, degradation_validation]),
        (*names, "fold_local_degradation_distance"),
    )


def degradation_matrices(
    dataset: V2Dataset,
    train_indices: NDArray[np.int_],
    validation_indices: NDArray[np.int_],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    names = tuple(
        name for name in _DEGRADATION_FEATURES if name in dataset.feature_names
    )
    values = dataset.columns(names)
    early_indices: list[int] = []
    train_groups = dataset.groups[train_indices]
    for group in sorted(set(train_groups.tolist())):
        members = train_indices[train_groups == group]
        members = members[np.argsort(dataset.sequence_indices[members])]
        early_count = min(len(members), max(5, int(np.ceil(len(members) * 0.10))))
        early_indices.extend(int(value) for value in members[:early_count])
    center, scale = _median_iqr(values[np.asarray(early_indices, dtype=np.int_)])

    def transform(indices: NDArray[np.int_]) -> NDArray[np.float64]:
        normalized = (values[indices] - center) / scale
        return np.asarray(
            np.linalg.norm(normalized, axis=1).reshape(-1, 1), dtype=np.float64
        )

    return transform(train_indices), transform(validation_indices)


def grouped_condition_folds(
    groups: NDArray[np.str_],
    conditions: NDArray[np.str_],
    *,
    fold_count: int = 3,
    seed: int = 20260803,
) -> tuple[tuple[NDArray[np.int_], NDArray[np.int_]], ...]:
    unique_groups = sorted(set(groups.tolist()))
    group_condition = {
        group: str(np.unique(conditions[groups == group]).item())
        for group in unique_groups
    }
    validation_groups: list[list[str]] = [[] for _ in range(fold_count)]
    for condition in sorted(set(group_condition.values())):
        members = sorted(
            (group for group in unique_groups if group_condition[group] == condition),
            key=lambda group: (_seeded_hash(seed, condition, group), group),
        )
        for index, group in enumerate(members):
            validation_groups[index % fold_count].append(group)
    result = []
    for fold_groups in validation_groups:
        validation_mask = np.isin(groups, fold_groups)
        result.append(
            (np.flatnonzero(~validation_mask), np.flatnonzero(validation_mask))
        )
    if any(not len(train) or not len(validation) for train, validation in result):
        raise ValueError("grouped condition fold is empty")
    return tuple(result)


def _median_iqr(
    values: NDArray[np.float64],
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    lower, center, upper = np.percentile(values, [25, 50, 75], axis=0)
    return np.asarray(center), np.maximum(np.asarray(upper - lower), _EPSILON)


def _seeded_hash(seed: int, condition: str, group: str) -> str:
    return hashlib.sha256(f"{seed}|{condition}|{group}".encode()).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
