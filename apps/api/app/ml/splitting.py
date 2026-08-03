"""Bearing-level splitting helpers that prevent adjacent-window leakage."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from sklearn.model_selection import GroupKFold, GroupShuffleSplit


@dataclass(frozen=True)
class GroupedSplit:
    train: NDArray[np.int64]
    validation: NDArray[np.int64]
    test: NDArray[np.int64]


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
    group_array = np.asarray(groups)
    train = set(group_array[split.train].tolist())
    validation = set(group_array[split.validation].tolist())
    test = set(group_array[split.test].tolist())
    if train & validation or train & test or validation & test:
        raise AssertionError("bearing groups overlap across dataset splits")
