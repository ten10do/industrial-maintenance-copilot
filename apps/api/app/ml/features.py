"""Single feature implementation used for training and online inference."""

from __future__ import annotations

import math
from collections.abc import Sequence

import numpy as np
from numpy.typing import NDArray
from scipy.signal import hilbert
from scipy.stats import kurtosis, skew

from app.ml.types import FeatureDefinition, FeatureVector, TelemetryWindow
from app.ml.validation import validated_signal

FEATURE_SCHEMA_VERSION = "bearing-features-v1"
_EPSILON = 1e-12


def extract_features(
    window: TelemetryWindow,
    *,
    history: Sequence[FeatureVector] = (),
) -> FeatureVector:
    normalized, values, quality = validated_signal(window)
    absolute = np.abs(values)
    rms = float(np.sqrt(np.mean(np.square(values))))
    absolute_mean = float(np.mean(absolute))
    sqrt_abs_mean = float(np.mean(np.sqrt(absolute)))
    peak = float(np.max(absolute))
    values_map: dict[str, float] = {
        "mean": float(np.mean(values)),
        "std": float(np.std(values)),
        "variance": float(np.var(values)),
        "rms": rms,
        "max": float(np.max(values)),
        "min": float(np.min(values)),
        "peak_to_peak": float(np.ptp(values)),
        "absolute_mean": absolute_mean,
        "skewness": _finite(float(skew(values, bias=False))),
        "kurtosis": _finite(float(kurtosis(values, fisher=False, bias=False))),
        "crest_factor": peak / max(rms, _EPSILON),
        "shape_factor": rms / max(absolute_mean, _EPSILON),
        "impulse_factor": peak / max(absolute_mean, _EPSILON),
        "clearance_factor": peak / max(sqrt_abs_mean**2, _EPSILON),
    }
    values_map.update(_frequency_features(values, normalized.sampling_rate_hz))
    envelope_energy = float(np.mean(np.square(np.abs(hilbert(values)))))
    values_map["envelope_energy"] = envelope_energy
    values_map.update(_trend_features(values_map, history))
    for name, value in sorted(normalized.context.items()):
        values_map[f"context_{name}"] = float(value)
    if not all(math.isfinite(value) for value in values_map.values()):
        raise ValueError("feature extraction produced non-finite values")
    return FeatureVector(
        bearing_id=normalized.bearing_id,
        window_started_at=normalized.started_at,
        window_ended_at=normalized.ended_at,
        schema_version=FEATURE_SCHEMA_VERSION,
        values=values_map,
        operating_condition=normalized.operating_condition,
        quality_score=quality,
    )


def feature_definitions(
    context_names: Sequence[str] = (),
) -> tuple[FeatureDefinition, ...]:
    time_names = (
        "mean",
        "std",
        "variance",
        "rms",
        "max",
        "min",
        "peak_to_peak",
        "absolute_mean",
        "skewness",
        "kurtosis",
        "crest_factor",
        "shape_factor",
        "impulse_factor",
        "clearance_factor",
        "envelope_energy",
    )
    frequency_names = (
        "dominant_frequency_hz",
        "spectral_centroid_hz",
        "spectral_rms_hz",
        "spectral_entropy",
        "low_band_energy",
        "mid_band_energy",
        "high_band_energy",
        "low_energy_ratio",
        "mid_energy_ratio",
        "high_energy_ratio",
    )
    trend_names = (
        "rolling_mean",
        "rolling_std",
        "rolling_rms",
        "rms_slope",
        "kurtosis_slope",
        "envelope_energy_slope",
        "degradation_rate",
        "recent_vs_baseline_delta",
    )
    definitions = [
        FeatureDefinition(
            name, FEATURE_SCHEMA_VERSION, "derived", name.replace("_", " "), "time"
        )
        for name in time_names
    ]
    definitions.extend(
        FeatureDefinition(
            name, FEATURE_SCHEMA_VERSION, "derived", name.replace("_", " "), "frequency"
        )
        for name in frequency_names
    )
    definitions.extend(
        FeatureDefinition(
            name, FEATURE_SCHEMA_VERSION, "derived", name.replace("_", " "), "trend"
        )
        for name in trend_names
    )
    definitions.extend(
        FeatureDefinition(
            f"context_{name}", FEATURE_SCHEMA_VERSION, "dataset", name, "context"
        )
        for name in sorted(context_names)
    )
    return tuple(definitions)


