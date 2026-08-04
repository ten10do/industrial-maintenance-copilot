"""Generate the locked condition-balanced XJTU V2 outer folds."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np


def build_manifest(
    processed_path: Path, *, seed: int = 20260803, fold_count: int = 5
) -> dict[str, Any]:
    with np.load(processed_path, allow_pickle=False) as payload:
        if str(payload["dataset_name"].item()) != "xjtu-sy":
            raise ValueError("XJTU V2 fold source has the wrong dataset")
        groups = np.asarray(payload["groups"], dtype=np.str_)
        conditions = np.asarray(payload["conditions"], dtype=np.str_)
        dataset_version = str(payload["dataset_version"].item())
        feature_version = str(payload["feature_schema_version"].item())
        config_sha = str(payload["config_sha"].item())
    unique_groups = sorted(set(groups.tolist()))
    if len(unique_groups) != 15 or fold_count != 5:
        raise ValueError("XJTU V2 requires 15 bearings and five outer folds")
    group_condition = {
        group: str(np.unique(conditions[groups == group]).item())
        for group in unique_groups
    }
    validation_folds: list[list[str]] = [[] for _ in range(fold_count)]
    for condition in sorted(set(group_condition.values())):
        members = sorted(
            (group for group in unique_groups if group_condition[group] == condition),
            key=lambda group: (_seeded_hash(seed, condition, group), group),
        )
        if len(members) != fold_count:
            raise ValueError(
                f"operating condition does not have five bearings: {condition}"
            )
        for index, group in enumerate(members):
            validation_folds[index].append(group)
    all_groups = set(unique_groups)
    folds = [
        {
            "fold_id": f"fold-{index + 1}",
            "train": sorted(all_groups - set(validation)),
            "validation": sorted(validation),
            "validation_conditions": {
                group: group_condition[group] for group in sorted(validation)
            },
        }
        for index, validation in enumerate(validation_folds)
    ]
    seen = [group for fold in folds for group in fold["validation"]]
    if sorted(seen) != unique_groups or len(seen) != len(set(seen)):
        raise ValueError("each XJTU bearing must be outer validation exactly once")
    return {
        "dataset": "xjtu-sy",
        "manifest_version": "xjtu-v2-outer-folds-v1",
        "locked": True,
        "amendment": "docs/ml-experiments/v2.1-amendment.md",
        "designed_before_v2_1_rerun": True,
        "seed": seed,
        "fold_count": fold_count,
        "group": "bearing_id",
        "strategy": "deterministic condition-balanced five-fold grouped outer CV",
        "dataset_version": dataset_version,
        "feature_version": feature_version,
        "processed_config_sha": config_sha,
        "source_processed_sha256": _sha256(processed_path),
        "development_bearings": unique_groups,
        "unbiased_final_test": False,
        "folds": folds,
    }


def _seeded_hash(seed: int, condition: str, group: str) -> str:
    return hashlib.sha256(f"{seed}|{condition}|{group}".encode()).hexdigest()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()
    manifest = build_manifest(args.processed, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(manifest['folds'])} locked XJTU outer folds to {args.output}")


if __name__ == "__main__":
    main()
