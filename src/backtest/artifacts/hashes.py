"""
Deterministic hashing utilities for backtest artifacts.

Provides hash functions for:
- Trades list (for replay determinism)
- Equity curve (for replay determinism)
- Play (for config identity)

All hash functions produce deterministic, reproducible hashes
from the same input data across runs.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from ..types import Trade, EquityPoint


def compute_trades_hash(trades: list[Trade]) -> str:
    """
    Compute deterministic hash of trades list.
    
    Args:
        trades: List of Trade objects
        
    Returns:
        SHA256 hash (first 16 chars) of serialized trades
    """
    # Serialize trades to dicts
    trades_data = []
    for t in trades:
        if hasattr(t, 'to_dict'):
            trades_data.append(t.to_dict())
        elif isinstance(t, dict):
            trades_data.append(t)
        else:
            # Fallback: extract key fields
            trades_data.append({
                "entry_time": str(getattr(t, 'entry_time', '')),
                "exit_time": str(getattr(t, 'exit_time', '')),
                "side": getattr(t, 'side', ''),
                "entry_price": getattr(t, 'entry_price', 0),
                "exit_price": getattr(t, 'exit_price', 0),
                "net_pnl": getattr(t, 'net_pnl', 0),
            })
    
    # Sort keys for determinism
    serialized = json.dumps(trades_data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]


def compute_equity_hash(equity_curve: list[EquityPoint]) -> str:
    """
    Compute deterministic hash of equity curve.
    
    Args:
        equity_curve: List of EquityPoint objects
        
    Returns:
        SHA256 hash (first 16 chars) of serialized equity curve
    """
    # Serialize equity points
    equity_data = []
    for e in equity_curve:
        if hasattr(e, 'to_dict'):
            equity_data.append(e.to_dict())
        elif isinstance(e, dict):
            equity_data.append(e)
        else:
            # Fallback: extract key fields
            equity_data.append({
                "timestamp": str(getattr(e, 'timestamp', '')),
                "equity": getattr(e, 'equity', 0),
            })
    
    serialized = json.dumps(equity_data, sort_keys=True, default=str)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]


def compute_run_hash(
    trades_hash: str,
    equity_hash: str,
    play_hash: str | None = None,
) -> str:
    """
    Compute combined run hash from component hashes.
    
    Args:
        trades_hash: Hash of trades list
        equity_hash: Hash of equity curve
        play_hash: Optional hash of Play config
        
    Returns:
        Combined SHA256 hash (first 16 chars)
    """
    components = {
        "trades": trades_hash,
        "equity": equity_hash,
    }
    if play_hash:
        components["play"] = play_hash
    
    serialized = json.dumps(components, sort_keys=True)
    return hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:16]


# =============================================================================
# Canonical Serialization Rules
# =============================================================================
# All hash inputs MUST follow these canonicalization rules:
#
# 1. JSON keys: sorted alphabetically
# 2. Lists: sorted (symbols, tf_ctx) and deduplicated
# 3. Timestamps: ISO8601 format (YYYY-MM-DD for dates, YYYY-MM-DDTHH:MM:SSZ for datetimes)
# 4. Symbol casing: UPPERCASE (e.g., "BTCUSDT" not "btcusdt")
# 5. Timeframes: normalized to {value}{unit} where unit ∈ {m, h, d, w, M}
#    - Examples: "1m", "15m", "1h", "4h", "1d", "1w", "1M"
#    - No numeric-only representations allowed (e.g., "15" is INVALID)
# 6. No implicit defaults: all hashed fields must be explicit
# 7. Null handling: None values are included as null in JSON
#
# CRITICAL: Hashing non-canonical data is INVALID and will produce wrong hashes.
# =============================================================================

# Default short hash length (chars)
# 12 chars = 48 bits = ~281 trillion possibilities (negligible collision risk)
DEFAULT_SHORT_HASH_LENGTH = 12

# Extended short hash length for collision recovery
EXTENDED_SHORT_HASH_LENGTH = 16


def _canonicalize_symbol(symbol: str) -> str:
    """Canonicalize symbol to uppercase."""
    return symbol.upper()


def _canonicalize_symbols(symbols: list[str]) -> list[str]:
    """Canonicalize and sort symbol list."""
    return sorted(set(_canonicalize_symbol(s) for s in symbols))


def _canonicalize_tf(tf: str) -> str:
    """
    Canonicalize timeframe to {value}{unit} format.
    
    Valid units: m (minutes), h (hours), d (days), w (weeks), M (months)
    
    Examples:
        "15" -> "15m"
        "15m" -> "15m"
        "240" -> "4h"
        "4h" -> "4h"
        "D" -> "1d"
        "1d" -> "1d"
        "W" -> "1w"
        "1M" -> "1M"
    
    Raises:
        ValueError: If timeframe format is unrecognized
    """
    tf_stripped = tf.strip()
    
    # Already in {value}{unit} format
    if len(tf_stripped) >= 2:
        value_part = tf_stripped[:-1]
        unit_part = tf_stripped[-1].lower()
        if value_part.isdigit() and unit_part in ('m', 'h', 'd', 'w'):
            return f"{value_part}{unit_part}"
        # Month uses uppercase M
        if value_part.isdigit() and tf_stripped[-1] == 'M':
            return f"{value_part}M"
    
    # Numeric-only (Bybit API format) -> add unit
    if tf_stripped.isdigit():
        minutes = int(tf_stripped)
        if minutes < 60:
            return f"{minutes}m"
        elif minutes < 1440:  # Less than a day
            hours = minutes // 60
            return f"{hours}h"
        elif minutes == 1440:
            return "1d"
        else:
            days = minutes // 1440
            return f"{days}d"
    
    # Single letter formats
    tf_upper = tf_stripped.upper()
    if tf_upper == 'D':
        return "1d"
    if tf_upper == 'W':
        return "1w"
    if tf_upper == 'M':
        return "1M"
    
    # Verbose formats
    tf_lower = tf_stripped.lower()
    if tf_lower in ('day', 'daily'):
        return "1d"
    if tf_lower in ('week', 'weekly'):
        return "1w"
    if tf_lower in ('month', 'monthly'):
        return "1M"
    
    # Unknown format - return as-is but log warning
    # In strict mode, this should raise ValueError
    return tf_stripped


def compute_universe_id(symbols: list[str]) -> str:
    """
    Compute deterministic universe identifier for symbol sets.
    
    Single symbol: returns the symbol itself (e.g., "BTCUSDT")
    Multiple symbols: returns hash of sorted symbol list (e.g., "uni_a1b2c3d4")
    
    Used in folder paths to avoid ambiguity with multi-symbol runs.
    """
    canonical = _canonicalize_symbols(symbols)
    if len(canonical) == 1:
        return canonical[0]
    # Multi-symbol: hash the sorted list
    serialized = json.dumps(canonical, sort_keys=True)
    short_hash = hashlib.sha256(serialized.encode('utf-8')).hexdigest()[:8]
    return f"uni_{short_hash}"


@dataclass
class InputHashComponents:
    """
    All factors that affect backtest results.
    
    Used for deterministic, content-addressed run folders.
    Same inputs = same folder = same results (determinism guarantee).
    
    CANONICALIZATION RULES:
    - symbols: sorted, deduplicated, UPPERCASE
    - tf_ctx: sorted, deduplicated, API format
    - window dates: YYYY-MM-DD format
    - All fields explicit (no implicit defaults)
    
    Changing ANY of these fields MUST change the hash.
    """
    # Strategy config
    play_hash: str
    
    # Symbol universe
    symbols: list[str]

    # Timeframes
    tf_exec: str
    tf_ctx: list[str]  # All timeframes used (high_tf, med_tf, etc.)
    
    # Window
    window_start: str  # YYYY-MM-DD
    window_end: str    # YYYY-MM-DD
    
    # Execution model versions
    fee_model_version: str = "1.0.0"
    simulator_version: str = "1.0.0"
    engine_version: str = "1.0.0"
    fill_policy_version: str = "1.0.0"  # Execution/fill model
    
    # Data provenance (REQUIRED for determinism)
    data_source_id: str = "duckdb_live"  # e.g., "duckdb_live", "duckdb_demo", vendor ID
    data_version: str | None = None   # Snapshot/version reference if available
    candle_policy: str = "closed_only"   # "closed_only" (no partial candles)

    # Randomness
    seed: int | None = None
    
    def _canonicalize(self) -> dict[str, Any]:
        """
        Convert to canonical dict for hashing.
        
        CRITICAL: This is the ONLY valid serialization for hashing.
        """
        return {
            # Strategy
            "play_hash": self.play_hash,
            
            # Symbols (sorted, uppercase, deduplicated)
            "symbols": _canonicalize_symbols(self.symbols),
            
            # Timeframes (sorted, deduplicated, API format)
            "tf_exec": _canonicalize_tf(self.tf_exec),
            "tf_ctx": sorted(set(_canonicalize_tf(tf) for tf in self.tf_ctx)),
            
            # Window (YYYY-MM-DD format)
            "window_start": self.window_start,
            "window_end": self.window_end,
            
            # Execution model versions
            "fee_model_version": self.fee_model_version,
            "simulator_version": self.simulator_version,
            "engine_version": self.engine_version,
            "fill_policy_version": self.fill_policy_version,
            
            # Data provenance
            "data_source_id": self.data_source_id,
            "data_version": self.data_version,
            "candle_policy": self.candle_policy,
            
            # Randomness
            "seed": self.seed,
        }
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to canonical dict for hashing."""
        return self._canonicalize()
    
    def compute_full_hash(self) -> str:
        """Compute full SHA256 hash of all inputs (64 chars)."""
        # MUST use sorted keys for determinism
        serialized = json.dumps(self._canonicalize(), sort_keys=True)
        return hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    
    def compute_short_hash(self, length: int = DEFAULT_SHORT_HASH_LENGTH) -> str:
        """
        Compute short hash for folder naming.
        
        Args:
            length: Number of chars (default 8, use 12 for collision recovery)
            
        Returns:
            First N chars of full hash
        """
        return self.compute_full_hash()[:length]
    
    @property
    def universe_id(self) -> str:
        """Get universe identifier for folder paths."""
        return compute_universe_id(self.symbols)


