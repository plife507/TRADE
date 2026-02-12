"""
Batch wrapper for incremental structure detectors.

Allows running O(1) incremental detectors in batch mode for validation
and comparison with batch implementations.
"""

import numpy as np
from typing import Any

from .base import BarData, BaseIncrementalDetector
from .registry import STRUCTURE_REGISTRY


def run_detector_batch(
    detector_type: str,
    ohlcv: dict[str, np.ndarray],
    params: dict[str, Any],
    deps: dict[str, BaseIncrementalDetector] | None = None,
    indicators_data: dict[str, np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    """
    Run an incremental detector in batch mode over OHLCV data.

    Args:
        detector_type: Registered detector type name (e.g., "swing", "trend")
        ohlcv: Dict with keys: open, high, low, close, volume (numpy arrays)
        params: Detector parameters
        deps: Optional dependency detectors (already instantiated)
        indicators_data: Optional dict of indicator arrays (e.g., {"atr_14": np.ndarray}).
            When provided, indicator values are passed through BarData.indicators
            at each bar, enabling ATR-dependent features (significance, noise
            filtering, atr_zigzag).

    Returns:
        Dict mapping output_key -> numpy array of values per bar
    """
    if detector_type not in STRUCTURE_REGISTRY:
        raise ValueError(f"Unknown detector type: {detector_type}")

    detector_class = STRUCTURE_REGISTRY[detector_type]
    detector = detector_class(params, deps)  # type: ignore[call-arg]

    n_bars = len(ohlcv["close"])
    output_keys = detector.get_output_keys()

    # Pre-allocate output arrays
    outputs: dict[str, np.ndarray] = {}
    for key in output_keys:
        # dtype=object so arrays can hold floats, strings, bools, etc.
        outputs[key] = np.full(n_bars, np.nan, dtype=object)

    # Process each bar
    for bar_idx in range(n_bars):
        # Build indicators dict for this bar from indicator arrays
        bar_indicators: dict[str, float] = {}
        if indicators_data:
            for ind_key, ind_arr in indicators_data.items():
                if bar_idx < len(ind_arr):
                    val = float(ind_arr[bar_idx])
                    if not np.isnan(val):
                        bar_indicators[ind_key] = val

        bar = BarData(
            idx=bar_idx,
            open=float(ohlcv["open"][bar_idx]),
            high=float(ohlcv["high"][bar_idx]),
            low=float(ohlcv["low"][bar_idx]),
            close=float(ohlcv["close"][bar_idx]),
            volume=float(ohlcv["volume"][bar_idx]),
            indicators=bar_indicators,
        )

        detector.update(bar_idx, bar)

        # Collect outputs
        for key in output_keys:
            try:
                value = detector.get_value(key)
                outputs[key][bar_idx] = value
            except (KeyError, ValueError):
                pass  # Keep NaN for unavailable values

    return outputs


def create_detector_with_deps(
    detector_type: str,
    params: dict[str, Any],
    dep_specs: dict[str, tuple[str, dict[str, Any]]] | None = None,
) -> tuple[BaseIncrementalDetector, dict[str, BaseIncrementalDetector]]:
    """
    Create a detector with its dependencies instantiated.

    Args:
        detector_type: Main detector type
        params: Main detector parameters
        dep_specs: Dict mapping dep_name -> (dep_type, dep_params)

    Returns:
        Tuple of (main_detector, deps_dict)
    """
    deps = {}
    if dep_specs:
        for dep_name, (dep_type, dep_params) in dep_specs.items():
            if dep_type not in STRUCTURE_REGISTRY:
                raise ValueError(f"Unknown dependency type: {dep_type}")
            dep_class = STRUCTURE_REGISTRY[dep_type]
            deps[dep_name] = dep_class(dep_params, None)  # type: ignore[call-arg]

    if detector_type not in STRUCTURE_REGISTRY:
        raise ValueError(f"Unknown detector type: {detector_type}")

    detector_class = STRUCTURE_REGISTRY[detector_type]
    detector = detector_class(params, deps if deps else None)  # type: ignore[call-arg]

    return detector, deps
