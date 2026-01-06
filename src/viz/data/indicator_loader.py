"""
Indicator data loader for visualization.

Loads indicators from Play definition, computes via FeatureFrameBuilder,
and renders using the Renderer Registry.
"""

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.backtest.play import Play
from src.backtest.feature_registry import Feature, FeatureType
from src.backtest.features.feature_frame_builder import (
    FeatureFrameBuilder,
    FeatureSpecSet,
    FeatureSpec,
)
from src.backtest.features.feature_spec import InputSource

from .play_loader import load_play_for_run, get_unique_timeframes
from .ohlcv_loader import load_ohlcv_for_timeframes
from .timestamp_utils import to_unix_timestamp
from ..renderers.indicators import IndicatorRenderer, UnsupportedIndicatorError
from ..renderers.structures import StructureRenderer, UnsupportedStructureError


def load_indicators_for_run(
    run_path: Path,
    verify_hash: bool = True,
) -> dict[str, Any]:
    """
    Load all indicator data for a backtest run.

    Computes indicators from Play definition using DuckDB OHLCV data.
    Multi-TF indicators are forward-filled to exec bar timestamps.

    Args:
        run_path: Path to run directory
        verify_hash: Verify Play hash matches stored hash

    Returns:
        Dict with:
        - play_id: Play identifier
        - play_hash: Current Play hash
        - hash_verified: Whether hash was verified
        - overlays: List of overlay indicator data
        - panes: List of pane indicator data
        - structures: List of structure data

    Raises:
        UnsupportedIndicatorError: If Play has unsupported indicator type
        UnsupportedStructureError: If Play has unsupported structure type
    """
    # Load Play and verify hash
    play, result = load_play_for_run(run_path, verify_hash=verify_hash)

    # Get run metadata
    symbol = result.get("symbol")
    window_start = result.get("window_start")
    window_end = result.get("window_end")
    exec_tf = result.get("tf_exec", play.execution_tf)

    # Collect unique timeframes from features
    timeframes = get_unique_timeframes(play)

    # Load OHLCV for all timeframes from DuckDB
    ohlcv_dict = load_ohlcv_for_timeframes(
        symbol=symbol,
        timeframes=timeframes,
        start_ts=window_start,
        end_ts=window_end,
    )

    if not ohlcv_dict:
        return {
            "play_id": play.id,
            "play_hash": result.get("idea_hash"),
            "hash_verified": verify_hash,
            "overlays": [],
            "panes": [],
            "structures": [],
            "error": "No OHLCV data found in DuckDB",
        }

    # Get exec TF timestamps for alignment
    exec_df = ohlcv_dict.get(exec_tf)
    if exec_df is None:
        exec_df = list(ohlcv_dict.values())[0]

    exec_timestamps = _extract_timestamps(exec_df)

    # Build features by timeframe
    builder = FeatureFrameBuilder()
    features_by_tf: dict[str, dict[str, np.ndarray]] = {}

    for tf in timeframes:
        tf_df = ohlcv_dict.get(tf)
        if tf_df is None:
            continue

        # Get features for this TF
        tf_features = [f for f in play.features if f.tf == tf and f.type == FeatureType.INDICATOR]
        if not tf_features:
            continue

        # Create FeatureSpecSet from Play features
        specs = []
        for feature in tf_features:
            # Convert from feature_registry.InputSource to feature_spec.InputSource
            input_src = InputSource.CLOSE
            if feature.input_source:
                input_src = InputSource(feature.input_source.value)

            spec = FeatureSpec(
                indicator_type=feature.indicator_type,
                output_key=feature.id,
                params=dict(feature.params) if feature.params else {},
                input_source=input_src,
            )
            specs.append(spec)

        spec_set = FeatureSpecSet(
            symbol=symbol,
            tf=tf,
            specs=specs,
        )

        # Build features
        feature_arrays = builder.build(tf_df, spec_set)
        features_by_tf[tf] = {}

        # Extract indicator arrays
        for feature in tf_features:
            values = feature_arrays.get(feature.id)
            if values is not None:
                features_by_tf[tf][feature.id] = values

    # Reset color index for consistent coloring
    IndicatorRenderer.reset_colors()

    # Process each feature
    overlays = []
    panes_by_type: dict[str, list[dict]] = {}
    structures = []

    for feature in play.features:
        if feature.type == FeatureType.INDICATOR:
            indicator_data = _process_indicator_feature(
                feature=feature,
                features_by_tf=features_by_tf,
                exec_timestamps=exec_timestamps,
                ohlcv_dict=ohlcv_dict,
            )
            if indicator_data:
                if IndicatorRenderer.is_overlay(feature.indicator_type):
                    overlays.append(indicator_data)
                else:
                    pane_type = IndicatorRenderer.get_spec(feature.indicator_type).pane_type
                    if pane_type not in panes_by_type:
                        panes_by_type[pane_type] = []
                    panes_by_type[pane_type].append(indicator_data)

        elif feature.type == FeatureType.STRUCTURE:
            structure_data = _process_structure_feature(
                feature=feature,
                ohlcv_dict=ohlcv_dict,
                exec_timestamps=exec_timestamps,
            )
            if structure_data:
                structures.append(structure_data)

    # Convert panes dict to list format
    panes = []
    for pane_type, indicators in panes_by_type.items():
        spec = IndicatorRenderer.get_spec(indicators[0]["type"])
        panes.append({
            "type": pane_type,
            "indicators": indicators,
            "reference_lines": spec.reference_lines or [],
        })

    return {
        "play_id": play.id,
        "play_hash": result.get("idea_hash"),
        "hash_verified": verify_hash,
        "overlays": overlays,
        "panes": panes,
        "structures": structures,
    }


