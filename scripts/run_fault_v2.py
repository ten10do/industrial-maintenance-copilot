"""Run preregistered Paderborn V2 grouped fault experiments."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.ml.v2_governance import PaderbornAccessPolicy, fault_promotion
from app.ml.v2_research import FaultFamily, V2Dataset, fault_fold_matrices

SEED = 20260803
FAMILIES: tuple[FaultFamily, ...] = ("F0", "F1", "F2", "F3", "F4")


@dataclass(frozen=True, slots=True)
class Candidate:
    algorithm: str
    hyperparameters: dict[str, Any]

    @property
    def candidate_id(self) -> str:
        value = json.dumps(
            {"algorithm": self.algorithm, "hyperparameters": self.hyperparameters},
            sort_keys=True,
            separators=(",", ":"),
        )
        return f"{self.algorithm}-{hashlib.sha256(value.encode()).hexdigest()[:10]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--fold-manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    dataset = V2Dataset.load(args.processed, expected_dataset="paderborn")
    policy = PaderbornAccessPolicy.from_manifest(args.fold_manifest)
    policy.validate_development_groups(dataset.groups.tolist())
    fold_manifest = _read_json(args.fold_manifest)
    folds = _fold_indices(dataset, fold_manifest)
    damaged = np.asarray(dataset.targets != "healthy", dtype=np.int_)
    git_sha = _git_sha()
    args.runs_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    candidates = _candidates()
    for family in FAMILIES:
        for number, candidate in enumerate(candidates, start=1):
            output = (
                args.runs_dir / f"fault-{family.lower()}-{candidate.candidate_id}.json"
            )
            existing = _resumable_result(output, git_sha, dataset)
            if existing is not None:
                print(
                    f"resume {family} {number}/{len(candidates)} {candidate.candidate_id}"
                )
                results.append(existing)
                continue
            print(f"run {family} {number}/{len(candidates)} {candidate.candidate_id}")
            result = _evaluate_candidate(
                dataset,
                family,
                candidate,
                folds,
                damaged,
                args.fold_manifest,
                git_sha,
                args.jobs,
            )
            output.write_text(
                json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            results.append(result)
    selected = _select(results)
    stage_two = _stage_two_evaluation(
        dataset,
        selected,
        folds,
        damaged,
        _labels(args.labels, policy.development),
        args.jobs,
    )
    summary = {
        "research_scope": "Paderborn 26 Development bearings only",
        "dataset_version": dataset.dataset_version,
        "feature_version": "bearing-features-v2",
        "processed_sha256": dataset.processed_sha256,
        "config_sha": dataset.config_sha,
        "fold_manifest": args.fold_manifest.as_posix(),
        "git_sha": git_sha,
        "frozen_test_accessed": False,
        "candidate_count": len(results),
        "selected": selected,
        "stage_two": stage_two,
        "all_candidates": results,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(_markdown(summary), encoding="utf-8")
    print(
        f"selected {selected['family']} {selected['algorithm']}; "
        f"promotion={selected['promotion']['passed']}; frozen test remains closed"
    )


def _evaluate_candidate(
    dataset: V2Dataset,
    family: FaultFamily,
    candidate: Candidate,
    folds: list[tuple[str, NDArray[np.int_], NDArray[np.int_]]],
    damaged: NDArray[np.int_],
    fold_manifest: Path,
    git_sha: str,
    jobs: int,
) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    oof_probability = np.full(len(damaged), np.nan, dtype=np.float64)
    fold_metrics: list[dict[str, Any]] = []
    feature_names: tuple[str, ...] = ()
    for fold_id, train_indices, validation_indices in folds:
        train, validation, feature_names = fault_fold_matrices(
            dataset, family, train_indices, validation_indices, damaged
        )
        scaler = StandardScaler().fit(train)
        estimator = _classifier(candidate, jobs)
        estimator.fit(scaler.transform(train), damaged[train_indices])
        probability = np.asarray(
            estimator.predict_proba(scaler.transform(validation))[:, 1],
            dtype=np.float64,
        )
        oof_probability[validation_indices] = probability
        metrics = _binary_metrics(damaged[validation_indices], probability)
        metrics["fold_id"] = fold_id
        metrics["validation_bearings"] = sorted(
            set(dataset.groups[validation_indices].tolist())
        )
        fold_metrics.append(metrics)
    if not np.isfinite(oof_probability).all():
        raise ValueError("fixed folds did not produce one OOF prediction per row")
    oof = _binary_metrics(damaged, oof_probability)
    recalls = np.asarray([item["macro_recall"] for item in fold_metrics])
    pr_aucs = np.asarray([item["pr_auc"] for item in fold_metrics])
    oof.update(
        {
            "mean_fold_macro_recall": float(np.mean(recalls)),
            "std_fold_macro_recall": float(np.std(recalls)),
            "worst_fold_macro_recall": float(np.min(recalls)),
            "mean_fold_pr_auc": float(np.mean(pr_aucs)),
            "std_fold_pr_auc": float(np.std(pr_aucs)),
            "stability_score": float(np.mean(recalls) - 0.5 * np.std(recalls)),
        }
    )
    return {
        "experiment_id": f"fault-{family.lower()}-{candidate.candidate_id}",
        "dataset_version": dataset.dataset_version,
        "processed_sha256": dataset.processed_sha256,
        "feature_version": "bearing-features-v2",
        "feature_family": family,
        "feature_count": len(feature_names),
        "feature_names": list(feature_names),
        "fold_manifest": fold_manifest.as_posix(),
        "algorithm": candidate.algorithm,
        "hyperparameters": candidate.hyperparameters,
        "seed": SEED,
        "git_sha": git_sha,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "metrics": oof,
        "fold_metrics": fold_metrics,
        "artifact_hash": hashlib.sha256(oof_probability.tobytes()).hexdigest(),
        "frozen_test_accessed": False,
        "promotion": fault_promotion(oof),
    }


def _stage_two_evaluation(
    dataset: V2Dataset,
    selected: dict[str, Any],
    folds: list[tuple[str, NDArray[np.int_], NDArray[np.int_]]],
    damaged: NDArray[np.int_],
    labels: dict[str, dict[str, str]],
    jobs: int,
) -> dict[str, Any]:
    origins = np.asarray([labels[group]["damage_origin"] for group in dataset.groups])
    bearing_counts = Counter(
        labels[group]["damage_origin"]
        for group in sorted(set(dataset.groups.tolist()))
        if labels[group]["damage_origin"] != "healthy"
    )
    eligible = bool(bearing_counts) and min(bearing_counts.values()) >= 5
    if not eligible:
        return {
            "status": "N/A",
            "target": "damage_origin",
            "bearing_counts": dict(sorted(bearing_counts.items())),
            "reason": "fewer than five Development bearings in a subtype",
        }
    family = selected["family"]
    candidate = Candidate(selected["algorithm"], selected["hyperparameters"])
    truth: list[int] = []
    probability: list[float] = []
    for _, train_indices, validation_indices in folds:
        train_indices = train_indices[damaged[train_indices] == 1]
        validation_indices = validation_indices[damaged[validation_indices] == 1]
        train, validation, _ = fault_fold_matrices(
            dataset, family, train_indices, validation_indices, damaged
        )
        target_train = np.asarray(origins[train_indices] == "real", dtype=np.int_)
        target_validation = np.asarray(
            origins[validation_indices] == "real", dtype=np.int_
        )
        scaler = StandardScaler().fit(train)
        estimator = _classifier(candidate, jobs)
        estimator.fit(scaler.transform(train), target_train)
        predicted = estimator.predict_proba(scaler.transform(validation))[:, 1]
        truth.extend(target_validation.tolist())
        probability.extend(float(value) for value in predicted)
    return {
        "status": "evaluated",
        "target": "damage_origin artificial vs real",
        "bearing_counts": dict(sorted(bearing_counts.items())),
        "metrics": _binary_metrics(
            np.asarray(truth, dtype=np.int_), np.asarray(probability, dtype=np.float64)
        ),
        "promotion_role": "none; Stage 1 remains the safety classifier",
    }


def _binary_metrics(
    truth: NDArray[np.int_], probability: NDArray[np.float64]
) -> dict[str, Any]:
    predicted = np.asarray(probability >= 0.50, dtype=np.int_)
    matrix = confusion_matrix(truth, predicted, labels=[0, 1])
    healthy_recall, damaged_recall = recall_score(
        truth, predicted, labels=[0, 1], average=None, zero_division=0
    )
    return {
        "macro_precision": float(
            precision_score(truth, predicted, average="macro", zero_division=0)
        ),
        "macro_recall": float(
            recall_score(truth, predicted, average="macro", zero_division=0)
        ),
        "macro_f1": float(f1_score(truth, predicted, average="macro", zero_division=0)),
        "roc_auc": float(roc_auc_score(truth, probability)),
        "pr_auc": float(average_precision_score(truth, probability)),
        "healthy_recall": float(healthy_recall),
        "damaged_recall": float(damaged_recall),
        "false_negative_rate": float(1.0 - damaged_recall),
        "false_positive_rate": float(1.0 - healthy_recall),
        "confusion_matrix": matrix.tolist(),
    }


def _select(results: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [item for item in results if item["promotion"]["passed"]]
    pool = eligible or results
    selected = max(
        pool,
        key=lambda item: (
            item["metrics"]["stability_score"],
            item["metrics"]["mean_fold_macro_recall"],
            item["metrics"]["worst_fold_macro_recall"],
            item["metrics"]["mean_fold_pr_auc"],
            -item["feature_count"],
            -_complexity(item["algorithm"]),
        ),
    )
    return {
        "selection_pool": "gate-passing candidates"
        if eligible
        else "best failed candidate",
        "family": selected["feature_family"],
        "algorithm": selected["algorithm"],
        "hyperparameters": selected["hyperparameters"],
        "feature_count": selected["feature_count"],
        "metrics": selected["metrics"],
        "promotion": selected["promotion"],
        "experiment_id": selected["experiment_id"],
    }


def _classifier(candidate: Candidate, jobs: int) -> Any:
    parameters = dict(candidate.hyperparameters)
    if candidate.algorithm == "logistic_regression":
        return LogisticRegression(**parameters, random_state=SEED, solver="lbfgs")
    if candidate.algorithm == "random_forest":
        return RandomForestClassifier(**parameters, random_state=SEED, n_jobs=jobs)
    if candidate.algorithm == "hist_gradient_boosting":
        return HistGradientBoostingClassifier(
            **parameters, random_state=SEED, class_weight="balanced"
        )
    raise ValueError(f"unsupported fault algorithm: {candidate.algorithm}")


def _candidates() -> list[Candidate]:
    candidates = [
        Candidate(
            "logistic_regression",
            {"C": value, "class_weight": "balanced", "max_iter": 2000},
        )
        for value in (0.1, 1.0, 10.0)
    ]
    candidates.extend(
        Candidate(
            "random_forest",
            {
                "n_estimators": 300,
                "max_depth": depth,
                "min_samples_leaf": leaf,
                "max_features": "sqrt",
                "class_weight": "balanced_subsample",
            },
        )
        for depth, leaf in ((8, 5), (12, 2), (None, 1))
    )
    candidates.extend(
        Candidate(
            "hist_gradient_boosting",
            {
                "max_iter": 150,
                "learning_rate": learning_rate,
                "max_leaf_nodes": leaves,
                "l2_regularization": regularization,
            },
        )
        for learning_rate, leaves, regularization in (
            (0.03, 15, 1.0),
            (0.05, 31, 1.0),
            (0.10, 15, 0.0),
            (0.10, 31, 0.0),
        )
    )
    return candidates


def _fold_indices(
    dataset: V2Dataset, manifest: dict[str, Any]
) -> list[tuple[str, NDArray[np.int_], NDArray[np.int_]]]:
    result = []
    for fold in manifest["folds"]:
        train = np.flatnonzero(np.isin(dataset.groups, fold["train"]))
        validation = np.flatnonzero(np.isin(dataset.groups, fold["validation"]))
        if set(dataset.groups[train]) & set(dataset.groups[validation]):
            raise ValueError("bearing leakage in fixed Paderborn fold")
        result.append((str(fold["fold_id"]), train, validation))
    return result


def _labels(path: Path, development: frozenset[str]) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result = {
        row["bearing_id"]: row for row in rows if row["bearing_id"] in development
    }
    if set(result) != development:
        raise ValueError("official labels do not cover all development bearings")
    return result


def _resumable_result(
    path: Path, git_sha: str, dataset: V2Dataset
) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    result = _read_json(path)
    result_sha = str(result.get("git_sha", ""))
    if result.get("processed_sha256") != dataset.processed_sha256 or not _is_ancestor(
        result_sha, git_sha
    ):
        raise ValueError(f"stale experiment result cannot be resumed: {path}")
    return result


def _complexity(algorithm: str) -> int:
    return {"logistic_regression": 0, "random_forest": 1, "hist_gradient_boosting": 2}[
        algorithm
    ]


def _markdown(summary: dict[str, Any]) -> str:
    selected = summary["selected"]
    metrics = selected["metrics"]
    lines = [
        "# Paderborn Fault V2 Grouped Development Results",
        "",
        "- Scope: 26 Development bearings; six Frozen Test bearings remain closed.",
        f"- Dataset / feature: `{summary['dataset_version']}` / `bearing-features-v2`",
        f"- Git SHA: `{summary['git_sha']}`",
        f"- Candidates: {summary['candidate_count']} across F0–F4 and five fixed folds",
        "- Classification threshold: 0.50",
        "",
        "## Selected Development candidate",
        "",
        f"- Selection pool: {selected['selection_pool']}",
        f"- Family / algorithm: **{selected['family']} / {selected['algorithm']}**",
        f"- Hyperparameters: `{selected['hyperparameters']}`",
        f"- OOF macro recall: **{metrics['macro_recall']:.4f}**",
        f"- OOF healthy recall: **{metrics['healthy_recall']:.4f}**",
        f"- OOF damaged recall: {metrics['damaged_recall']:.4f}",
        f"- OOF PR-AUC: {metrics['pr_auc']:.4f}",
        (
            f"- Fold macro recall: {metrics['mean_fold_macro_recall']:.4f} ± "
            f"{metrics['std_fold_macro_recall']:.4f}; worst "
            f"{metrics['worst_fold_macro_recall']:.4f}"
        ),
        f"- Promotion gate: **{'PASS' if selected['promotion']['passed'] else 'REJECTED'}**",
        "",
        "## Hierarchical result",
        "",
        f"`{summary['stage_two']}`",
        "",
        "## Frozen-test decision",
        "",
    ]
    if selected["promotion"]["passed"]:
        lines.append(
            "Development gates passed. Freeze and commit a final config before any one-time test access."
        )
    else:
        lines.append(
            "Development gates did not both pass. No final config is created and Frozen Test remains unaccessed."
        )
    lines.append("")
    return "\n".join(lines)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def _git_sha() -> str:
    return subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _is_ancestor(ancestor: str, descendant: str) -> bool:
    if len(ancestor) != 40 or len(descendant) != 40:
        return False
    return (
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", ancestor, descendant],
            cwd=REPO_ROOT,
            check=False,
        ).returncode
        == 0
    )


if __name__ == "__main__":
    main()