def _frequency_features(
    values: NDArray[np.float64], sampling_rate_hz: float
) -> dict[str, float]:
    centered = values - np.mean(values)
    magnitudes = np.abs(np.fft.rfft(centered))
    frequencies = np.asarray(
        np.fft.rfftfreq(len(centered), d=1.0 / sampling_rate_hz), dtype=np.float64
    )
    power = np.asarray(np.square(magnitudes), dtype=np.float64)
    if len(power) > 0:
        power[0] = 0.0
    total = float(np.sum(power))
    distribution = power / max(total, _EPSILON)
    nonzero = distribution > 0
    nyquist = sampling_rate_hz / 2.0
    low = _band_energy(frequencies, power, 0.0, nyquist / 3.0)
    mid = _band_energy(frequencies, power, nyquist / 3.0, 2.0 * nyquist / 3.0)
    high = _band_energy(frequencies, power, 2.0 * nyquist / 3.0, nyquist + 1.0)
    return {
        "dominant_frequency_hz": float(frequencies[int(np.argmax(power))]),
        "spectral_centroid_hz": float(
            np.sum(frequencies * power) / max(total, _EPSILON)
        ),
        "spectral_rms_hz": float(
            np.sqrt(np.sum(np.square(frequencies) * power) / max(total, _EPSILON))
        ),
        "spectral_entropy": float(
            -np.sum(distribution[nonzero] * np.log2(distribution[nonzero]))
        ),
        "low_band_energy": low,
        "mid_band_energy": mid,
        "high_band_energy": high,
        "low_energy_ratio": low / max(total, _EPSILON),
        "mid_energy_ratio": mid / max(total, _EPSILON),
        "high_energy_ratio": high / max(total, _EPSILON),
    }


def _band_energy(
    frequencies: NDArray[np.float64],
    power: NDArray[np.float64],
    start: float,
    end: float,
) -> float:
    mask = (frequencies >= start) & (frequencies < end)
    return float(np.sum(power[mask]))


def _trend_features(
    current: dict[str, float], history: Sequence[FeatureVector]
) -> dict[str, float]:
    all_history = list(history)
    recent = all_history[-9:]
    rms_values = [item.values.get("rms", current["rms"]) for item in recent] + [
        current["rms"]
    ]
    kurtosis_values = [
        item.values.get("kurtosis", current["kurtosis"]) for item in recent
    ] + [current["kurtosis"]]
    envelope_values = [
        item.values.get("envelope_energy", current["envelope_energy"])
        for item in recent
    ] + [current["envelope_energy"]]
    baseline = (
        all_history[0].values.get("rms", current["rms"])
        if all_history
        else current["rms"]
    )
    return {
        "rolling_mean": float(np.mean(rms_values)),
        "rolling_std": float(np.std(rms_values)),
        "rolling_rms": float(np.sqrt(np.mean(np.square(rms_values)))),
        "rms_slope": _slope(rms_values),
        "kurtosis_slope": _slope(kurtosis_values),
        "envelope_energy_slope": _slope(envelope_values),
        "degradation_rate": _slope(rms_values) / max(abs(baseline), _EPSILON),
        "recent_vs_baseline_delta": current["rms"] - baseline,
    }


def _slope(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(values), dtype=np.float64), values, 1)[0])


def _finite(value: float) -> float:
    return value if math.isfinite(value) else 0.0
