"""Leakage-resistant bearing-features-v2 research primitives."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
from numpy.typing import NDArray
from scipy.signal import hilbert
from scipy.stats import kurtosis, skew

FEATURE_SCHEMA_VERSION_V2 = "bearing-features-v2"
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


def extract_envelope_features(
    signal: Sequence[float] | NDArray[np.float64], sampling_rate_hz: float
) -> dict[str, float]:
    values = _validated_signal(signal)
    envelope = np.abs(hilbert(values))
    power, frequencies = _spectrum(envelope, sampling_rate_hz)
    total = float(np.sum(power))
    ratios, energies = _three_bands(power, frequencies, sampling_rate_hz)
    distribution = power / max(total, _EPSILON)
    nonzero = distribution > 0
    result = {
        "envelope_rms": float(np.sqrt(np.mean(np.square(envelope)))),
        "envelope_kurtosis": _finite(
            float(kurtosis(envelope, fisher=False, bias=False))
        ),
        "envelope_peak": float(np.max(envelope)),
        "envelope_energy": float(np.mean(np.square(envelope))),
        "envelope_spectral_entropy": float(
            -np.sum(distribution[nonzero] * np.log2(distribution[nonzero]))
        ),
    }
    for name, value in zip(("low", "mid", "high"), energies, strict=True):
        result[f"envelope_{name}_band_energy"] = value
    for name, value in zip(("low", "mid", "high"), ratios, strict=True):
        result[f"envelope_{name}_energy_ratio"] = value
    return result


def extract_spectral_features_v2(
    signal: Sequence[float] | NDArray[np.float64], sampling_rate_hz: float
) -> dict[str, float]:
    values = _validated_signal(signal)
    power, frequencies = _spectrum(values, sampling_rate_hz)
    total = float(np.sum(power))
    ratios, energies = _three_bands(power, frequencies, sampling_rate_hz)
    amplitudes = np.sqrt(power)
    peak_index = int(np.argmax(power))
    peak_frequency = float(frequencies[peak_index])
    sorted_power = np.sort(power)
    concentrated = float(np.sum(sorted_power[-min(5, len(sorted_power)) :]))
    result = {
        "spectral_kurtosis_v2": _finite(
            float(kurtosis(amplitudes, fisher=False, bias=False))
        ),
        "spectral_skewness_v2": _finite(float(skew(amplitudes, bias=False))),
        "dominant_peak_energy_ratio": float(power[peak_index] / max(total, _EPSILON)),
        "energy_concentration_top5": concentrated / max(total, _EPSILON),
        "second_harmonic_energy_ratio": _harmonic_ratio(
            power, frequencies, peak_frequency, 2.0
        ),
        "third_harmonic_energy_ratio": _harmonic_ratio(
            power, frequencies, peak_frequency, 3.0
        ),
    }
    for name, energy, ratio in zip(
        ("low", "mid", "high"), energies, ratios, strict=True
    ):
        mask = _band_mask(frequencies, sampling_rate_hz, name)
        band_amplitude = amplitudes[mask]
        result[f"{name}_band_rms_v2"] = float(
            np.sqrt(np.mean(np.square(band_amplitude)))
        )
        result[f"{name}_band_kurtosis_v2"] = (
            _finite(float(kurtosis(band_amplitude, fisher=False, bias=False)))
            if len(band_amplitude) >= 4
            else 0.0
        )
        result[f"{name}_band_energy_v2"] = energy
        result[f"{name}_band_energy_ratio_v2"] = ratio
    return result


def extract_dual_channel_features(
    horizontal: Sequence[float] | NDArray[np.float64],
    vertical: Sequence[float] | NDArray[np.float64],
    sampling_rate_hz: float,
    *,
    first_name: str = "horizontal",
    second_name: str = "vertical",
    cross_prefix: str = "cross",
) -> dict[str, float]:
    horizontal_values = _validated_signal(horizontal)
    vertical_values = _validated_signal(vertical)
    if horizontal_values.shape != vertical_values.shape:
        raise ValueError("horizontal and vertical channels must align")
    horizontal_features = _channel_features(horizontal_values, sampling_rate_hz)
    vertical_features = _channel_features(vertical_values, sampling_rate_hz)
    if not first_name or not second_name or not cross_prefix:
        raise ValueError("channel feature prefixes must be non-empty")
    result = {
        f"{first_name}_{name}": value for name, value in horizontal_features.items()
    }
    result.update(
        {f"{second_name}_{name}": value for name, value in vertical_features.items()}
    )
    horizontal_energy = float(np.mean(np.square(horizontal_values)))
    vertical_energy = float(np.mean(np.square(vertical_values)))
    result.update(
        {
            f"{cross_prefix}_rms_ratio_first_over_second": horizontal_features["rms"]
            / max(vertical_features["rms"], _EPSILON),
            f"{cross_prefix}_energy_ratio_first_over_second": horizontal_energy
            / max(vertical_energy, _EPSILON),
            f"{cross_prefix}_kurtosis_ratio_first_over_second": horizontal_features[
                "kurtosis"
            ]
            / max(abs(vertical_features["kurtosis"]), _EPSILON),
            f"{cross_prefix}_spectral_energy_ratio_first_over_second": horizontal_features[
                "spectral_energy"
            ]
            / max(vertical_features["spectral_energy"], _EPSILON),
            f"{cross_prefix}_channel_correlation": _finite(
                float(np.corrcoef(horizontal_values, vertical_values)[0, 1])
            ),
        }
    )
    if not all(math.isfinite(value) for value in result.values()):
        raise ValueError("dual-channel extraction produced non-finite values")
    return result


@dataclass(frozen=True, slots=True)
class ConditionBaseline:
    """Fold-local healthy median/IQR baseline."""

    by_condition: Mapping[str, Mapping[str, tuple[float, float]]]
    pooled: Mapping[str, tuple[float, float]]
    feature_names: tuple[str, ...]

    @classmethod
    def fit(
        cls,
        rows: Sequence[Mapping[str, float]],
        conditions: Sequence[str],
        damaged: Sequence[bool],
        *,
        feature_names: Sequence[str] = _CONDITION_FEATURES,
    ) -> ConditionBaseline:
        if not (len(rows) == len(conditions) == len(damaged)) or not rows:
            raise ValueError("baseline inputs must be non-empty and aligned")
        selected_names = tuple(name for name in feature_names if name in rows[0])
        if not selected_names:
            raise ValueError("no condition-normalized features are available")
        healthy_indices = [index for index, value in enumerate(damaged) if not value]
        if not healthy_indices:
            raise ValueError("train fold has no healthy samples for condition baseline")
        pooled = _baseline_stats(rows, healthy_indices, selected_names)
        by_condition: dict[str, Mapping[str, tuple[float, float]]] = {}
        for condition in sorted(set(conditions)):
            indices = [
                index for index in healthy_indices if conditions[index] == condition
            ]
            if indices:
                by_condition[condition] = _baseline_stats(rows, indices, selected_names)
        return cls(by_condition, pooled, selected_names)

    def transform(
        self, rows: Sequence[Mapping[str, float]], conditions: Sequence[str]
    ) -> list[dict[str, float]]:
        if len(rows) != len(conditions):
            raise ValueError("rows and conditions must align")
        transformed = []
        for row, condition in zip(rows, conditions, strict=True):
            baseline = self.by_condition.get(condition, self.pooled)
            transformed.append(
                {
                    f"condition_normalized_{name}": (
                        float(row[name]) - baseline[name][0]
                    )
                    / max(baseline[name][1], _EPSILON)
                    for name in self.feature_names
                }
            )
        return transformed


def causal_multiscale_context(
    rows: Sequence[Mapping[str, float]],
    *,
    horizons: Sequence[int] = (5, 15, 30, 60),
    feature_names: Sequence[str] = (
        "horizontal_rms",
        "horizontal_kurtosis",
        "horizontal_envelope_energy",
        "horizontal_spectral_entropy",
        "horizontal_spectral_energy",
    ),
) -> list[dict[str, float]]:
    if not rows:
        return []
    available = tuple(name for name in feature_names if name in rows[0])
    if not available:
        raise ValueError("no causal context features are available")
    result: list[dict[str, float]] = []
    for index, row in enumerate(rows):
        context: dict[str, float] = {}
        for name in available:
            values = np.asarray([float(item[name]) for item in rows[: index + 1]])
            context[f"{name}_lag_0m"] = float(row[name])
            for horizon in horizons:
                start = max(0, index - horizon)
                window = values[start : index + 1]
                lag_index = max(0, index - horizon)
                prefix = f"{name}_causal_{horizon}m"
                context[f"{name}_lag_{horizon}m"] = float(values[lag_index])
                context[f"{prefix}_mean"] = float(np.mean(window))
                context[f"{prefix}_std"] = float(np.std(window))
                context[f"{prefix}_rms"] = float(np.sqrt(np.mean(np.square(window))))
                context[f"{prefix}_slope"] = _slope(window)
        result.append(context)
    return result


@dataclass(frozen=True, slots=True)
class FoldLocalDegradationIndicator:
    median: NDArray[np.float64]
    scale: NDArray[np.float64]
    feature_names: tuple[str, ...]

    @classmethod
    def fit(
        cls,
        rows: Sequence[Mapping[str, float]],
        groups: Sequence[str],
        indices: Sequence[int],
        *,
        feature_names: Sequence[str] = (
            "horizontal_rms",
            "vertical_rms",
            "horizontal_kurtosis",
            "vertical_kurtosis",
            "horizontal_envelope_energy",
            "vertical_envelope_energy",
        ),
    ) -> FoldLocalDegradationIndicator:
        if not (len(rows) == len(groups) == len(indices)) or not rows:
            raise ValueError("degradation inputs must be non-empty and aligned")
        available = tuple(name for name in feature_names if name in rows[0])
        if not available:
            raise ValueError("no degradation features are available")
        early_rows: list[Mapping[str, float]] = []
        for group in sorted(set(groups)):
            members = sorted(
                (index for index, value in enumerate(groups) if value == group),
                key=lambda index: indices[index],
            )
            early_count = min(len(members), max(5, math.ceil(len(members) * 0.10)))
            early_rows.extend(rows[index] for index in members[:early_count])
        matrix = np.asarray(
            [[float(row[name]) for name in available] for row in early_rows],
            dtype=np.float64,
        )
        median = np.median(matrix, axis=0)
        lower, upper = np.percentile(matrix, [25, 75], axis=0)
        scale = np.maximum(upper - lower, _EPSILON)
        return cls(median=median, scale=scale, feature_names=available)

    def transform(self, rows: Sequence[Mapping[str, float]]) -> NDArray[np.float64]:
        matrix = np.asarray(
            [[float(row[name]) for name in self.feature_names] for row in rows],
            dtype=np.float64,
        )
        normalized = (matrix - self.median) / self.scale
        return np.asarray(np.linalg.norm(normalized, axis=1), dtype=np.float64)


def _channel_features(
    values: NDArray[np.float64], sampling_rate_hz: float
) -> dict[str, float]:
    absolute = np.abs(values)
    rms = float(np.sqrt(np.mean(np.square(values))))
    power, frequencies = _spectrum(values, sampling_rate_hz)
    total = float(np.sum(power))
    distribution = power / max(total, _EPSILON)
    nonzero = distribution > 0
    bands, energies = _three_bands(power, frequencies, sampling_rate_hz)
    envelope = extract_envelope_features(values, sampling_rate_hz)
    result = {
        "rms": rms,
        "std": float(np.std(values)),
        "kurtosis": _finite(float(kurtosis(values, fisher=False, bias=False))),
        "crest_factor": float(np.max(absolute) / max(rms, _EPSILON)),
        "spectral_centroid_hz": float(
            np.sum(frequencies * power) / max(total, _EPSILON)
        ),
        "spectral_entropy": float(
            -np.sum(distribution[nonzero] * np.log2(distribution[nonzero]))
        ),
        "spectral_energy": total,
        "low_band_energy": energies[0],
        "mid_band_energy": energies[1],
        "high_band_energy": energies[2],
        "low_band_energy_ratio": bands[0],
        "mid_band_energy_ratio": bands[1],
        "high_band_energy_ratio": bands[2],
        "envelope_rms": envelope["envelope_rms"],
        "envelope_kurtosis": envelope["envelope_kurtosis"],
        "envelope_energy": envelope["envelope_energy"],
    }
    return result


def _baseline_stats(
    rows: Sequence[Mapping[str, float]],
    indices: Sequence[int],
    feature_names: Sequence[str],
) -> dict[str, tuple[float, float]]:
    matrix = np.asarray(
        [[float(rows[index][name]) for name in feature_names] for index in indices],
        dtype=np.float64,
    )
    lower, median, upper = np.percentile(matrix, [25, 50, 75], axis=0)
    return {
        name: (float(median[column]), float(upper[column] - lower[column]))
        for column, name in enumerate(feature_names)
    }


def _spectrum(
    values: NDArray[np.float64], sampling_rate_hz: float
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    if sampling_rate_hz <= 0:
        raise ValueError("sampling_rate_hz must be positive")
    centered = values - np.mean(values)
    power = np.asarray(np.square(np.abs(np.fft.rfft(centered))), dtype=np.float64)
    if len(power):
        power[0] = 0.0
    frequencies = np.asarray(
        np.fft.rfftfreq(len(centered), 1.0 / sampling_rate_hz), dtype=np.float64
    )
    return power, frequencies


def _three_bands(
    power: NDArray[np.float64],
    frequencies: NDArray[np.float64],
    sampling_rate_hz: float,
) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    energies = tuple(
        float(np.sum(power[_band_mask(frequencies, sampling_rate_hz, name)]))
        for name in ("low", "mid", "high")
    )
    total = max(sum(energies), _EPSILON)
    return tuple(value / total for value in energies), energies  # type: ignore[return-value]


def _band_mask(
    frequencies: NDArray[np.float64], sampling_rate_hz: float, name: str
) -> NDArray[np.bool_]:
    nyquist = sampling_rate_hz / 2.0
    bounds = {
        "low": (0.0, nyquist / 3.0),
        "mid": (nyquist / 3.0, 2.0 * nyquist / 3.0),
        "high": (2.0 * nyquist / 3.0, nyquist + 1.0),
    }
    start, end = bounds[name]
    return np.asarray((frequencies >= start) & (frequencies < end))


def _harmonic_ratio(
    power: NDArray[np.float64],
    frequencies: NDArray[np.float64],
    fundamental_hz: float,
    harmonic: float,
) -> float:
    if fundamental_hz <= 0 or harmonic * fundamental_hz > frequencies[-1]:
        return 0.0
    fundamental_index = int(np.argmin(np.abs(frequencies - fundamental_hz)))
    harmonic_index = int(np.argmin(np.abs(frequencies - harmonic * fundamental_hz)))
    return float(power[harmonic_index] / max(power[fundamental_index], _EPSILON))


def _validated_signal(
    signal: Sequence[float] | NDArray[np.float64],
) -> NDArray[np.float64]:
    values = np.asarray(signal, dtype=np.float64).reshape(-1)
    if len(values) < 8 or not np.isfinite(values).all():
        raise ValueError("signal must contain at least eight finite values")
    return values


def _slope(values: NDArray[np.float64]) -> float:
    if len(values) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(values), dtype=np.float64), values, 1)[0])


def _finite(value: float) -> float:
    return value if math.isfinite(value) else 0.0
