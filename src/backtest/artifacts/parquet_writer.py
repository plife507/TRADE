"""
Parquet Writer Helper for Backtest Artifacts.

Provides consistent Parquet writing with pyarrow engine.
Phase 3: Migrate CSV artifacts to Parquet format.

Design choices:
- pyarrow engine for broad compatibility
- snappy compression (fast, reasonable ratio)
- No index written (consistent with CSV behavior)
- Lossless dtypes (float64, int64 preserved)
"""

from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq


# =============================================================================
# Parquet Format Constants
# =============================================================================

# Parquet format version for artifact files.
# Version 2.6 chosen for broad compatibility (pyarrow 4.0+, pandas 1.0+, Spark 3.0+).
# Increment only when needing newer features (e.g., nanosecond timestamps require 2.6+).
PARQUET_VERSION = "2.6"

# Default compression codec for artifact files.
# Snappy: fast compression/decompression, reasonable compression ratio.
DEFAULT_COMPRESSION = "snappy"


def write_parquet(
    df: pd.DataFrame,
    path: Path,
    compression: str = DEFAULT_COMPRESSION,
) -> Path:
    """
    Write DataFrame to Parquet with consistent settings.

    Args:
        df: DataFrame to write
        path: Output path (should end with .parquet)
        compression: Compression codec (default: snappy via DEFAULT_COMPRESSION)

    Returns:
        Path to written file

    Notes:
        - Uses pyarrow engine
        - No index written (matches CSV behavior)
        - Lossless dtypes (floats remain float64, ints remain int64)
        - Stable compression (snappy)
        - Version controlled via PARQUET_VERSION constant
    """
    # Convert to pyarrow table for explicit control
    table = pa.Table.from_pandas(df, preserve_index=False)

    # Write with consistent settings
    pq.write_table(
        table,
        path,
        compression=compression,
        version=PARQUET_VERSION,
        # Don't write pandas metadata (keeps files clean)
        # Note: We preserve dtypes via pyarrow's native type inference
    )

    return path


def read_parquet(path: Path) -> pd.DataFrame:
    """
    Read Parquet file to DataFrame.
    
    Args:
        path: Path to Parquet file
        
    Returns:
        DataFrame with data
    """
    return pd.read_parquet(path, engine="pyarrow")


def compare_csv_parquet(
    csv_path: Path,
    parquet_path: Path,
    float_tolerance: float = 1e-12,
) -> tuple[bool, list[str]]:
    """
    Compare CSV and Parquet files for parity.
    
    Args:
        csv_path: Path to CSV file
        parquet_path: Path to Parquet file
        float_tolerance: Tolerance for float comparison
        
    Returns:
        Tuple of (passed: bool, errors: list[str])
    """
    errors = []
    
    # Check files exist
    if not csv_path.exists():
        errors.append(f"CSV file not found: {csv_path}")
        return False, errors
    if not parquet_path.exists():
        errors.append(f"Parquet file not found: {parquet_path}")
        return False, errors
    
    # Read both files
    try:
        df_csv = pd.read_csv(csv_path)
    except Exception as e:
        errors.append(f"Failed to read CSV: {e}")
        return False, errors
    
    try:
        df_parquet = read_parquet(parquet_path)
    except Exception as e:
        errors.append(f"Failed to read Parquet: {e}")
        return False, errors
    
    # Compare column names and order
    if list(df_csv.columns) != list(df_parquet.columns):
        errors.append(
            f"Column mismatch: CSV has {list(df_csv.columns)}, "
            f"Parquet has {list(df_parquet.columns)}"
        )
        return False, errors
    
    # Compare row counts
    if len(df_csv) != len(df_parquet):
        errors.append(
            f"Row count mismatch: CSV has {len(df_csv)}, "
            f"Parquet has {len(df_parquet)}"
        )
        return False, errors
    
    # Compare values column by column
    for col in df_csv.columns:
        csv_col = df_csv[col]
        pq_col = df_parquet[col]
        
        # Handle NaN masks
        csv_null = csv_col.isna()
        pq_null = pq_col.isna()
        
        if not csv_null.equals(pq_null):
            errors.append(f"Column '{col}': NaN mask mismatch")
            continue
        
        # Compare non-null values
        if csv_col.dtype in ['float64', 'float32']:
            # Float comparison with tolerance
            csv_vals = csv_col[~csv_null].values
            pq_vals = pq_col[~pq_null].values
            
            if len(csv_vals) > 0:
                max_diff = abs(csv_vals - pq_vals).max()
                if max_diff > float_tolerance:
                    errors.append(
                        f"Column '{col}': Float values differ by {max_diff} "
                        f"(tolerance: {float_tolerance})"
                    )
        else:
            # Exact comparison for non-floats
            csv_vals = csv_col[~csv_null]
            pq_vals = pq_col[~pq_null]
            
            # Convert to string for comparison (handles type differences)
            if not csv_vals.astype(str).equals(pq_vals.astype(str)):
                # Find first mismatch
                for i, (c, p) in enumerate(zip(csv_vals, pq_vals)):
                    if str(c) != str(p):
                        errors.append(
                            f"Column '{col}': Value mismatch at row {i}: "
                            f"CSV='{c}', Parquet='{p}'"
                        )
                        break
    
    return len(errors) == 0, errors