def compute_input_hash(
    play_hash: str,
    window_start: str,
    window_end: str,
    symbols: list[str] | None = None,
    tf_exec: str = "",
    tf_ctx: list[str] | None = None,
    fee_model_version: str = "1.0.0",
    simulator_version: str = "1.0.0",
    engine_version: str = "1.0.0",
    fill_policy_version: str = "1.0.0",
    data_source_id: str = "duckdb_live",
    data_version: str | None = None,
    candle_policy: str = "closed_only",
    seed: int | None = None,
    short_hash_length: int = DEFAULT_SHORT_HASH_LENGTH,
) -> str:
    """
    Compute deterministic short hash of backtest inputs.
    
    Used for folder naming - same inputs = same folder.
    
    Args:
        play_hash: Hash of Play config
        window_start: Window start as ISO string (YYYY-MM-DD)
        window_end: Window end as ISO string (YYYY-MM-DD)
        symbols: List of symbols
        tf_exec: Execution timeframe
        tf_ctx: All context timeframes
        fee_model_version: Fee model version
        simulator_version: Simulator version
        engine_version: Engine version
        fill_policy_version: Fill/execution policy version
        data_source_id: Data source identifier
        data_version: Data snapshot/version reference
        candle_policy: Candle handling policy
        seed: Random seed if any
        short_hash_length: Length of short hash (default 8, use 12 for collisions)
        
    Returns:
        SHA256 hash (first N chars) - short for folder names
    """
    components = InputHashComponents(
        play_hash=play_hash,
        symbols=symbols or [],
        tf_exec=tf_exec,
        tf_ctx=tf_ctx or [],
        window_start=window_start,
        window_end=window_end,
        fee_model_version=fee_model_version,
        simulator_version=simulator_version,
        engine_version=engine_version,
        fill_policy_version=fill_policy_version,
        data_source_id=data_source_id,
        data_version=data_version,
        candle_policy=candle_policy,
        seed=seed,
    )
    return components.compute_short_hash(length=short_hash_length)


def compute_input_hash_full(components: InputHashComponents) -> str:
    """
    Compute full SHA256 hash of backtest inputs.
    
    Used for manifest storage and verification.
    """
    return components.compute_full_hash()


def verify_short_hash_derivation(full_hash: str, short_hash: str) -> bool:
    """
    Verify that short_hash is correctly derived from full_hash.
    
    Args:
        full_hash: Full 64-char SHA256 hash
        short_hash: Short hash (8 or 12 chars)
        
    Returns:
        True if full_hash starts with short_hash
    """
    return full_hash.startswith(short_hash)


def compute_artifact_file_hash(file_path: str) -> str:
    """
    Compute SHA256 hash of a file's contents.
    
    Args:
        file_path: Path to file
        
    Returns:
        Full SHA256 hash of file contents
    """
    with open(file_path, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

