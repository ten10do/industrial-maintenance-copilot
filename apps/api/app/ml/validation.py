"""Reproducible raw-signal validation, normalization and windowing."""

from __future__ import annotations

from dataclasses import replace
from datetime import timedelta

import numpy as np
from numpy.typing import NDArray

from app.ml.types import TelemetryWindow


class SignalValidationError(ValueError):
    """The signal cannot safely enter the feature pipeline."""


_UNIT_SCALE_TO_M_S2 = {"m/s2": 1.0, "m/s^2": 1.0, "g": 9.80665}


def validated_signal(
    window: TelemetryWindow,
    *,
    minimum_samples: int = 32,
    max_missing_ratio: float = 0.01,
    max_absolute_amplitude: float | None = None,
) -> tuple[TelemetryWindow, NDArray[np.float64], float]:
    """Return an SI-normalized finite signal and a deterministic quality score."""
    if window.sampling_rate_hz <= 0:
        raise SignalValidationError("sampling_rate_hz must be positive")
    if window.ended_at <= window.started_at:
        raise SignalValidationError("window timestamps must be strictly increasing")
    if len(window.signal) < minimum_samples:
        raise SignalValidationError(
            f"signal requires at least {minimum_samples} samples"
        )
    if window.unit not in _UNIT_SCALE_TO_M_S2:
        raise SignalValidationError(f"unsupported vibration unit: {window.unit}")

    values = np.asarray(window.signal, dtype=np.float64)
    if np.isinf(values).any():
        raise SignalValidationError("signal contains infinite values")
    missing = np.isnan(values)
    missing_ratio = float(np.mean(missing))
    if missing_ratio > max_missing_ratio:
        raise SignalValidationError(
            "signal missing-value ratio exceeds configured limit"
        )
    if missing.any():
        valid_indices = np.flatnonzero(~missing)
        if valid_indices.size < 2:
            raise SignalValidationError("not enough finite samples for interpolation")
        values[missing] = np.interp(
            np.flatnonzero(missing), valid_indices, values[~missing]
        )

    values *= _UNIT_SCALE_TO_M_S2[window.unit]
    if (
        max_absolute_amplitude is not None
        and np.max(np.abs(values)) > max_absolute_amplitude
    ):
        raise SignalValidationError(
            "signal amplitude exceeds configured physical limit"
        )

    if window.sample_timestamps is not None:
        timestamps = np.asarray(window.sample_timestamps, dtype=np.float64)
        if len(timestamps) != len(values):
            raise SignalValidationError("sample timestamps and signal length differ")
        if not np.isfinite(timestamps).all() or np.any(np.diff(timestamps) <= 0):
            raise SignalValidationError("sample timestamps must be finite and unique")

    normalized = replace(window, signal=tuple(values.tolist()), unit="m/s2")
    return normalized, values, max(0.0, 1.0 - missing_ratio)


def split_windows(
    window: TelemetryWindow,
    *,
    window_size: int,
    stride: int,
) -> list[TelemetryWindow]:
    if window_size < 32 or stride <= 0:
        raise SignalValidationError(
            "window_size must be >= 32 and stride must be positive"
        )
    normalized, values, _ = validated_signal(window, minimum_samples=window_size)
    duration_per_sample = 1.0 / normalized.sampling_rate_hz
    result: list[TelemetryWindow] = []
    for start in range(0, len(values) - window_size + 1, stride):
        end = start + window_size
        started_at = normalized.started_at + timedelta(
            seconds=start * duration_per_sample
        )
        ended_at = normalized.started_at + timedelta(seconds=end * duration_per_sample)
        result.append(
            replace(
                normalized,
                signal=tuple(values[start:end].tolist()),
                started_at=started_at,
                ended_at=ended_at,
                sample_timestamps=None,
            )
        )
    return result
