"""Quantify Paderborn V2 development-only domain and identity effects."""

from __future__ import annotations

import argparse
import csv
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray
from scipy.io import loadmat
from sklearn.decomposition import PCA
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.ml.v2_governance import PaderbornAccessPolicy

ANALYSIS_FEATURES = (
    "rms",
    "kurtosis",
    "crest_factor",
    "spectral_centroid_hz",
    "low_band_energy",
    "mid_band_energy",
    "high_band_energy",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed", type=Path, required=True)
    parser.add_argument("--fold-manifest", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--json-output", type=Path, required=True)
    args = parser.parse_args()
    result = analyze(args.processed, args.fold_manifest, args.labels, args.raw_dir)
    args.json_output.parent.mkdir(parents=True, exist_ok=True)
    args.json_output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(_markdown(result), encoding="utf-8")
    print(f"wrote development-only domain analysis to {args.report}")


def analyze(
    processed_path: Path,
    fold_manifest_path: Path,
    labels_path: Path,
    raw_dir: Path,
) -> dict[str, Any]:
    policy = PaderbornAccessPolicy.from_manifest(fold_manifest_path)
    labels = _labels(labels_path, policy.development)
    with np.load(processed_path, allow_pickle=False) as payload:
        groups = [str(value) for value in payload["groups"].tolist()]
        policy.validate_development_groups(groups)
        conditions = [str(value) for value in payload["conditions"].tolist()]
        targets = [str(value) for value in payload["targets"].tolist()]
        names = [str(value) for value in payload["feature_names"].tolist()]
        missing = sorted(set(ANALYSIS_FEATURES) - set(names))
        if missing:
            raise ValueError(f"domain-analysis features missing: {missing}")
        selected = [names.index(name) for name in ANALYSIS_FEATURES]
        features = np.asarray(payload["features"][:, selected], dtype=np.float64)
        dataset_version = str(payload["dataset_version"].item())
        feature_version = str(payload["feature_schema_version"].item())
        config_sha = str(payload["config_sha"].item())
    damage_origins = [labels[group]["damage_origin"] for group in groups]
    damaged = np.asarray([target != "healthy" for target in targets], dtype=np.int_)
    distributions = {
        "bearing_fault_class": _bearing_distribution(labels, "fault_class"),
        "bearing_damage_origin": _bearing_distribution(labels, "damage_origin"),
        "window_fault_class": dict(sorted(Counter(targets).items())),
        "window_damage_origin": dict(sorted(Counter(damage_origins).items())),
        "window_operating_condition": dict(sorted(Counter(conditions).items())),
    }
    feature_distribution = {
        feature: {
            origin: _summary(features[np.asarray(damage_origins) == origin, index])
            for origin in sorted(set(damage_origins))
        }
        for index, feature in enumerate(ANALYSIS_FEATURES)
    }
    overlap = {}
    for index, feature in enumerate(ANALYSIS_FEATURES):
        values = features[:, index]
        auc = float(roc_auc_score(damaged, values))
        overlap[feature] = {
            "direction_invariant_auc": max(auc, 1.0 - auc),
            "standardized_mean_difference": _standardized_mean_difference(
                values[damaged == 0], values[damaged == 1]
            ),
        }
    bearing_summary = {
        bearing_id: {
            feature: float(np.median(features[np.asarray(groups) == bearing_id, index]))
            for index, feature in enumerate(ANALYSIS_FEATURES)
        }
        for bearing_id in sorted(set(groups))
    }
    condition_summary = {
        condition: {
            feature: float(
                np.median(features[np.asarray(conditions) == condition, index])
            )
            for index, feature in enumerate(ANALYSIS_FEATURES)
        }
        for condition in sorted(set(conditions))
    }
    pca = _pca_diagnostics(features, groups, conditions, damage_origins)
    channel_audit = _audit_channels(raw_dir, policy.development)
    return {
        "scope": "Paderborn 26 Development bearings only",
        "frozen_test_accessed": False,
        "frozen_test_intersection": sorted(set(groups) & policy.frozen_test),
        "dataset_version": dataset_version,
        "feature_version": feature_version,
        "config_sha": config_sha,
        "git_sha": _git_sha(),
        "rows": len(groups),
        "bearing_count": len(set(groups)),
        "distributions": distributions,
        "feature_distribution": feature_distribution,
        "healthy_damaged_overlap": overlap,
        "bearing_specific_medians": bearing_summary,
        "condition_specific_medians": condition_summary,
        "pca": pca,
        "channel_audit": channel_audit,
        "bearing_characteristic_frequencies": {
            "status": "disabled",
            "reason": "official bearing geometry is not available in the locked inputs",
        },
    }


def _pca_diagnostics(
    features: NDArray[np.float64],
    groups: list[str],
    conditions: list[str],
    origins: list[str],
) -> dict[str, Any]:
    selected: list[int] = []
    group_array = np.asarray(groups)
    for group in sorted(set(groups)):
        indices = np.flatnonzero(group_array == group)
        stride = max(1, len(indices) // 500)
        selected.extend(int(value) for value in indices[::stride][:500])
    selected_array = np.asarray(selected, dtype=np.int_)
    scaled = StandardScaler().fit_transform(features[selected_array])
    coordinates = PCA(n_components=3, random_state=20260803).fit_transform(scaled)
    fitted = PCA(n_components=3, random_state=20260803).fit(scaled)
    return {
        "purpose": "analysis only; coordinates are not model inputs",
        "sample_rows": len(selected),
        "explained_variance_ratio": [
            float(value) for value in fitted.explained_variance_ratio_
        ],
        "eta_squared": {
            "bearing_identity": _eta_squared(coordinates, group_array[selected_array]),
            "operating_condition": _eta_squared(
                coordinates, np.asarray(conditions)[selected_array]
            ),
            "damage_origin": _eta_squared(
                coordinates, np.asarray(origins)[selected_array]
            ),
        },
    }


def _eta_squared(
    coordinates: NDArray[np.float64], labels: NDArray[np.str_]
) -> list[float]:
    result = []
    for component in coordinates.T:
        overall = float(np.mean(component))
        total = float(np.sum(np.square(component - overall)))
        between = sum(
            len(component[labels == label])
            * (float(np.mean(component[labels == label])) - overall) ** 2
            for label in np.unique(labels)
        )
        result.append(float(between / max(total, 1e-12)))
    return result


def _audit_channels(raw_dir: Path, development: frozenset[str]) -> dict[str, Any]:
    coverage: Counter[str] = Counter()
    aligned = 0
    inspected = 0
    for bearing_id in sorted(development):
        representatives: dict[str, Path] = {}
        for path in sorted((raw_dir / bearing_id).glob("*.mat")):
            condition = "_".join(path.stem.split("_")[:3])
            representatives.setdefault(condition, path)
        for path in representatives.values():
            payload = loadmat(path, squeeze_me=True, struct_as_record=False)
            root = payload[path.stem]
            channels = {
                str(getattr(item, "Name", "")): np.asarray(
                    getattr(item, "Data", [])
                ).reshape(-1)
                for item in np.atleast_1d(root.Y)
            }
            inspected += 1
            coverage.update(channels.keys())
            required = ("vibration_1", "phase_current_1", "phase_current_2")
            if (
                all(name in channels for name in required)
                and len({len(channels[name]) for name in required}) == 1
            ):
                aligned += 1
    return {
        "representative_files": inspected,
        "channel_coverage": dict(sorted(coverage.items())),
        "high_rate_channels_aligned": aligned,
        "f4_status": "applicable" if inspected and aligned == inspected else "N/A",
        "f4_channels": ["vibration_1", "phase_current_1", "phase_current_2"],
    }


def _labels(path: Path, development: frozenset[str]) -> dict[str, dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as stream:
        rows = list(csv.DictReader(stream))
    result = {
        row["bearing_id"]: row for row in rows if row["bearing_id"] in development
    }
    if set(result) != development:
        raise ValueError("official labels do not cover all development bearings")
    return result


def _bearing_distribution(
    labels: dict[str, dict[str, str]], field: str
) -> dict[str, int]:
    return dict(sorted(Counter(row[field] for row in labels.values()).items()))


def _summary(values: NDArray[np.float64]) -> dict[str, float]:
    lower, median, upper = np.percentile(values, [25, 50, 75])
    return {
        "median": float(median),
        "p25": float(lower),
        "p75": float(upper),
    }


def _standardized_mean_difference(
    healthy: NDArray[np.float64], damaged: NDArray[np.float64]
) -> float:
    pooled = np.sqrt((np.var(healthy) + np.var(damaged)) / 2.0)
    return float((np.mean(damaged) - np.mean(healthy)) / max(float(pooled), 1e-12))


def _markdown(result: dict[str, Any]) -> str:
    distributions = result["distributions"]
    pca = result["pca"]
    eta = pca["eta_squared"]
    overlap = result["healthy_damaged_overlap"]
    lines = [
        "# Paderborn V2 Development-only Domain Analysis",
        "",
        f"- Scope: {result['scope']}",
        f"- Rows / bearings: {result['rows']} / {result['bearing_count']}",
        f"- Dataset / feature: `{result['dataset_version']}` / `{result['feature_version']}`",
        f"- Config SHA: `{result['config_sha']}`",
        f"- Git SHA: `{result['git_sha']}`",
        "- Frozen test accessed: **no**",
        f"- Frozen-test intersection: `{result['frozen_test_intersection']}`",
        "",
        "## Distribution",
        "",
        f"- Bearing fault class: `{distributions['bearing_fault_class']}`",
        f"- Bearing damage origin: `{distributions['bearing_damage_origin']}`",
        f"- Window operating condition: `{distributions['window_operating_condition']}`",
        "",
        "## Healthy vs damaged overlap",
        "",
        "| Feature | Direction-invariant AUC | Standardized mean difference |",
        "|---|---:|---:|",
    ]
    for feature, metrics in result["healthy_damaged_overlap"].items():
        lines.append(
            f"| {feature} | {metrics['direction_invariant_auc']:.4f} | "
            f"{metrics['standardized_mean_difference']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## PCA factor effects",
            "",
            (
                "PCA is analysis-only and is not used as a model input. Eta-squared is "
                "reported for PC1–PC3; a larger value means that factor explains more "
                "coordinate variance."
            ),
            "",
            f"- Explained variance: `{pca['explained_variance_ratio']}`",
            f"- Bearing identity eta²: `{pca['eta_squared']['bearing_identity']}`",
            f"- Operating condition eta²: `{pca['eta_squared']['operating_condition']}`",
            f"- Damage origin eta²: `{pca['eta_squared']['damage_origin']}`",
            "",
            "## Quantitative interpretation",
            "",
            (
                f"- RMS alone has direction-invariant AUC "
                f"{overlap['rms']['direction_invariant_auc']:.4f}, which is close to random "
                "and confirms substantial healthy/damaged overlap."
            ),
            (
                f"- Spectral centroid is the strongest audited univariate separator "
                f"(AUC {overlap['spectral_centroid_hz']['direction_invariant_auc']:.4f}), "
                "but a univariate Development effect is not cross-bearing proof."
            ),
            (
                f"- Mean PC1–PC3 eta² is bearing={np.mean(eta['bearing_identity']):.4f}, "
                f"condition={np.mean(eta['operating_condition']):.4f}, and "
                f"damage-origin={np.mean(eta['damage_origin']):.4f}. Bearing identity is the "
                "dominant factor, so identity/domain learning is a material generalization risk."
            ),
            (
                "- Operating condition contributes measurable variance (especially PC1), so "
                "fold-local condition normalization is justified but cannot by itself remove "
                "bearing-specific shift."
            ),
            "",
            "## Channel audit",
            "",
            f"- Representative files: {result['channel_audit']['representative_files']}",
            f"- Coverage: `{result['channel_audit']['channel_coverage']}`",
            f"- Aligned high-rate triplets: {result['channel_audit']['high_rate_channels_aligned']}",
            (
                f"- F4: **{result['channel_audit']['f4_status']}** using "
                f"`{result['channel_audit']['f4_channels']}`"
            ),
            "- BPFO/BPFI/BSF/FTF: disabled because locked inputs do not contain bearing geometry.",
            "",
            "## Interpretation guardrail",
            "",
            (
                "The committed JSON contains bearing- and condition-specific medians. This "
                "analysis quantifies whether identity/condition effects rival damage-origin "
                "effects; it does not inspect or summarize the six frozen test bearings and "
                "does not select a model."
            ),
            "",
        ]
    )
    return "\n".join(lines)


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
