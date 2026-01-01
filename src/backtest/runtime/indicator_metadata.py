"""
Indicator Metadata System v1.

Provides lightweight, auditable metadata for indicator computation:
- Reproducibility: Know exactly how each indicator was computed
- Provenance: Trace which FeatureSpec produced which indicator
- Drift detection: Identify parameter/version changes across runs
- Auditability: Verify indicator correctness for money-adjacent decisions

DESIGN PRINCIPLES:
- In-memory only (no DB persistence)
- Zero impact on indicator array shape/dtype/access
- Deterministic feature_spec_id via stable hashing
- Multi-output indicators share feature_spec_id; indicator_key distinguishes outputs

HASH PAYLOAD:
- feature_spec_id = hash({indicator_type, canonicalized params, input_source})
- EXCLUDES: tf, tf_role, symbol, output_key (stored in metadata but not hashed)
"""

from __future__ import annotations

import csv
import hashlib
import json
import numpy as np
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

if TYPE_CHECKING:
    from .feed_store import FeedStore


# =============================================================================
# Version Helpers
# =============================================================================

def get_pandas_ta_version() -> str:
    """Get pandas_ta version string."""
    try:
        import pandas_ta as ta
        # pandas_ta uses 'version' attribute, not '__version__'
        if hasattr(ta, "version"):
            return str(ta.version)
        elif hasattr(ta, "__version__"):
            return str(ta.__version__)
        return "unknown"
    except ImportError:
        return "not_installed"


def get_code_version() -> str:
    """
    Get code version (git SHA short or 'unknown').
    
    Reuses get_git_commit from manifest_writer if available.
    """
    try:
        from ..artifacts.manifest_writer import get_git_commit
        commit = get_git_commit()
        return commit if commit else "unknown"
    except ImportError:
        return "unknown"


# =============================================================================
# Canonicalization
# =============================================================================

