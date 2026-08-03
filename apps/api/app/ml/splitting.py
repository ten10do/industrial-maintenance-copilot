"""Bearing-level splitting helpers that prevent adjacent-window leakage."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from numpy.typing import NDArray
from sklearn.model_selection import GroupKFold, GroupShuffleSplit


@dataclass(frozen=True)
class GroupedSplit:
    train: NDArray[np.int64]
    validation: NDArray[np.int64]
    test: NDArray[np.int64]


@dataclass(frozen=True)
class LeakageAudit:
    train_groups: tuple[str, ...]
    validation_groups: tuple[str, ...]
    test_groups: tuple[str, ...]
    train_validation_overlap: tuple[str, ...]
    train_test_overlap: tuple[str, ...]
    validation_test_overlap: tuple[str, ...]

    @property
    def passed(self) -> bool:
        return not (
            self.train_validation_overlap
            or self.train_test_overlap
            or self.validation_test_overlap
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "train_bearings": list(self.train_groups),
            "validation_bearings": list(self.validation_groups),
            "test_bearings": list(self.test_groups),
            "train_validation_intersection": list(self.train_validation_overlap),
            "train_test_intersection": list(self.train_test_overlap),
            "validation_test_intersection": list(self.validation_test_overlap),
            "passed": self.passed,
        }


def grouped_train_validation_test_split(
    groups: list[str],
    *,
    test_size: float,
    validation_size: float,
    seed: int,
) -> GroupedSplit:
    """Split twice by bearing/run; validation_size is a fraction of all samples."""
    if not groups or len(set(groups)) < 3:
        raise ValueError("at least three distinct bearing groups are required")
    if test_size <= 0 or validation_size <= 0 or test_size + validation_size >= 1:
        raise ValueError(
            "test and validation fractions must be positive and sum below one"
        )
    indices = np.arange(len(groups), dtype=np.int64)
    group_array = np.asarray(groups)
    first = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_validation, test = next(first.split(indices, groups=group_array))
    relative_validation_size = validation_size / (1.0 - test_size)
    second = GroupShuffleSplit(
        n_splits=1, test_size=relative_validation_size, random_state=seed + 1
    )
    train_local, validation_local = next(
        second.split(train_validation, groups=group_array[train_validation])
    )
    split = GroupedSplit(
        train=indices[train_validation[train_local]],
        validation=indices[train_validation[validation_local]],
        test=indices[test],
    )
    assert_disjoint_groups(split, groups)
    return split


def grouped_split_from_manifest(groups: list[str], manifest_path: Path) -> GroupedSplit:
    """Materialize a pre-metric, immutable bearing split manifest."""
    value = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError("split manifest root must be an object")
    split_groups: dict[str, set[str]] = {}
    for name in ("train", "validation", "test"):
        configured = value.get(name)
        if not isinstance(configured, list) or not configured:
            raise ValueError(f"split manifest has no {name} groups")
        split_groups[name] = {str(item) for item in configured}
        if len(split_groups[name]) != len(configured):
            raise ValueError(f"split manifest has duplicate {name} groups")
    if (
        split_groups["train"] & split_groups["validation"]
        or split_groups["train"] & split_groups["test"]
        or split_groups["validation"] & split_groups["test"]
    ):
        raise ValueError("split manifest bearing groups overlap")
    observed = set(groups)
    configured_groups = set().union(*split_groups.values())
    if observed != configured_groups:
        raise ValueError(
            "split manifest and processed bearing groups differ: "
            f"missing={sorted(observed - configured_groups)}, "
            f"unexpected={sorted(configured_groups - observed)}"
        )
    group_array = np.asarray(groups)
    split = GroupedSplit(
        train=np.flatnonzero(np.isin(group_array, list(split_groups["train"]))).astype(
            np.int64
        ),
        validation=np.flatnonzero(
            np.isin(group_array, list(split_groups["validation"]))
        ).astype(np.int64),
        test=np.flatnonzero(np.isin(group_array, list(split_groups["test"]))).astype(
            np.int64
        ),
    )
    assert_disjoint_groups(split, groups)
    return split


def group_kfold_indices(
    groups: list[str], folds: int
) -> list[tuple[NDArray[np.int64], NDArray[np.int64]]]:
    if folds < 2 or folds > len(set(groups)):
        raise ValueError("fold count must be between 2 and the number of groups")
    indices = np.arange(len(groups), dtype=np.int64)
    splitter = GroupKFold(n_splits=folds)
    return [
        (train.astype(np.int64), test.astype(np.int64))
        for train, test in splitter.split(indices, groups=groups)
    ]


def assert_disjoint_groups(split: GroupedSplit, groups: list[str]) -> None:
    audit = group_split_audit(split, groups)
    if not audit.passed:
        raise AssertionError("bearing groups overlap across dataset splits")


def group_split_audit(split: GroupedSplit, groups: list[str]) -> LeakageAudit:
    group_array = np.asarray(groups)
    train = set(group_array[split.train].tolist())
    validation = set(group_array[split.validation].tolist())
    test = set(group_array[split.test].tolist())
    return LeakageAudit(
        train_groups=tuple(sorted(train)),
        validation_groups=tuple(sorted(validation)),
        test_groups=tuple(sorted(test)),
        train_validation_overlap=tuple(sorted(train & validation)),
        train_test_overlap=tuple(sorted(train & test)),
        validation_test_overlap=tuple(sorted(validation & test)),
    )
