"""Generate the locked Paderborn V2 development folds before training."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


def build_manifest(
    split_path: Path,
    labels_path: Path,
    *,
    seed: int = 20260803,
    fold_count: int = 5,
) -> dict[str, Any]:
    if fold_count < 2:
        raise ValueError("fold_count must be at least two")
    split = _read_json(split_path)
    development = _string_list(split, "train") + _string_list(split, "validation")
    frozen_test = _string_list(split, "test")
    if len(development) != len(set(development)):
        raise ValueError("development bearing IDs are not unique")
    if set(development) & set(frozen_test):
        raise ValueError("frozen test bearing appears in development")

    labels = _read_labels(labels_path)
    missing = sorted(set(development) - labels.keys())
    if missing:
        raise ValueError(f"official labels missing development bearings: {missing}")

    strata: dict[tuple[str, str], list[str]] = defaultdict(list)
    for bearing_id in development:
        label = labels[bearing_id]
        strata[(label["damage_origin"], label["fault_class"])].append(bearing_id)

    validation_folds: list[list[str]] = [[] for _ in range(fold_count)]
    stratum_counts: list[Counter[tuple[str, str]]] = [
        Counter() for _ in range(fold_count)
    ]
    for stratum in sorted(strata):
        ordered = sorted(
            strata[stratum],
            key=lambda bearing_id: (
                _seeded_digest(seed, stratum, bearing_id),
                bearing_id,
            ),
        )
        for bearing_id in ordered:
            selected = min(
                range(fold_count),
                key=lambda index: (
                    stratum_counts[index][stratum],
                    len(validation_folds[index]),
                    index,
                ),
            )
            validation_folds[selected].append(bearing_id)
            stratum_counts[selected][stratum] += 1

    folds = []
    development_set = set(development)
    for index, validation in enumerate(validation_folds, start=1):
        validation = sorted(validation)
        train = sorted(development_set - set(validation))
        folds.append(
            {
                "fold_id": f"fold-{index}",
                "train": train,
                "validation": validation,
                "validation_distribution": _distribution(validation, labels),
            }
        )
    _validate_folds(folds, development_set, frozen_test, fold_count)
    return {
        "dataset": "paderborn",
        "manifest_version": "paderborn-v2-cv-folds-v1",
        "locked": True,
        "designed_before_v2_training": True,
        "seed": seed,
        "fold_count": fold_count,
        "group": "bearing_id",
        "strategy": "deterministic grouped stratification by damage_origin and fault_class",
        "source_split": split_path.as_posix(),
        "source_split_sha256": _sha256(split_path),
        "source_labels": labels_path.as_posix(),
        "source_labels_sha256": _sha256(labels_path),
        "development_bearings": sorted(development),
        "frozen_test_bearings": sorted(frozen_test),
        "frozen_test_accessed": False,
        "folds": folds,
    }


def _validate_folds(
    folds: list[dict[str, Any]],
    development: set[str],
    frozen_test: list[str],
    fold_count: int,
) -> None:
    seen: Counter[str] = Counter()
    for fold in folds:
        train = set(fold["train"])
        validation = set(fold["validation"])
        if train & validation or train | validation != development:
            raise ValueError("fold does not partition all development bearings")
        if (train | validation) & set(frozen_test):
            raise ValueError("fold includes a frozen test bearing")
        seen.update(validation)
    if len(folds) != fold_count or seen != Counter({item: 1 for item in development}):
        raise ValueError("each development bearing must be validation exactly once")


def _distribution(
    bearings: list[str], labels: dict[str, dict[str, str]]
) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for field in ("damage_origin", "fault_class"):
        counts = Counter(labels[bearing_id][field] for bearing_id in bearings)
        result[field] = dict(sorted(counts.items()))
    return result


def _seeded_digest(seed: int, stratum: tuple[str, str], bearing_id: str) -> str:
    value = f"{seed}|{stratum[0]}|{stratum[1]}|{bearing_id}".encode()
    return hashlib.sha256(value).hexdigest()


def _read_labels(path: Path) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    labels = {row["bearing_id"].strip(): row for row in rows}
    if len(labels) != len(rows):
        raise ValueError("official labels contain duplicate bearing IDs")
    return labels


def _string_list(value: dict[str, Any], key: str) -> list[str]:
    items = value.get(key)
    if not isinstance(items, list) or not items:
        raise ValueError(f"split manifest has no {key} bearings")
    return [str(item) for item in items]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--split", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20260803)
    args = parser.parse_args()
    manifest = build_manifest(args.split, args.labels, seed=args.seed)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"wrote {len(manifest['folds'])} locked folds to {args.output}")


if __name__ == "__main__":
    main()
