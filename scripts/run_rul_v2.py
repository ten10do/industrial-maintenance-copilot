"""Run preregistered XJTU-SY V2 nested cross-bearing RUL experiments."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sklearn.ensemble import (
    ExtraTreesRegressor,
    GradientBoostingRegressor,
    HistGradientBoostingRegressor,
    RandomForestRegressor,
)
from sklearn.inspection import permutation_importance
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.ml.evaluation import evaluate_rul
from app.ml.v2_governance import (
    causal_ewma,
    rul_promotion,
    trajectory_metrics,
)
from app.ml.v2_research import (
    RulFamily,
    V2Dataset,
    grouped_condition_folds,
    rul_fold_matrices,
)

SEED = 20260803
FAMILIES: tuple[RulFamily, ...] = ("R0", "R1", "R2", "R3")


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
    parser.add_argument("--outer-manifest", type=Path, required=True)
    parser.add_argument("--runs-dir", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--jobs", type=int, default=4)
    args = parser.parse_args()
    dataset = V2Dataset.load(args.processed, expected_dataset="xjtu-sy")
    unique_groups = sorted(set(dataset.groups.tolist()))
    if len(unique_groups) != 15:
        raise ValueError("XJTU V2 requires all 15 Development bearings")
    outer_manifest = _read_json(args.outer_manifest)
    if outer_manifest.get("source_processed_sha256") != dataset.processed_sha256:
        raise ValueError("XJTU outer manifest does not match the processed dataset")
    outer_folds = _outer_folds(dataset, outer_manifest)
    git_sha = _git_sha()
    args.runs_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict[str, Any]] = []
    for family in FAMILIES:
        output = args.runs_dir / f"rul-{family.lower()}-grouped-5fold.json"
        existing = _resumable_result(output, git_sha, dataset)
        if existing is not None:
            print(f"resume {family}")
            results.append(existing)
            continue
        print(f"run {family} grouped five-fold outer CV")
        result = _evaluate_family(
            dataset,
            family,
            outer_folds,
            args.outer_manifest,
            git_sha,
            args.jobs,
        )
        output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        results.append(result)
    selected = _select(results)
    summary = {
        "research_scope": "XJTU-SY 15-bearing Development Dataset",
        "evaluation_name": "Cross-Bearing Generalization Estimate",
        "unbiased_final_test": False,
        "protocol": "fixed condition-balanced 5-fold grouped outer; grouped 3-fold inner",
        "outer_manifest": args.outer_manifest.as_posix(),
        "dataset_version": dataset.dataset_version,
        "feature_version": "bearing-features-v2",
        "processed_sha256": dataset.processed_sha256,
        "config_sha": dataset.config_sha,
        "git_sha": git_sha,
        "selected": selected,
        "families": results,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(_markdown(summary), encoding="utf-8")
    print(f"selected {selected['family']}; promotion={selected['promotion']['passed']}")


def _evaluate_family(
    dataset: V2Dataset,
    family: RulFamily,
    outer_folds: list[tuple[str, NDArray[np.int_], NDArray[np.int_]]],
    outer_manifest_path: Path,
    git_sha: str,
    jobs: int,
) -> dict[str, Any]:
    started_at = datetime.now(UTC).isoformat()
    targets = np.asarray(dataset.targets, dtype=np.float64)
    oof = np.full(len(targets), np.nan, dtype=np.float64)
    lower = np.full(len(targets), np.nan, dtype=np.float64)
    upper = np.full(len(targets), np.nan, dtype=np.float64)
    outer_records: list[dict[str, Any]] = []
    importance_records: list[dict[str, float]] = []
    local_records: list[dict[str, Any]] = []
    candidates = _candidates()
    for outer_number, (fold_id, outer_train, outer_validation) in enumerate(
        outer_folds, start=1
    ):
        held_out = sorted(set(dataset.groups[outer_validation].tolist()))
        print(f"  {family} outer {outer_number}/5 held-out={held_out}")
        inner_relative = grouped_condition_folds(
            dataset.groups[outer_train], dataset.conditions[outer_train]
        )
        candidate_scores = []
        for candidate in candidates:
            metrics = []
            for inner_train_relative, inner_validation_relative in inner_relative:
                inner_train = outer_train[inner_train_relative]
                inner_validation = outer_train[inner_validation_relative]
                train, validation, _ = rul_fold_matrices(
                    dataset, family, inner_train, inner_validation
                )
                scaler = StandardScaler().fit(train)
                estimator = _regressor(candidate, jobs)
                estimator.fit(scaler.transform(train), targets[inner_train])
                prediction = np.asarray(
                    estimator.predict(scaler.transform(validation)), dtype=np.float64
                )
                metrics.append(evaluate_rul(targets[inner_validation], prediction))
            candidate_scores.append(
                {
                    "candidate": candidate,
                    "mean_mae": float(np.mean([item["mae"] for item in metrics])),
                    "mean_rmse": float(np.mean([item["rmse"] for item in metrics])),
                    "mean_late_error": float(
                        np.mean([item["late_prediction_error"] for item in metrics])
                    ),
                }
            )
        selected_score = min(
            candidate_scores,
            key=lambda item: (
                item["mean_mae"],
                item["mean_rmse"],
                item["mean_late_error"],
                _complexity(item["candidate"].algorithm),
            ),
        )
        selected_candidate = selected_score["candidate"]
        train, validation, feature_names = rul_fold_matrices(
            dataset, family, outer_train, outer_validation
        )
        scaler = StandardScaler().fit(train)
        estimator = _regressor(selected_candidate, jobs)
        transformed_train = scaler.transform(train)
        transformed_validation = scaler.transform(validation)
        estimator.fit(transformed_train, targets[outer_train])
        prediction = np.asarray(
            estimator.predict(transformed_validation), dtype=np.float64
        )
        oof[outer_validation] = prediction
        interval = _tree_interval(estimator, transformed_validation)
        if interval is not None:
            lower[outer_validation], upper[outer_validation] = interval
        stride = max(1, len(outer_validation) // 1_000)
        importance_positions = np.arange(0, len(outer_validation), stride)[:1_000]
        importance = permutation_importance(
            estimator,
            transformed_validation[importance_positions],
            targets[outer_validation[importance_positions]],
            scoring="neg_mean_absolute_error",
            n_repeats=3,
            random_state=SEED,
            n_jobs=jobs,
        )
        importance_records.append(
            {
                name: float(value)
                for name, value in zip(
                    feature_names, importance.importances_mean, strict=True
                )
            }
        )
        local_records.append(
            _local_contributors(
                estimator, transformed_validation[0], feature_names, ",".join(held_out)
            )
        )
        outer_records.append(
            {
                "fold_id": fold_id,
                "held_out_bearings": held_out,
                "selected_algorithm": selected_candidate.algorithm,
                "selected_hyperparameters": selected_candidate.hyperparameters,
                "inner_selected_metrics": {
                    key: value
                    for key, value in selected_score.items()
                    if key != "candidate"
                },
                "outer_metrics": evaluate_rul(targets[outer_validation], prediction),
                "inner_candidates": [
                    {
                        "algorithm": item["candidate"].algorithm,
                        "hyperparameters": item["candidate"].hyperparameters,
                        "mean_mae": item["mean_mae"],
                        "mean_rmse": item["mean_rmse"],
                        "mean_late_error": item["mean_late_error"],
                    }
                    for item in candidate_scores
                ],
            }
        )
    if not np.isfinite(oof).all():
        raise ValueError("grouped outer CV did not predict every XJTU row exactly once")
    raw_metrics = evaluate_rul(targets, oof)
    raw_trajectories = _prediction_trajectories(dataset, oof)
    raw_stability = trajectory_metrics(raw_trajectories)
    raw_metrics.update(
        {key: value for key, value in raw_stability.items() if key != "per_bearing"}
    )
    smoothed = np.empty_like(oof)
    for group in sorted(set(dataset.groups.tolist())):
        indices = np.flatnonzero(dataset.groups == group)
        indices = indices[np.argsort(dataset.sequence_indices[indices])]
        smoothed[indices] = causal_ewma(oof[indices])
    smoothed_metrics = evaluate_rul(targets, smoothed)
    smoothed_stability = trajectory_metrics(_prediction_trajectories(dataset, smoothed))
    smoothed_metrics.update(
        {
            key: value
            for key, value in smoothed_stability.items()
            if key != "per_bearing"
        }
    )
    uncertainty = _uncertainty_summary(targets, lower, upper)
    return {
        "experiment_id": f"rul-{family.lower()}-nested-grouped-5fold",
        "dataset_version": dataset.dataset_version,
        "processed_sha256": dataset.processed_sha256,
        "feature_version": "bearing-features-v2",
        "feature_family": family,
        "fold_manifest": outer_manifest_path.as_posix(),
        "algorithm": "nested candidate selection",
        "hyperparameters": "preregistered finite grids",
        "seed": SEED,
        "git_sha": git_sha,
        "started_at": started_at,
        "finished_at": datetime.now(UTC).isoformat(),
        "raw_metrics": raw_metrics,
        "smoothed_metrics": smoothed_metrics,
        "raw_per_bearing_trajectory": raw_stability["per_bearing"],
        "smoothed_per_bearing_trajectory": smoothed_stability["per_bearing"],
        "outer_folds": outer_records,
        "uncertainty": uncertainty,
        "explainability_scope": (
            "Development held-out folds; deterministic maximum 1000 rows/fold"
        ),
        "global_permutation_importance": _aggregate_importance(importance_records),
        "sample_level_contributors": local_records,
        "artifact_hash": hashlib.sha256(oof.tobytes()).hexdigest(),
        "promotion": rul_promotion(raw_metrics),
    }


def _prediction_trajectories(
    dataset: V2Dataset, predictions: NDArray[np.float64]
) -> dict[str, NDArray[np.float64]]:
    result = {}
    for group in sorted(set(dataset.groups.tolist())):
        indices = np.flatnonzero(dataset.groups == group)
        indices = indices[np.argsort(dataset.sequence_indices[indices])]
        result[group] = predictions[indices]
    return result


def _tree_interval(
    estimator: Any, features: NDArray[np.float64]
) -> tuple[NDArray[np.float64], NDArray[np.float64]] | None:
    trees = getattr(estimator, "estimators_", None)
    if trees is None or not isinstance(
        estimator, (RandomForestRegressor, ExtraTreesRegressor)
    ):
        return None
    predictions = np.vstack([tree.predict(features) for tree in trees])
    return (
        np.asarray(np.percentile(predictions, 10, axis=0), dtype=np.float64),
        np.asarray(np.percentile(predictions, 90, axis=0), dtype=np.float64),
    )


def _uncertainty_summary(
    targets: NDArray[np.float64],
    lower: NDArray[np.float64],
    upper: NDArray[np.float64],
) -> dict[str, Any]:
    available = np.isfinite(lower) & np.isfinite(upper)
    if not np.any(available):
        return {
            "status": "unavailable",
            "reason": "selected outer estimators did not expose tree-level dispersion",
        }
    return {
        "status": "partial empirical 10th/90th tree dispersion",
        "calibrated_probability_interval": False,
        "covered_rows": int(np.sum(available)),
        "coverage_fraction": float(np.mean(available)),
        "empirical_target_coverage": float(
            np.mean(
                (targets[available] >= lower[available])
                & (targets[available] <= upper[available])
            )
        ),
        "mean_interval_width_hours": float(
            np.mean(upper[available] - lower[available])
        ),
    }


def _aggregate_importance(records: list[dict[str, float]]) -> list[dict[str, float]]:
    names = sorted({name for record in records for name in record})
    result = [
        {
            "feature": name,
            "mean_importance": float(
                np.mean([record.get(name, 0.0) for record in records])
            ),
        }
        for name in names
    ]
    return sorted(result, key=lambda item: abs(item["mean_importance"]), reverse=True)


def _local_contributors(
    estimator: Any,
    features: NDArray[np.float64],
    feature_names: tuple[str, ...],
    bearing_id: str,
) -> dict[str, Any]:
    coefficient = getattr(estimator, "coef_", None)
    if coefficient is None:
        return {
            "bearing_id": bearing_id,
            "status": "unavailable",
            "reason": "selected estimator has no reliable native linear attribution",
        }
    contributions = np.asarray(coefficient).reshape(-1) * features
    order = np.argsort(np.abs(contributions))[::-1][:10]
    return {
        "bearing_id": bearing_id,
        "status": "linear scaled_feature_x_coefficient",
        "top_contributors": [
            {
                "feature": feature_names[index],
                "contribution": float(contributions[index]),
            }
            for index in order
        ],
    }


def _regressor(candidate: Candidate, jobs: int) -> Any:
    parameters = dict(candidate.hyperparameters)
    if candidate.algorithm == "ridge":
        return Ridge(**parameters)
    if candidate.algorithm == "random_forest":
        return RandomForestRegressor(**parameters, random_state=SEED, n_jobs=jobs)
    if candidate.algorithm == "extra_trees":
        return ExtraTreesRegressor(**parameters, random_state=SEED, n_jobs=jobs)
    if candidate.algorithm == "gradient_boosting":
        return GradientBoostingRegressor(**parameters, random_state=SEED)
    if candidate.algorithm == "hist_gradient_boosting":
        return HistGradientBoostingRegressor(**parameters, random_state=SEED)
    raise ValueError(f"unsupported RUL algorithm: {candidate.algorithm}")


def _candidates() -> list[Candidate]:
    candidates = [Candidate("ridge", {"alpha": alpha}) for alpha in (0.1, 1.0)]
    candidates.extend(
        Candidate(
            algorithm,
            {
                "n_estimators": 300,
                "max_depth": depth,
                "min_samples_leaf": leaf,
            },
        )
        for algorithm, depth, leaf in (
            ("random_forest", 8, 3),
            ("random_forest", 12, 1),
            ("extra_trees", 8, 3),
            ("extra_trees", 12, 1),
        )
    )
    candidates.extend(
        [
            Candidate(
                "gradient_boosting",
                {
                    "n_estimators": 100,
                    "learning_rate": 0.05,
                    "max_depth": 2,
                },
            ),
            Candidate(
                "gradient_boosting",
                {
                    "n_estimators": 200,
                    "learning_rate": 0.03,
                    "max_depth": 2,
                },
            ),
            Candidate(
                "hist_gradient_boosting",
                {
                    "max_iter": 150,
                    "learning_rate": 0.03,
                    "max_leaf_nodes": 15,
                    "l2_regularization": 0.0,
                },
            ),
            Candidate(
                "hist_gradient_boosting",
                {
                    "max_iter": 150,
                    "learning_rate": 0.05,
                    "max_leaf_nodes": 31,
                    "l2_regularization": 1.0,
                },
            ),
        ]
    )
    return candidates


def _select(results: list[dict[str, Any]]) -> dict[str, Any]:
    eligible = [item for item in results if item["promotion"]["passed"]]
    pool = eligible or results
    selected = min(
        pool,
        key=lambda item: (
            item["raw_metrics"]["mae"],
            item["raw_metrics"]["rmse"],
            item["raw_metrics"]["late_prediction_error"],
            item["raw_metrics"]["mean_per_bearing_oscillation_rate"],
            int(item["feature_family"][1:]),
        ),
    )
    return {
        "selection_pool": "gate-passing families" if eligible else "best failed family",
        "family": selected["feature_family"],
        "raw_metrics": selected["raw_metrics"],
        "smoothed_metrics": selected["smoothed_metrics"],
        "promotion": selected["promotion"],
        "uncertainty": selected["uncertainty"],
        "explainability_scope": selected.get(
            "explainability_scope", "all Development held-out rows/fold"
        ),
        "global_permutation_importance": selected["global_permutation_importance"][:20],
        "experiment_id": selected["experiment_id"],
    }


def _outer_folds(
    dataset: V2Dataset, manifest: dict[str, Any]
) -> list[tuple[str, NDArray[np.int_], NDArray[np.int_]]]:
    result = []
    seen: list[str] = []
    for fold in manifest["folds"]:
        train = np.flatnonzero(np.isin(dataset.groups, fold["train"]))
        validation = np.flatnonzero(np.isin(dataset.groups, fold["validation"]))
        train_groups = set(dataset.groups[train].tolist())
        validation_groups = set(dataset.groups[validation].tolist())
        if train_groups & validation_groups:
            raise ValueError("bearing leakage in fixed XJTU outer fold")
        if train_groups | validation_groups != set(dataset.groups.tolist()):
            raise ValueError("XJTU outer fold does not partition all bearings")
        seen.extend(validation_groups)
        result.append((str(fold["fold_id"]), train, validation))
    if len(result) != 5 or sorted(seen) != sorted(set(dataset.groups.tolist())):
        raise ValueError("each XJTU bearing must be outer validation exactly once")
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
    return {
        "ridge": 0,
        "gradient_boosting": 1,
        "random_forest": 2,
        "extra_trees": 3,
        "hist_gradient_boosting": 4,
    }[algorithm]


def _markdown(summary: dict[str, Any]) -> str:
    selected = summary["selected"]
    raw = selected["raw_metrics"]
    smoothed = selected["smoothed_metrics"]
    lines = [
        "# XJTU-SY RUL V2 Cross-Bearing Generalization Estimate",
        "",
        "This is a 15-bearing Development estimate, not an unbiased final test.",
        "",
        f"- Protocol: {summary['protocol']}",
        f"- Dataset / feature: `{summary['dataset_version']}` / `bearing-features-v2`",
        f"- Git SHA: `{summary['git_sha']}`",
        f"- Selected family: **{selected['family']}** ({selected['selection_pool']})",
        "",
        "## Raw trajectory (promotion basis)",
        "",
        f"- MAE / RMSE: **{raw['mae']:.4f} h** / {raw['rmse']:.4f} h",
        f"- R²: **{raw['r2']:.4f}**",
        f"- Mean late error: {raw['late_prediction_error']:.4f} h",
        (
            f"- Oscillation count / mean bearing rate: {raw['oscillation_count']} / "
            f"{raw['mean_per_bearing_oscillation_rate']:.4f}"
        ),
        (
            f"- Mean / max positive jump: {raw['mean_positive_jump']:.4f} h / "
            f"{raw['max_positive_jump']:.4f} h"
        ),
        "",
        "## Causal EWMA (alpha=0.20; supplemental only)",
        "",
        f"- MAE / RMSE: {smoothed['mae']:.4f} h / {smoothed['rmse']:.4f} h",
        f"- R²: {smoothed['r2']:.4f}",
        (
            f"- Oscillation count / mean bearing rate: {smoothed['oscillation_count']} / "
            f"{smoothed['mean_per_bearing_oscillation_rate']:.4f}"
        ),
        "",
        f"Promotion: **{'PASS' if selected['promotion']['passed'] else 'REJECTED'}**",
        f"Uncertainty: `{selected['uncertainty']}`",
        "",
    ]
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