def canonicalize_params(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Canonicalize parameters for stable hashing.
    
    Rules:
    - Drop None values
    - Convert numpy scalars to Python types
    - Convert Enum to string value
    - Convert Path to string
    - Sort keys deterministically
    - NO float rounding (preserve exact precision)
    
    Args:
        params: Raw parameter dict
        
    Returns:
        Canonicalized dict suitable for JSON serialization
        
    Example:
        >>> canonicalize_params({"length": np.int64(20), "fast": None})
        {"length": 20}
    """
    if not params:
        return {}
    
    result = {}
    for key in sorted(params.keys()):
        value = params[key]
        
        # Drop None values
        if value is None:
            continue
        
        # Convert numpy scalars to Python types
        if isinstance(value, (np.integer, np.floating)):
            value = value.item()
        elif isinstance(value, np.ndarray):
            # Convert small arrays to lists (unlikely but handle gracefully)
            value = value.tolist()
        
        # Convert Enum to string value
        if isinstance(value, Enum):
            value = value.value
        
        # Convert Path to string
        if isinstance(value, Path):
            value = str(value)
        
        # Convert bool (ensure JSON-compatible)
        if isinstance(value, (bool, np.bool_)):
            value = bool(value)
        
        result[key] = value
    
    return result


def compute_feature_spec_id(
    indicator_type: str,
    params: Dict[str, Any],
    input_source: str,
) -> str:
    """
    Compute stable, deterministic feature_spec_id.
    
    Hash payload includes ONLY:
    - indicator_type: str (e.g., "ema")
    - params: canonicalized dict
    - input_source: str (e.g., "close", "indicator:ema_20")
    
    EXCLUDES (stored in metadata but not hashed):
    - tf (timeframe)
    - tf_role (exec/htf/mtf)
    - symbol
    - output_key
    
    Args:
        indicator_type: Indicator type string (e.g., "ema", "macd")
        params: Raw or canonicalized parameters
        input_source: Input source string (e.g., "close", "hlc3")
        
    Returns:
        First 12 characters of SHA256 hex digest
        
    Example:
        >>> compute_feature_spec_id("ema", {"length": 20}, "close")
        "a1b2c3d4e5f6"
    """
    canonical_params = canonicalize_params(params)
    
    payload = {
        "indicator_type": indicator_type.lower(),
        "params": canonical_params,
        "input_source": input_source.lower(),
    }
    
    # Deterministic JSON serialization
    json_str = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    
    # SHA256 hash, first 12 chars
    hash_digest = hashlib.sha256(json_str.encode("utf-8")).hexdigest()
    return hash_digest[:12]


# =============================================================================
# Data Model
# =============================================================================

@dataclass(frozen=True)
class IndicatorMetadata:
    """
    Immutable metadata for a single indicator computation.
    
    Captured at computation time in FeatureFrameBuilder.
    Stored in-memory only (not persisted to DB).
    Provides full reproducibility and provenance trail.
    
    Attributes:
        indicator_key: Exact storage key in FeedStore.indicators
        feature_spec_id: Stable hash (12 chars, timeframe-agnostic)
        
        indicator_type: Type string (e.g., "ema", "macd")
        params: Canonicalized parameters dict
        input_source: Input source string (e.g., "close", "hlc3")
        
        symbol: Trading symbol (context, not hashed)
        tf: Timeframe string (context, not hashed)
        tf_role: TF role (exec/htf/mtf, context, not hashed)
        
        warmup_bars_declared: Declared warmup from FeatureSpec
        first_valid_idx_observed: First index where output is non-NaN
        start_bar_idx: Generally = first_valid_idx_observed
        end_bar_idx: Last valid index
        start_ts: Optional timestamp of start_bar_idx
        end_ts: Optional timestamp of end_bar_idx
        
        pandas_ta_version: Version of pandas_ta used
        code_version: Git SHA short or "unknown"
        computed_at_utc: Computation timestamp (datetime in-memory)
    """
    # Identity
    indicator_key: str
    feature_spec_id: str
    
    # Definition
    indicator_type: str
    params: Dict[str, Any]
    input_source: str
    
    # Context (NOT hashed)
    symbol: str
    tf: str
    tf_role: str
    
    # Bounds
    warmup_bars_declared: int
    first_valid_idx_observed: int
    start_bar_idx: int
    end_bar_idx: int
    start_ts: Optional[datetime] = None
    end_ts: Optional[datetime] = None
    
    # Versioning
    pandas_ta_version: str = field(default_factory=get_pandas_ta_version)
    code_version: str = field(default_factory=get_code_version)
    computed_at_utc: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def __post_init__(self):
        """Validate metadata fields."""
        if not self.indicator_key:
            raise ValueError("indicator_key cannot be empty")
        if not self.feature_spec_id:
            raise ValueError("feature_spec_id cannot be empty")
        if len(self.feature_spec_id) != 12:
            raise ValueError(f"feature_spec_id must be 12 chars, got {len(self.feature_spec_id)}")
    
    def to_dict(self, serialize_datetime: bool = False) -> Dict[str, Any]:
        """
        Convert to dict for serialization.
        
        Args:
            serialize_datetime: If True, convert datetimes to ISO8601 strings
            
        Returns:
            Dict representation
        """
        result = asdict(self)
        
        if serialize_datetime:
            # Convert datetimes to ISO8601 with Z suffix
            if self.start_ts:
                result["start_ts"] = self.start_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            if self.end_ts:
                result["end_ts"] = self.end_ts.strftime("%Y-%m-%dT%H:%M:%SZ")
            result["computed_at_utc"] = self.computed_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        return result
    
    def recompute_feature_spec_id(self) -> str:
        """
        Recompute feature_spec_id from stored fields.
        
        Used for consistency validation.
        """
        return compute_feature_spec_id(
            self.indicator_type,
            self.params,
            self.input_source,
        )


def find_first_valid_idx(arr: np.ndarray) -> int:
    """
    Find first index where array value is not NaN.
    
    Args:
        arr: Numpy array to search
        
    Returns:
        First valid index, or -1 if all values are NaN
    """
    if len(arr) == 0:
        return -1
    
    # Handle non-float arrays (all valid)
    if not np.issubdtype(arr.dtype, np.floating):
        return 0
    
    # Find first non-NaN
    valid_mask = ~np.isnan(arr)
    valid_indices = np.where(valid_mask)[0]
    
    if len(valid_indices) == 0:
        return -1
    
    return int(valid_indices[0])


# =============================================================================
# Validation Helpers
# =============================================================================

@dataclass
class MetadataValidationResult:
    """Result of metadata validation."""
    is_valid: bool
    coverage_ok: bool
    ids_consistent: bool
    missing_metadata: List[str] = field(default_factory=list)
    extra_metadata: List[str] = field(default_factory=list)
    id_mismatches: List[Dict[str, str]] = field(default_factory=list)
    key_mismatches: List[str] = field(default_factory=list)


def validate_metadata_coverage(feed_store: "FeedStore") -> bool:
    """
    Validate that every indicator has corresponding metadata.
    
    Args:
        feed_store: FeedStore to validate
        
    Returns:
        True if indicator_keys == metadata_keys
    """
    indicator_keys = set(feed_store.indicators.keys())
    metadata_keys = set(feed_store.indicator_metadata.keys())
    return indicator_keys == metadata_keys


def validate_feature_spec_ids(feed_store: "FeedStore") -> MetadataValidationResult:
    """
    Validate metadata coverage and feature_spec_id consistency.
    
    Checks:
    1. Every indicator key has matching metadata key
    2. No extra metadata keys
    3. feature_spec_id matches recomputed value
    4. metadata.indicator_key matches dict key
    
    Args:
        feed_store: FeedStore to validate
        
    Returns:
        MetadataValidationResult with detailed findings
    """
    indicator_keys = set(feed_store.indicators.keys())
    metadata_keys = set(feed_store.indicator_metadata.keys())
    
    missing = list(indicator_keys - metadata_keys)
    extra = list(metadata_keys - indicator_keys)
    coverage_ok = len(missing) == 0 and len(extra) == 0
    
    id_mismatches = []
    key_mismatches = []
    
    # Check each metadata entry
    for key, meta in feed_store.indicator_metadata.items():
        # Check indicator_key == dict key
        if meta.indicator_key != key:
            key_mismatches.append(f"{key} != {meta.indicator_key}")
        
        # Check feature_spec_id consistency
        recomputed = meta.recompute_feature_spec_id()
        if meta.feature_spec_id != recomputed:
            id_mismatches.append({
                "indicator_key": key,
                "stored_id": meta.feature_spec_id,
                "recomputed_id": recomputed,
            })
    
    ids_consistent = len(id_mismatches) == 0 and len(key_mismatches) == 0
    is_valid = coverage_ok and ids_consistent
    
    return MetadataValidationResult(
        is_valid=is_valid,
        coverage_ok=coverage_ok,
        ids_consistent=ids_consistent,
        missing_metadata=missing,
        extra_metadata=extra,
        id_mismatches=id_mismatches,
        key_mismatches=key_mismatches,
    )


# =============================================================================
# Export Utilities
# =============================================================================

def _build_run_header() -> Dict[str, str]:
    """Build run header for exports."""
    return {
        "schema_version": "indicator-metadata-v1",
        "pandas_ta_version": get_pandas_ta_version(),
        "code_version": get_code_version(),
        "exported_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


def _filter_metadata(
    metadata_dict: Dict[str, IndicatorMetadata],
    filters: Optional[Dict[str, Any]] = None,
) -> List[IndicatorMetadata]:
    """
    Filter metadata by criteria.
    
    Supported filters:
    - symbol: str
    - tf: str
    - tf_role: str
    - indicator_type: str
    - feature_spec_id: str
    """
    if not filters:
        return list(metadata_dict.values())
    
    result = []
    for meta in metadata_dict.values():
        match = True
        for key, value in filters.items():
            if hasattr(meta, key):
                if getattr(meta, key) != value:
                    match = False
                    break
        if match:
            result.append(meta)
    
    return result


def export_metadata_jsonl(
    feed_store: "FeedStore",
    output_path: Path,
    filters: Optional[Dict[str, Any]] = None,
    include_header: bool = True,
) -> None:
    """
    Export metadata to JSONL format.
    
    First line (if include_header=True) is run header.
    Subsequent lines are individual indicator metadata records.
    
    Args:
        feed_store: FeedStore with metadata
        output_path: Output file path
        filters: Optional filters (symbol, tf, tf_role, indicator_type, feature_spec_id)
        include_header: Whether to include run header as first line
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    metadata_list = _filter_metadata(feed_store.indicator_metadata, filters)
    
    with open(output_path, "w", encoding="utf-8") as f:
        if include_header:
            header = _build_run_header()
            header["_type"] = "header"
            f.write(json.dumps(header, sort_keys=True) + "\n")
        
        for meta in metadata_list:
            record = meta.to_dict(serialize_datetime=True)
            record["_type"] = "indicator"
            f.write(json.dumps(record, sort_keys=True) + "\n")


def export_metadata_json(
    feed_store: "FeedStore",
    output_path: Path,
    filters: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Export metadata to JSON format.
    
    Structure:
    {
        "header": { run header },
        "indicators": [ list of indicator metadata ]
    }
    
    Args:
        feed_store: FeedStore with metadata
        output_path: Output file path
        filters: Optional filters
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    metadata_list = _filter_metadata(feed_store.indicator_metadata, filters)
    
    output = {
        "header": _build_run_header(),
        "indicators": [meta.to_dict(serialize_datetime=True) for meta in metadata_list],
    }
    
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, sort_keys=True)


def export_metadata_csv(
    feed_store: "FeedStore",
    output_path: Path,
    filters: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Export metadata to CSV format (flattened).
    
    Note: params dict is JSON-serialized as a single column.
    
    Args:
        feed_store: FeedStore with metadata
        output_path: Output file path
        filters: Optional filters
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    metadata_list = _filter_metadata(feed_store.indicator_metadata, filters)
    
    if not metadata_list:
        # Write empty file with header only
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "indicator_key", "feature_spec_id", "indicator_type",
                "params_json", "input_source", "symbol", "tf", "tf_role",
                "warmup_bars_declared", "first_valid_idx_observed",
                "start_bar_idx", "end_bar_idx", "start_ts", "end_ts",
                "pandas_ta_version", "code_version", "computed_at_utc",
            ])
        return
    
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        
        # Header row
        writer.writerow([
            "indicator_key", "feature_spec_id", "indicator_type",
            "params_json", "input_source", "symbol", "tf", "tf_role",
            "warmup_bars_declared", "first_valid_idx_observed",
            "start_bar_idx", "end_bar_idx", "start_ts", "end_ts",
            "pandas_ta_version", "code_version", "computed_at_utc",
        ])
        
        # Data rows
        for meta in metadata_list:
            start_ts_str = meta.start_ts.strftime("%Y-%m-%dT%H:%M:%SZ") if meta.start_ts else ""
            end_ts_str = meta.end_ts.strftime("%Y-%m-%dT%H:%M:%SZ") if meta.end_ts else ""
            computed_str = meta.computed_at_utc.strftime("%Y-%m-%dT%H:%M:%SZ")
            
            writer.writerow([
                meta.indicator_key,
                meta.feature_spec_id,
                meta.indicator_type,
                json.dumps(meta.params, sort_keys=True),
                meta.input_source,
                meta.symbol,
                meta.tf,
                meta.tf_role,
                meta.warmup_bars_declared,
                meta.first_valid_idx_observed,
                meta.start_bar_idx,
                meta.end_bar_idx,
                start_ts_str,
                end_ts_str,
                meta.pandas_ta_version,
                meta.code_version,
                computed_str,
            ])

