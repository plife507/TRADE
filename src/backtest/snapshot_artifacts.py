"""
Snapshot Artifacts: Emit lossless snapshots of computed indicators for audit.

This module handles writing snapshot artifacts during backtest execution:
- OHLCV dataframes with computed indicators
- Manifest with metadata for audit reconstruction
- Lossless Parquet format to avoid float rounding issues

Used by verification suite to enable pandas_ta parity audits.
"""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
import json


@dataclass
class SnapshotFrameInfo:
    """Metadata about a snapshot frame (role-keyed: exec/htf/mtf)."""
    role: str  # exec, htf, or mtf
    tf: str
    row_count: int
    column_count: int
    timestamp_range: tuple[datetime, datetime]
    columns_present: list[str]  # ordered list of all columns as written
    feature_specs_resolved: list[dict[str, Any]]
    # Per feature_spec contract tracking
    outputs_expected_by_registry: dict[str, list[str]]  # output_key -> expected outputs
    outputs_written: dict[str, list[str]]  # output_key -> actual outputs in frame
    extras_dropped: dict[str, list[str]]  # output_key -> extras dropped by vendor


@dataclass
class SnapshotManifest:
    """Manifest for a snapshot artifact set (role-keyed)."""
    idea_card_id: str
    symbol: str
    window_start: datetime
    window_end: datetime
    exec_tf: str
    htf: str | None
    mtf: str | None

    # Frame info keyed by ROLE (exec/htf/mtf), not TF
    frames: dict[str, SnapshotFrameInfo]  # role -> info

    # Metadata
    frame_format: str = "parquet"
    float_precision: str = "lossless"
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for JSON serialization."""
        result = {
            "idea_card_id": self.idea_card_id,
            "symbol": self.symbol,
            "window_start": self.window_start.isoformat(),
            "window_end": self.window_end.isoformat(),
            "exec_tf": self.exec_tf,
            "htf": self.htf,
            "mtf": self.mtf,
            "frame_format": self.frame_format,
            "float_precision": self.float_precision,
            "created_at": self.created_at.isoformat(),
            "frames": {}
        }

        for role, info in self.frames.items():
            result["frames"][role] = {
                "role": info.role,
                "tf": info.tf,
                "frame_path": f"{role}_frame.parquet",
                "row_count": info.row_count,
                "column_count": info.column_count,
                "timestamp_range": [info.timestamp_range[0].isoformat(), info.timestamp_range[1].isoformat()],
                "columns_present": info.columns_present,
                "feature_specs_resolved": info.feature_specs_resolved,
                "outputs_expected_by_registry": info.outputs_expected_by_registry,
                "outputs_written": info.outputs_written,
                "extras_dropped": info.extras_dropped,
            }

        return result


def emit_snapshot_artifacts(
    run_dir: Path,
    idea_card_id: str,
    symbol: str,
    window_start: datetime,
    window_end: datetime,
    exec_tf: str,
    htf: str | None,
    mtf: str | None,
    exec_df: Any,  # DataFrame
    htf_df: Any | None = None,  # DataFrame
    mtf_df: Any | None = None,  # DataFrame
    exec_feature_specs: list | None = None,
    htf_feature_specs: list | None = None,
    mtf_feature_specs: list | None = None,
) -> Path:
    """
    Emit snapshot artifacts to run_dir/snapshots/ (role-keyed).

    Args:
        run_dir: Run directory (e.g., backtests/system_symbol_tf/run-001/)
        idea_card_id: IdeaCard identifier
        symbol: Trading symbol
        window_start/end: Backtest window
        exec_tf/htf/mtf: Timeframes
        exec_df/htf_df/mtf_df: DataFrames with OHLCV + computed indicators
        exec_feature_specs/htf_feature_specs/mtf_feature_specs: FeatureSpec objects used

    Returns:
        Path to snapshots directory
    """
    import pandas as pd
    from .indicator_registry import get_registry

    snapshots_dir = run_dir / "snapshots"
    snapshots_dir.mkdir(exist_ok=True)
    
    registry = get_registry()
    frames_info = {}
    ohlcv_cols = ["open", "high", "low", "close", "volume", "timestamp"]

    def write_frame(
        df: pd.DataFrame,
        role: str,
        tf: str,
        feature_specs: list | None = None
    ) -> SnapshotFrameInfo | None:
        """Write a frame with role-keyed naming and contract tracking."""
        if df is None or df.empty:
            return None

        # Write Parquet with role-based naming
        parquet_path = snapshots_dir / f"{role}_frame.parquet"
        df.to_parquet(parquet_path, index=False)

        # Build feature specs resolved and contract tracking
        feature_specs_resolved = []
        outputs_expected_by_registry: dict[str, list[str]] = {}
        outputs_written: dict[str, list[str]] = {}
        extras_dropped: dict[str, list[str]] = {}

        if feature_specs:
            for spec in feature_specs:
                indicator_type = spec.indicator_type.value if hasattr(spec.indicator_type, 'value') else str(spec.indicator_type)
                output_key = spec.output_key
                
                feature_specs_resolved.append({
                    "indicator_type": indicator_type,
                    "output_key": output_key,
                    "params": spec.params,
                    "input_source": spec.input_source.value if hasattr(spec.input_source, 'value') else str(spec.input_source),
                })
                
                # Get registry-declared outputs for this indicator
                if registry.is_multi_output(indicator_type):
                    declared_suffixes = list(registry.get_output_suffixes(indicator_type))
                    expected_cols = [f"{output_key}_{suffix}" for suffix in declared_suffixes]
                else:
                    expected_cols = [output_key]
                
                outputs_expected_by_registry[output_key] = expected_cols
                
                # Find what was actually written to the frame
                written_cols = [col for col in expected_cols if col in df.columns]
                outputs_written[output_key] = written_cols
                
                # Note: extras are dropped by vendor before reaching here
                # We record if any expected were missing (shouldn't happen if vendor works)
                extras_dropped[output_key] = []  # Already dropped by vendor

        # Columns present (ordered list as written)
        columns_present = list(df.columns)

        info = SnapshotFrameInfo(
            role=role,
            tf=tf,
            row_count=len(df),
            column_count=len(df.columns),
            timestamp_range=(df["timestamp"].min(), df["timestamp"].max()),
            columns_present=columns_present,
            feature_specs_resolved=feature_specs_resolved,
            outputs_expected_by_registry=outputs_expected_by_registry,
            outputs_written=outputs_written,
            extras_dropped=extras_dropped,
        )

        return info

    # Write each frame with role-based keys
    if exec_df is not None:
        info = write_frame(exec_df, "exec", exec_tf, exec_feature_specs)
        if info:
            frames_info["exec"] = info

    if htf_df is not None and htf:
        info = write_frame(htf_df, "htf", htf, htf_feature_specs)
        if info:
            frames_info["htf"] = info

    if mtf_df is not None and mtf:
        info = write_frame(mtf_df, "mtf", mtf, mtf_feature_specs)
        if info:
            frames_info["mtf"] = info

    # Write manifest
    manifest = SnapshotManifest(
        idea_card_id=idea_card_id,
        symbol=symbol,
        window_start=window_start,
        window_end=window_end,
        exec_tf=exec_tf,
        htf=htf,
        mtf=mtf,
        frames=frames_info,
    )

    manifest_path = snapshots_dir / "snapshot_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest.to_dict(), f, indent=2, sort_keys=True)

    return snapshots_dir


def load_snapshot_artifacts(run_dir: Path) -> dict[str, Any] | None:
    """
    Load snapshot artifacts from a run directory (role-keyed).

    Args:
        run_dir: Run directory containing snapshots/

    Returns:
        Dict with manifest and DataFrames keyed by role, or None if not found
    """
    import pandas as pd

    snapshots_dir = run_dir / "snapshots"
    if not snapshots_dir.exists():
        return None

    manifest_path = snapshots_dir / "snapshot_manifest.json"
    if not manifest_path.exists():
        return None

    # Load manifest
    with open(manifest_path, "r") as f:
        manifest_data = json.load(f)

    # Load DataFrames keyed by role
    frames = {}
    for role, info in manifest_data["frames"].items():
        # Try role-based naming first (new format)
        parquet_path = snapshots_dir / f"{role}_frame.parquet"
        if not parquet_path.exists():
            # Fall back to TF-based naming (legacy format)
            tf = info.get("tf", role)
            parquet_path = snapshots_dir / f"{tf}_frame.parquet"
        
        if parquet_path.exists():
            df = pd.read_parquet(parquet_path)
            frames[role] = df

    return {
        "manifest": manifest_data,
        "frames": frames,
    }