def _process_indicator_feature(
    feature: Feature,
    features_by_tf: dict[str, dict[str, np.ndarray]],
    exec_timestamps: list[int],
    ohlcv_dict: dict[str, pd.DataFrame],
) -> dict[str, Any] | None:
    """
    Process a single indicator feature into chart data.

    Args:
        feature: Feature definition
        features_by_tf: Computed feature arrays by TF
        exec_timestamps: Exec bar timestamps for alignment
        ohlcv_dict: OHLCV DataFrames by TF

    Returns:
        Rendered indicator data or None if no data
    """
    # Validate renderer supports this type
    if not IndicatorRenderer.is_supported(feature.indicator_type):
        raise UnsupportedIndicatorError(
            feature.indicator_type,
            IndicatorRenderer.get_supported_types(),
        )

    tf = feature.tf
    feature_key = feature.id

    # Get feature arrays for this TF
    tf_features = features_by_tf.get(tf, {})
    values = tf_features.get(feature_key)

    if values is None:
        return None

    # Get timestamps for this TF
    tf_df = ohlcv_dict.get(tf)
    if tf_df is None:
        return None

    tf_timestamps = _extract_timestamps(tf_df)

    # Align to exec timestamps (forward-fill for HTF/MTF)
    aligned_data = _align_to_exec(
        values=values,
        source_timestamps=tf_timestamps,
        target_timestamps=exec_timestamps,
    )

    # Render the indicator
    return IndicatorRenderer.render(
        indicator_type=feature.indicator_type,
        key=feature_key,
        data=aligned_data,
        params=dict(feature.params) if feature.params else {},
        tf=tf,
    )


def _process_structure_feature(
    feature: Feature,
    ohlcv_dict: dict[str, pd.DataFrame],
    exec_timestamps: list[int],
) -> dict[str, Any] | None:
    """
    Process a single structure feature into chart data.

    Note: Structure computation requires running incremental detectors.
    For now, we mark structures as "pending computation" in the response.
    Full structure rendering requires engine state replay.

    Args:
        feature: Feature definition
        ohlcv_dict: OHLCV DataFrames by TF
        exec_timestamps: Exec bar timestamps

    Returns:
        Structure placeholder data or None
    """
    # Validate renderer supports this type
    if not StructureRenderer.is_supported(feature.structure_type):
        raise UnsupportedStructureError(
            feature.structure_type,
            StructureRenderer.get_supported_types(),
        )

    # Structure computation requires incremental detector state
    # This is a placeholder - full implementation needs engine replay
    return {
        "key": feature.id,
        "type": feature.structure_type,
        "render_method": StructureRenderer.get_spec(feature.structure_type).render_method,
        "params": dict(feature.params) if feature.params else {},
        "tf": feature.tf,
        "label": StructureRenderer.format_label(
            feature.structure_type,
            dict(feature.params) if feature.params else {},
            feature.tf,
        ),
        "status": "pending",
        "message": "Structure computation requires engine replay",
    }


def _extract_timestamps(df: pd.DataFrame) -> list[int]:
    """Extract Unix timestamps (seconds) from DataFrame."""
    timestamps = []

    # Try common timestamp column names
    ts_col = None
    for col in ["timestamp", "ts_close", "time"]:
        if col in df.columns:
            ts_col = col
            break

    if ts_col is None:
        return timestamps

    for _, row in df.iterrows():
        unix_ts = to_unix_timestamp(row[ts_col])
        if unix_ts is not None:
            timestamps.append(unix_ts)

    return timestamps


def _align_to_exec(
    values: np.ndarray,
    source_timestamps: list[int],
    target_timestamps: list[int],
) -> list[dict[str, Any]]:
    """
    Align indicator values from source TF to target (exec) TF timestamps.

    For HTF/MTF indicators, forward-fills values to exec bars.
    Values are held until the next HTF/MTF close.

    Args:
        values: Indicator values at source TF
        source_timestamps: Source TF timestamps (seconds)
        target_timestamps: Target (exec) TF timestamps (seconds)

    Returns:
        List of {"time": unix_ts, "value": float} aligned to target timestamps
    """
    if len(values) != len(source_timestamps):
        # Length mismatch - return what we can
        min_len = min(len(values), len(source_timestamps))
        values = values[:min_len]
        source_timestamps = source_timestamps[:min_len]

    result = []

    # Build source map for fast lookup
    source_map = {}
    for i, ts in enumerate(source_timestamps):
        if not np.isnan(values[i]):
            source_map[ts] = float(values[i])

    # For each target timestamp, find the most recent source value
    sorted_source_ts = sorted(source_map.keys())
    current_value = None

    for target_ts in target_timestamps:
        # Find the most recent source timestamp <= target
        for src_ts in sorted_source_ts:
            if src_ts <= target_ts:
                current_value = source_map[src_ts]
            else:
                break

        if current_value is not None:
            result.append({"time": target_ts, "value": current_value})

    return result
