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

import hashlib
import json
import numpy as np
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


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
            return str(getattr(ta, "__version__"))
        return "unknown"
    except ImportError:
        return "not_installed"


def get_code_version() -> str:
    """
    Get code version (git SHA short or 'unknown').

    Reuses get_git_commit from manifest_writer if available.
    """
    try:
        from src.backtest.artifacts.manifest_writer import get_git_commit
        commit = get_git_commit()
        return commit if commit else "unknown"
    except ImportError:
        return "unknown"


# =============================================================================
# Canonicalization
# =============================================================================

def canonicalize_params(params: dict[str, Any]) -> dict[str, Any]:
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
    params: dict[str, Any],
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
    - tf_role (low_tf/med_tf/high_tf)
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
        tf_role: TF role (low_tf/med_tf/high_tf, context, not hashed)

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
    params: dict[str, Any]
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
    start_ts: datetime | None = None
    end_ts: datetime | None = None

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

    def to_dict(self, serialize_datetime: bool = False) -> dict[str, Any]:
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
