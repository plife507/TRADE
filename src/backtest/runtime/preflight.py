"""
Data Preflight Gate: Validates data availability and quality before backtest.

This gate MUST pass before any backtest can run. It verifies:
1. Data exists for all required TFs + warmup buffer
2. Bars are continuous (no large gaps beyond threshold)
3. Timestamps are monotonic and unique
4. Bar alignment is sane (correct step intervals)

If data is missing, the gate can optionally trigger auto-fix via data tools.

TOOL DISCIPLINE (MANDATORY):
- Preflight auto-fix MUST call data tools (not "should" / not optional)
- Simulator/backtest MUST NOT modify DuckDB directly
- All adjustments MUST go through src/tools/data_tools.py (tools are the API surface)
- All tool calls MUST pass explicit parameters (no implicit defaults)
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from math import ceil
from pathlib import Path
from typing import Any, TYPE_CHECKING
import json
import pandas as pd
import numpy as np

if TYPE_CHECKING:
    from ..execution_validation import WarmupRequirements


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class PreflightStatus(str, Enum):
    """Preflight check status."""
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"


@dataclass
class ToolCallRecord:
    """Record of a tool call made during auto-fix."""
    tool_name: str
    params: dict[str, Any]
    success: bool
    message: str = ""
    timestamp: datetime = field(default_factory=_utcnow)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "tool_name": self.tool_name,
            "params": self.params,
            "success": self.success,
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AutoSyncConfig:
    """Configuration for auto-sync behavior during preflight."""
    enabled: bool = False
    max_attempts: int = 2
    data_env: str = "live"  # "live" or "demo"

    # Tool hooks for dependency injection (used in testing)
    sync_range_tool: Callable | None = None
    fill_gaps_tool: Callable | None = None
    heal_data_tool: Callable | None = None


@dataclass
class AutoSyncResult:
    """Result of auto-sync attempt."""
    attempted: bool = False
    success: bool = False
    tool_calls: list[ToolCallRecord] = field(default_factory=list)
    attempts_made: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "attempted": self.attempted,
            "success": self.success,
            "attempts_made": self.attempts_made,
            "tool_calls": [tc.to_dict() for tc in self.tool_calls],
        }


@dataclass
class GapInfo:
    """Information about a detected gap in data."""
    start_ts: datetime
    end_ts: datetime
    expected_bars: int
    actual_bars: int
    gap_duration_minutes: float
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat(),
            "expected_bars": self.expected_bars,
            "actual_bars": self.actual_bars,
            "gap_duration_minutes": self.gap_duration_minutes,
        }


def _datetime_to_epoch_ms(dt: datetime | None) -> int | None:
    """Convert datetime to epoch milliseconds."""
    if dt is None:
        return None
    # Handle both aware and naive datetimes
    if dt.tzinfo is not None:
        return int(dt.timestamp() * 1000)
    # Assume naive datetime is UTC
    return int(dt.replace(tzinfo=timezone.utc).timestamp() * 1000)


@dataclass
class TFPreflightResult:
    """Preflight result for a single (symbol, tf) pair."""
    symbol: str
    tf: str
    status: PreflightStatus

    # Coverage info
    min_ts: datetime | None = None
    max_ts: datetime | None = None
    bar_count: int = 0

    # Required range
    required_start: datetime | None = None
    required_end: datetime | None = None
    warmup_bars: int = 0

    # Validation results
    data_exists: bool = False
    covers_range: bool = False
    is_monotonic: bool = False
    is_unique: bool = False
    alignment_ok: bool = False

    # Gaps
    gaps: list[GapInfo] = field(default_factory=list)
    max_gap_minutes: float = 0.0
    gap_threshold_minutes: float = 0.0
    gaps_within_threshold: bool = True

    # Errors
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "symbol": self.symbol,
            "tf": self.tf,
            "status": self.status.value,
            "coverage": {
                "min_ts": self.min_ts.isoformat() if self.min_ts else None,
                "max_ts": self.max_ts.isoformat() if self.max_ts else None,
                "bar_count": self.bar_count,
                # Phase 6: Add epoch-ms fields for smoke test assertions
                "db_start_ts_ms": _datetime_to_epoch_ms(self.min_ts),
                "db_end_ts_ms": _datetime_to_epoch_ms(self.max_ts),
                "ok": self.covers_range,
            },
            "required_range": {
                "start": self.required_start.isoformat() if self.required_start else None,
                "end": self.required_end.isoformat() if self.required_end else None,
                "warmup_bars": self.warmup_bars,
                # Phase 6: Add epoch-ms fields for smoke test assertions
                "start_ts_ms": _datetime_to_epoch_ms(self.required_start),
                "end_ts_ms": _datetime_to_epoch_ms(self.required_end),
            },
            "validation": {
                "data_exists": self.data_exists,
                "covers_range": self.covers_range,
                "is_monotonic": self.is_monotonic,
                "is_unique": self.is_unique,
                "alignment_ok": self.alignment_ok,
                "gaps_within_threshold": self.gaps_within_threshold,
            },
            "gaps": {
                "count": len(self.gaps),
                "max_gap_minutes": self.max_gap_minutes,
                "threshold_minutes": self.gap_threshold_minutes,
                "details": [g.to_dict() for g in self.gaps[:10]],  # Limit to first 10
            },
            "errors": self.errors,
            "warnings": self.warnings,
        }


@dataclass
class PreflightReport:
    """Complete preflight report for all TFs."""
    play_id: str
    window_start: datetime
    window_end: datetime
    overall_status: PreflightStatus
    tf_results: dict[str, TFPreflightResult]  # key: "symbol:tf"
    run_timestamp: datetime = field(default_factory=_utcnow)
    auto_sync_result: AutoSyncResult | None = None
    # Computed warmup requirements (source of truth from Play indicators)
    computed_warmup_requirements: "WarmupRequirements | None" = None
    # Phase 6: Error classification for structured smoke test assertions
    error_code: str | None = None  # e.g., "INSUFFICIENT_COVERAGE", "HISTORY_UNAVAILABLE", "MISSING_1M_COVERAGE"
    error_details: dict[str, Any] | None = None
    # 1m Price Feed: Mandatory 1m coverage fields
    has_1m_coverage: bool = False
    exec_to_1m_mapping_feasible: bool = False
    required_1m_bars: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "play_id": self.play_id,
            "window": {
                "start": self.window_start.isoformat(),
                "end": self.window_end.isoformat(),
            },
            "overall_status": self.overall_status.value,
            "run_timestamp": self.run_timestamp.isoformat(),
            "tf_results": {k: v.to_dict() for k, v in self.tf_results.items()},
        }
        if self.auto_sync_result:
            result["auto_sync"] = self.auto_sync_result.to_dict()
        if self.computed_warmup_requirements:
            result["computed_warmup_requirements"] = self.computed_warmup_requirements.to_dict()
        
        # Phase 6: Add top-level fields for smoke test assertions
        # Extract exec role required_range and coverage from tf_results
        exec_result = self._get_exec_result()
        if exec_result:
            result["required_range"] = {
                "start_ts_ms": _datetime_to_epoch_ms(exec_result.required_start),
                "end_ts_ms": _datetime_to_epoch_ms(exec_result.required_end),
            }
            result["coverage"] = {
                "db_start_ts_ms": _datetime_to_epoch_ms(exec_result.min_ts),
                "db_end_ts_ms": _datetime_to_epoch_ms(exec_result.max_ts),
                "ok": exec_result.covers_range,
            }
        
        # Phase 6: Error classification
        if self.error_code:
            result["error_code"] = self.error_code
        if self.error_details:
            result["error_details"] = self.error_details

        # 1m Price Feed: Add 1m coverage fields
        result["price_feed_1m"] = {
            "has_1m_coverage": self.has_1m_coverage,
            "exec_to_1m_mapping_feasible": self.exec_to_1m_mapping_feasible,
            "required_1m_bars": self.required_1m_bars,
        }

        return result
    
    def _get_exec_result(self) -> TFPreflightResult | None:
        """Get the exec role TFPreflightResult (first result if only one symbol)."""
        for key, tf_result in self.tf_results.items():
            # Return first result (typically exec TF for single-symbol runs)
            return tf_result
        return None
    
    def write_json(self, path: Path) -> None:
        """Write report to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, sort_keys=True)
    
    def print_summary(self) -> None:
        """Print summary to console."""
        status_icon = "[OK]" if self.overall_status == PreflightStatus.PASSED else "[FAIL]"
        print(f"\n{status_icon} Preflight Gate: {self.overall_status.value.upper()}")
        print(f"   Play: {self.play_id}")
        print(f"   Window: {self.window_start.date()} -> {self.window_end.date()}")
        print()

        # 1m Price Feed status
        pf_icon = "[OK]" if self.has_1m_coverage else "[FAIL]"
        print(f"   {pf_icon} 1m coverage: {'OK' if self.has_1m_coverage else 'MISSING'} ({self.required_1m_bars} bars required)")
        map_icon = "[OK]" if self.exec_to_1m_mapping_feasible else "[FAIL]"
        print(f"   {map_icon} exec->1m mapping: {'OK' if self.exec_to_1m_mapping_feasible else 'FAILED'}")
        print()

        for key, result in self.tf_results.items():
            tf_icon = "[OK]" if result.status == PreflightStatus.PASSED else "[FAIL]"
            print(f"   {tf_icon} {result.symbol} {result.tf}:")
            print(f"      Bars: {result.bar_count} | Range: {result.min_ts} -> {result.max_ts}")
            if result.errors:
                for err in result.errors:
                    print(f"      [ERR] {err}")
            if result.warnings:
                for warn in result.warnings:
                    print(f"      [WARN] {warn}")
        print()


def parse_tf_to_minutes(tf: str) -> int:
    """
    Parse timeframe string to minutes.

    Supports: 1m, 5m, 15m, 30m, 1h, 4h, D (1d), W (1w)
    Also supports single-letter formats: D, W (treated as 1D, 1W)
    """
    tf = tf.lower().strip()

    if tf.endswith("m"):
        return int(tf[:-1])
    elif tf.endswith("h"):
        return int(tf[:-1]) * 60
    elif tf.endswith("d"):
        prefix = tf[:-1]
        return (int(prefix) if prefix else 1) * 60 * 24
    elif tf.endswith("w"):
        prefix = tf[:-1]
        return (int(prefix) if prefix else 1) * 60 * 24 * 7
    else:
        raise ValueError(f"Unknown timeframe format: {tf}")


def calculate_warmup_start(
    window_start: datetime,
    warmup_bars: int,
    tf_minutes: int,
) -> datetime:
    """
    Calculate the start timestamp including warmup buffer.
    
    Note: This is a legacy wrapper. New code should use
    compute_warmup_start_simple() from windowing.py.
    """
    from .windowing import compute_warmup_start_simple
    # Convert tf_minutes to tf string for the canonical function
    # Common cases: 1, 5, 15, 60, 240, 1440
    if tf_minutes < 60:
        tf = f"{tf_minutes}m"
    elif tf_minutes < 1440:
        hours = tf_minutes // 60
        tf = f"{hours}h"
    elif tf_minutes == 1440:
        tf = "D"  # Bybit format
    elif tf_minutes == 10080:
        tf = "W"  # Bybit format
    else:
        # Fallback: treat as minutes
        tf = f"{tf_minutes}m"
    return compute_warmup_start_simple(window_start, warmup_bars, tf)


def validate_tf_data(
    df: pd.DataFrame,
    symbol: str,
    tf: str,
    required_start: datetime,
    required_end: datetime,
    warmup_bars: int = 0,
    gap_threshold_multiplier: float = 3.0,
) -> TFPreflightResult:
    """
    Validate data for a single (symbol, tf) pair.
    
    Args:
        df: DataFrame with OHLCV data (must have 'timestamp' column)
        symbol: Trading symbol
        tf: Timeframe string
        required_start: Start of required range
        required_end: End of required range
        warmup_bars: Number of warmup bars needed before required_start
        gap_threshold_multiplier: Gaps larger than this * tf_minutes are flagged
        
    Returns:
        TFPreflightResult with validation results
    """
    tf_minutes = parse_tf_to_minutes(tf)
    gap_threshold_minutes = tf_minutes * gap_threshold_multiplier
    
    # Calculate effective start with warmup
    effective_start = calculate_warmup_start(required_start, warmup_bars, tf_minutes)
    
    result = TFPreflightResult(
        symbol=symbol,
        tf=tf,
        status=PreflightStatus.FAILED,  # Default to failed, set to passed if all checks pass
        required_start=effective_start,
        required_end=required_end,
        warmup_bars=warmup_bars,
        gap_threshold_minutes=gap_threshold_minutes,
    )
    
    # Check 1: Data exists
    if df is None or df.empty:
        result.errors.append("No data available")
        return result
    
    result.data_exists = True
    
    # Ensure timestamp column exists and is datetime
    if "timestamp" not in df.columns:
        result.errors.append("Missing 'timestamp' column")
        return result
    
    # Sort by timestamp
    df = df.sort_values("timestamp").reset_index(drop=True)
    
    # Get coverage (normalize to naive for comparison - DuckDB returns naive timestamps)
    min_ts = pd.Timestamp(df["timestamp"].min()).to_pydatetime()
    max_ts = pd.Timestamp(df["timestamp"].max()).to_pydatetime()
    result.min_ts = min_ts
    result.max_ts = max_ts
    result.bar_count = len(df)
    
    # Normalize datetimes to naive for comparison (DuckDB stores as UTC naive)
    eff_start_cmp = effective_start.replace(tzinfo=None) if effective_start.tzinfo else effective_start
    req_end_cmp = required_end.replace(tzinfo=None) if required_end.tzinfo else required_end

    # Check 2: Covers required range
    # - min_ts <= eff_start_cmp: data starts at or before required start (for warmup)
    # - max_ts + bar_duration >= req_end_cmp: last bar covers required end
    # Note: max_ts is the START of the last bar, not its end. A 4h bar starting at 20:00
    # covers data through 00:00. We add tf_minutes to get effective coverage end.
    bar_duration = timedelta(minutes=tf_minutes)
    effective_end_coverage = max_ts + bar_duration

    if min_ts <= eff_start_cmp and effective_end_coverage >= req_end_cmp:
        result.covers_range = True
    else:
        if min_ts > eff_start_cmp:
            result.errors.append(
                f"Data starts too late: {min_ts} > {eff_start_cmp} (need {warmup_bars} warmup bars)"
            )
        if effective_end_coverage < req_end_cmp:
            result.errors.append(
                f"Data ends too early: last bar at {max_ts} covers until {effective_end_coverage}, need {req_end_cmp}"
            )
    
    # Check 3: Timestamps are monotonic
    ts_diff = df["timestamp"].diff().dropna()
    if (ts_diff <= pd.Timedelta(0)).any():
        result.errors.append("Timestamps are not strictly monotonic")
    else:
        result.is_monotonic = True
    
    # Check 4: Timestamps are unique
    if df["timestamp"].duplicated().any():
        dup_count = df["timestamp"].duplicated().sum()
        result.errors.append(f"Found {dup_count} duplicate timestamps")
    else:
        result.is_unique = True
    
    # Check 5: Alignment sanity (step intervals)
    expected_step = pd.Timedelta(minutes=tf_minutes)
    # Check most common step matches expected
    if len(ts_diff) > 0:
        mode_step = ts_diff.mode()
        if len(mode_step) > 0:
            actual_step = mode_step.iloc[0]
            if actual_step != expected_step:
                result.warnings.append(
                    f"Most common step {actual_step} != expected {expected_step}"
                )
            else:
                result.alignment_ok = True
    
    # Check 6: Detect gaps
    gap_threshold = pd.Timedelta(minutes=gap_threshold_minutes)
    large_gaps = ts_diff[ts_diff > gap_threshold]
    
    if len(large_gaps) > 0:
        for idx in large_gaps.index:
            gap_start = df.loc[idx - 1, "timestamp"]
            gap_end = df.loc[idx, "timestamp"]
            gap_duration = (gap_end - gap_start).total_seconds() / 60
            expected_bars = int(gap_duration / tf_minutes)
            
            result.gaps.append(GapInfo(
                start_ts=pd.Timestamp(gap_start).to_pydatetime(),
                end_ts=pd.Timestamp(gap_end).to_pydatetime(),
                expected_bars=expected_bars,
                actual_bars=1,
                gap_duration_minutes=gap_duration,
            ))
        
        result.max_gap_minutes = max(g.gap_duration_minutes for g in result.gaps)
        result.gaps_within_threshold = False
        result.warnings.append(
            f"Found {len(result.gaps)} gaps exceeding {gap_threshold_minutes} minutes"
        )
    else:
        result.gaps_within_threshold = True
    
    # Determine overall status
    if result.errors:
        result.status = PreflightStatus.FAILED
    elif result.warnings:
        result.status = PreflightStatus.WARNING
    else:
        result.status = PreflightStatus.PASSED
    
    # Override to FAILED if critical checks fail
    if not result.covers_range or not result.is_monotonic or not result.is_unique:
        result.status = PreflightStatus.FAILED
    
    return result


def _get_default_tools() -> tuple[Callable, Callable, Callable]:
    """
    Get the default data tools for auto-sync.
    
    Returns:
        Tuple of (sync_range_tool, fill_gaps_tool, heal_data_tool)
        
    These are imported lazily to avoid circular imports and allow
    dependency injection in tests.
    """
    from src.tools.data_tools import sync_range_tool, fill_gaps_tool, heal_data_tool
    return sync_range_tool, fill_gaps_tool, heal_data_tool


def _run_auto_sync(
    pairs_to_sync: list[tuple[str, str, datetime, datetime]],
    auto_sync_config: AutoSyncConfig,
) -> AutoSyncResult:
    """
    Run auto-sync for failed TF pairs via data tools.
    
    TOOL DISCIPLINE:
    - All data fixes MUST go through tools (sync_range_tool, fill_gaps_tool, heal_data_tool)
    - Simulator/backtest MUST NOT modify DuckDB directly
    - All tool calls MUST pass explicit parameters (no implicit defaults)
    
    Args:
        pairs_to_sync: List of (symbol, tf, start, end) tuples that need sync
        auto_sync_config: Configuration for auto-sync behavior
        
    Returns:
        AutoSyncResult with tool call records
    """
    result = AutoSyncResult(attempted=True)
    
    # Get tools (from config for DI, or default imports)
    if auto_sync_config.sync_range_tool:
        sync_range = auto_sync_config.sync_range_tool
    else:
        sync_range, _, _ = _get_default_tools()
    
    if auto_sync_config.fill_gaps_tool:
        fill_gaps = auto_sync_config.fill_gaps_tool
    else:
        _, fill_gaps, _ = _get_default_tools()
    
    if auto_sync_config.heal_data_tool:
        heal_data = auto_sync_config.heal_data_tool
    else:
        _, _, heal_data = _get_default_tools()
    
    data_env = auto_sync_config.data_env
    
    # Group by symbol for batching
    symbols_tfs: dict[str, list[tuple[str, datetime, datetime]]] = {}
    for symbol, tf, start, end in pairs_to_sync:
        if symbol not in symbols_tfs:
            symbols_tfs[symbol] = []
        symbols_tfs[symbol].append((tf, start, end))
    
    # Step 1: Sync missing data ranges via sync_range_tool
    for symbol, tf_ranges in symbols_tfs.items():
        for tf, start, end in tf_ranges:
            # EXPLICIT parameters - no implicit defaults
            params = {
                "symbols": [symbol],
                "start": start,
                "end": end,
                "timeframes": [tf],
                "env": data_env,
            }
            
            try:
                tool_result = sync_range(**params)
                record = ToolCallRecord(
                    tool_name="sync_range_tool",
                    params={k: str(v) if isinstance(v, datetime) else v for k, v in params.items()},
                    success=tool_result.success,
                    message=tool_result.message if tool_result.success else (tool_result.error or ""),
                )
            except Exception as e:
                record = ToolCallRecord(
                    tool_name="sync_range_tool",
                    params={k: str(v) if isinstance(v, datetime) else v for k, v in params.items()},
                    success=False,
                    message=f"Exception: {str(e)}",
                )
            
            result.tool_calls.append(record)
    
    # Step 2: Fill gaps via fill_gaps_tool
    for symbol in symbols_tfs.keys():
        for tf, _, _ in symbols_tfs[symbol]:
            # EXPLICIT parameters
            params = {
                "symbol": symbol,
                "timeframe": tf,
                "env": data_env,
            }
            
            try:
                tool_result = fill_gaps(**params)
                record = ToolCallRecord(
                    tool_name="fill_gaps_tool",
                    params=params,
                    success=tool_result.success,
                    message=tool_result.message if tool_result.success else (tool_result.error or ""),
                )
            except Exception as e:
                record = ToolCallRecord(
                    tool_name="fill_gaps_tool",
                    params=params,
                    success=False,
                    message=f"Exception: {str(e)}",
                )
            
            result.tool_calls.append(record)
    
    # Step 3: Heal data via heal_data_tool
    for symbol in symbols_tfs.keys():
        # EXPLICIT parameters
        params = {
            "symbol": symbol,
            "fix_issues": True,
            "fill_gaps_after": False,  # Already filled gaps
            "env": data_env,
        }
        
        try:
            tool_result = heal_data(**params)
            record = ToolCallRecord(
                tool_name="heal_data_tool",
                params=params,
                success=tool_result.success,
                message=tool_result.message if tool_result.success else (tool_result.error or ""),
            )
        except Exception as e:
            record = ToolCallRecord(
                tool_name="heal_data_tool",
                params=params,
                success=False,
                message=f"Exception: {str(e)}",
            )
        
        result.tool_calls.append(record)
    
    # Determine overall success (all tool calls succeeded)
    result.success = all(tc.success for tc in result.tool_calls)
    result.attempts_made = 1
    
    return result


def _validate_all_pairs(
    pairs_to_check: list[tuple[str, str, int]],
    data_loader: "DataLoader",
    window_start: datetime,
    window_end: datetime,
    gap_threshold_multiplier: float,
) -> tuple[dict[str, TFPreflightResult], list[tuple[str, str, datetime, datetime]]]:
    """
    Validate all (symbol, tf) pairs and collect failures.
    
    Returns:
        Tuple of (tf_results dict, list of failed pairs needing sync)
    """
    tf_results: dict[str, TFPreflightResult] = {}
    failed_pairs: list[tuple[str, str, datetime, datetime]] = []
    
    for symbol, tf, warmup_bars in pairs_to_check:
        key = f"{symbol}:{tf}"

        # Compute the effective required start including warmup for this TF
        tf_minutes = parse_tf_to_minutes(tf)
        effective_start = calculate_warmup_start(window_start, warmup_bars, tf_minutes)
        
        # Load data
        try:
            df = data_loader(symbol, tf, effective_start, window_end)
        except Exception as e:
            result = TFPreflightResult(
                symbol=symbol,
                tf=tf,
                status=PreflightStatus.FAILED,
                errors=[f"Failed to load data: {str(e)}"],
            )
            result.required_start = effective_start
            result.required_end = window_end
            result.warmup_bars = warmup_bars
            tf_results[key] = result
            failed_pairs.append((symbol, tf, effective_start, window_end))
            continue
        
        # Validate
        result = validate_tf_data(
            df=df,
            symbol=symbol,
            tf=tf,
            required_start=window_start,
            required_end=window_end,
            warmup_bars=warmup_bars,
            gap_threshold_multiplier=gap_threshold_multiplier,
        )
        
        tf_results[key] = result
        
        if result.status == PreflightStatus.FAILED:
            failed_pairs.append((symbol, tf, effective_start, window_end))
    
    return tf_results, failed_pairs


def _compute_safety_buffer(warmup_bars: int) -> int:
    """
    Compute safety buffer for warmup data fetch.

    Formula: max(10, ceil(warmup_bars * 0.05))

    This ensures we fetch a bit more data than strictly required,
    providing margin for edge cases without excessive over-fetching.
    """
    return max(10, ceil(warmup_bars * 0.05))


def _validate_exec_to_1m_mapping(
    exec_tf: str,
    window_start: datetime,
    window_end: datetime,
    df_1m: pd.DataFrame | None,
) -> tuple[bool, str | None]:
    """
    Validate that exec TF close times can be mapped to 1m bars.

    For each exec TF close time in the backtest window, verify that a 1m bar
    exists at-or-before that close time (for use as quote/ticker proxy).

    Mapping rule: exec_close_ts → floor(exec_close_ts / 60000) * 60000
    (i.e., round down to nearest 1m bar close)

    Args:
        exec_tf: Execution timeframe (e.g., "15m", "5m")
        window_start: Backtest window start
        window_end: Backtest window end
        df_1m: DataFrame with 1m bars (must have 'timestamp' column)

    Returns:
        Tuple of (mapping_ok, error_message)
    """
    if df_1m is None or df_1m.empty:
        return False, "No 1m data available for exec→1m mapping"

    if "timestamp" not in df_1m.columns:
        return False, "1m data missing 'timestamp' column"

    exec_minutes = parse_tf_to_minutes(exec_tf)

    # Get 1m timestamps as epoch ms for fast lookup
    df_1m_sorted = df_1m.sort_values("timestamp")
    ts_1m_array = df_1m_sorted["timestamp"].values

    # Convert to epoch ms for comparison
    # Handle both datetime objects and numpy datetime64
    if len(ts_1m_array) == 0:
        return False, "Empty 1m data array"

    # Convert to pandas Timestamp for reliable epoch ms conversion
    ts_1m_epoch_ms = np.array([
        int(pd.Timestamp(ts).timestamp() * 1000) for ts in ts_1m_array
    ])

    # Build set of available 1m close times (for O(1) lookup)
    available_1m_set = set(ts_1m_epoch_ms)

    # Calculate exec bar close times in the backtest window
    # Start from first exec close at-or-after window_start
    # Normalize to naive UTC for calculation
    ws = window_start.replace(tzinfo=None) if window_start.tzinfo else window_start
    we = window_end.replace(tzinfo=None) if window_end.tzinfo else window_end

    ws_epoch_ms = int(ws.replace(tzinfo=timezone.utc).timestamp() * 1000)
    we_epoch_ms = int(we.replace(tzinfo=timezone.utc).timestamp() * 1000)
    exec_ms = exec_minutes * 60 * 1000

    # Align to first exec close at-or-after window_start
    first_exec_close_ms = ((ws_epoch_ms // exec_ms) + 1) * exec_ms

    # Check each exec close time has a corresponding 1m bar
    missing_mappings = []
    current_exec_ms = first_exec_close_ms

    while current_exec_ms <= we_epoch_ms:
        # Mapping rule: exec close → floor to nearest 1m
        mapped_1m_ms = (current_exec_ms // 60000) * 60000

        if mapped_1m_ms not in available_1m_set:
            # Check if there's a 1m bar just before (within 1m window)
            # This handles edge case where exec close aligns exactly with 1m close
            found_nearby = False
            for offset_ms in [0, -60000]:  # Check exact match and 1 bar before
                if (mapped_1m_ms + offset_ms) in available_1m_set:
                    found_nearby = True
                    break

            if not found_nearby:
                missing_ts = datetime.fromtimestamp(current_exec_ms / 1000, tz=timezone.utc)
                missing_mappings.append(missing_ts)

                # Stop after finding first few missing (avoid huge list)
                if len(missing_mappings) >= 5:
                    break

        current_exec_ms += exec_ms

    if missing_mappings:
        first_missing = missing_mappings[0].strftime("%Y-%m-%d %H:%M")
        return False, (
            f"Missing 1m bars for {len(missing_mappings)}+ exec TF close times. "
            f"First missing: {first_missing} (exec TF={exec_tf})"
        )

    return True, None


def run_preflight_gate(
    play: "Play",
    data_loader: "DataLoader",
    window_start: datetime,
    window_end: datetime,
    gap_threshold_multiplier: float = 3.0,
    auto_sync_missing: bool = False,
    auto_sync_config: AutoSyncConfig | None = None,
) -> PreflightReport:
    """
    Run the data preflight gate for an Play.
    
    WARMUP COMPUTATION (SINGLE SOURCE OF TRUTH):
    - Calls compute_warmup_requirements(play) EXACTLY ONCE at the start
    - Stores result in PreflightReport.computed_warmup_requirements
    - All downstream warmup usage (coverage check, backfill) uses this computed value
    - Runner and Engine MUST NOT recompute warmup - they consume this output
    
    TOOL DISCIPLINE (MANDATORY):
    - When auto_sync_missing=True, preflight MUST call data tools to fix issues
    - All data fixes go through sync_range_tool, fill_gaps_tool, heal_data_tool
    - Simulator/backtest MUST NOT modify DuckDB directly
    
    Args:
        play: The Play to validate data for
        data_loader: Callable that loads data for (symbol, tf, start, end) -> DataFrame
        window_start: Backtest window start
        window_end: Backtest window end
        gap_threshold_multiplier: Gaps larger than this * tf_minutes are flagged
        auto_sync_missing: If True, attempt to sync missing data via tools
        auto_sync_config: Configuration for auto-sync (optional, uses defaults)
        
    Returns:
        PreflightReport with all validation results, auto_sync info, and computed_warmup_requirements
    """
    from ..execution_validation import (
        compute_warmup_requirements,
        EARLIEST_BYBIT_DATE_YEAR,
        EARLIEST_BYBIT_DATE_MONTH,
    )
    
    # ==========================================================================
    # STEP 0: Validate window dates (P2.2: prevent impossible data requests)
    # ==========================================================================
    earliest_date = datetime(EARLIEST_BYBIT_DATE_YEAR, EARLIEST_BYBIT_DATE_MONTH, 1, tzinfo=timezone.utc)
    # Ensure window dates are timezone-aware for comparison
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    if window_start < earliest_date:
        raise ValueError(
            f"Window start ({window_start.date()}) is before earliest available Bybit data "
            f"({earliest_date.date()}). Adjust window_start to a later date."
        )
    if window_end <= window_start:
        raise ValueError(
            f"Window end ({window_end.date()}) must be after window start ({window_start.date()})."
        )
    
    # ==========================================================================
    # STEP 1: Compute warmup requirements ONCE from Play (SOURCE OF TRUTH)
    # ==========================================================================
    
    warmup_requirements = compute_warmup_requirements(play)
    
    # Validate that warmup doesn't push data start before earliest available data
    # In new schema, use feature_registry to get all TFs
    try:
        all_tfs = play.feature_registry.get_all_tfs()
    except Exception:
        all_tfs = {play.execution_tf} if play.execution_tf else set()

    for tf in all_tfs:
        warmup = warmup_requirements.warmup_by_role.get(tf, 0)
        safety = _compute_safety_buffer(warmup)
        total_warmup = warmup + safety
        tf_minutes = parse_tf_to_minutes(tf)
        data_start = window_start - timedelta(minutes=total_warmup * tf_minutes)
        if data_start < earliest_date:
            raise ValueError(
                f"Warmup for {tf} TF ({total_warmup} bars) would require data "
                f"starting {data_start.date()}, which is before earliest available Bybit data "
                f"({earliest_date.date()}). Reduce warmup_bars or use a later window_start."
            )
    
    # ==========================================================================
    # STEP 2: Collect all (symbol, tf) pairs with computed warmup
    # ==========================================================================
    pairs_to_check: list[tuple[str, str, int]] = []  # (symbol, tf, warmup_bars)

    for symbol in play.symbol_universe:
        for tf in all_tfs:
            # Use computed warmup from WarmupRequirements
            warmup = warmup_requirements.warmup_by_role.get(tf, 0)
            # Add safety buffer
            safety_buffer = _compute_safety_buffer(warmup)
            warmup_with_buffer = warmup + safety_buffer
            pairs_to_check.append((symbol, tf, warmup_with_buffer))

    # ==========================================================================
    # STEP 2.5: Add mandatory 1m coverage check for all symbols
    # ==========================================================================
    # 1m is required as a quote/ticker proxy for simulator. Coverage must exist
    # for the full backtest window including max warmup across all roles.
    # The 1m warmup is calculated as: max warmup bars across all roles, converted to 1m.

    # Check if 1m is already declared (skip if already in pairs)
    declared_tfs = {tf.lower() for tf in all_tfs}

    if "1m" not in declared_tfs:
        # Calculate 1m warmup: max warmup across all roles, converted to 1m bars
        max_warmup_minutes = 0
        for tf in all_tfs:
            role_warmup = warmup_requirements.warmup_by_role.get(tf, 0)
            tf_minutes = parse_tf_to_minutes(tf)
            warmup_minutes = role_warmup * tf_minutes
            max_warmup_minutes = max(max_warmup_minutes, warmup_minutes)

        # Convert to 1m bars
        warmup_1m_bars = max_warmup_minutes  # 1m = 1 minute per bar
        safety_buffer_1m = _compute_safety_buffer(warmup_1m_bars)
        warmup_1m_with_buffer = warmup_1m_bars + safety_buffer_1m

        # Add 1m to pairs for each symbol
        for symbol in play.symbol_universe:
            pairs_to_check.append((symbol, "1m", warmup_1m_with_buffer))
    
    # First validation pass
    tf_results, failed_pairs = _validate_all_pairs(
        pairs_to_check=pairs_to_check,
        data_loader=data_loader,
        window_start=window_start,
        window_end=window_end,
        gap_threshold_multiplier=gap_threshold_multiplier,
    )
    
    auto_sync_result: AutoSyncResult | None = None
    
    # If there are failures and auto-sync is enabled, try to fix
    if failed_pairs and auto_sync_missing:
        # Build auto-sync config
        if auto_sync_config is None:
            auto_sync_config = AutoSyncConfig(enabled=True)
        else:
            auto_sync_config.enabled = True
        
        max_attempts = auto_sync_config.max_attempts
        attempt = 0
        
        while failed_pairs and attempt < max_attempts:
            attempt += 1
            
            # Run auto-sync via tools
            sync_result = _run_auto_sync(
                pairs_to_sync=failed_pairs,
                auto_sync_config=auto_sync_config,
            )
            sync_result.attempts_made = attempt
            
            # Accumulate tool calls
            if auto_sync_result is None:
                auto_sync_result = sync_result
            else:
                auto_sync_result.tool_calls.extend(sync_result.tool_calls)
                auto_sync_result.attempts_made = attempt
            
            # Re-validate after sync
            tf_results, failed_pairs = _validate_all_pairs(
                pairs_to_check=pairs_to_check,
                data_loader=data_loader,
                window_start=window_start,
                window_end=window_end,
                gap_threshold_multiplier=gap_threshold_multiplier,
            )
            
            # Update success based on re-validation
            auto_sync_result.success = len(failed_pairs) == 0
            
            if not failed_pairs:
                break
    
    # ==========================================================================
    # STEP 3: Determine 1m coverage status and exec→1m mapping feasibility
    # ==========================================================================
    # Check if 1m data exists for all symbols and covers required range
    has_1m_coverage = True
    required_1m_bars = 0

    for symbol in play.symbol_universe:
        key_1m = f"{symbol}:1m"
        if key_1m in tf_results:
            result_1m = tf_results[key_1m]
            required_1m_bars = max(required_1m_bars, result_1m.warmup_bars + result_1m.bar_count)
            if result_1m.status == PreflightStatus.FAILED:
                has_1m_coverage = False
        else:
            # 1m not in results means it wasn't checked (shouldn't happen now)
            has_1m_coverage = False

    # Validate exec→1m mapping feasibility
    exec_to_1m_mapping_feasible = True
    mapping_error: str | None = None

    if has_1m_coverage:
        # Get exec TF from Play (new schema uses execution_tf directly)
        exec_tf_str = play.execution_tf
        if exec_tf_str:
            # Load 1m data for mapping validation
            for symbol in play.symbol_universe:
                key_1m = f"{symbol}:1m"
                result_1m = tf_results.get(key_1m)
                if result_1m and result_1m.data_exists:
                    # Need to re-load 1m data for mapping check
                    try:
                        tf_minutes = parse_tf_to_minutes("1m")
                        effective_start_1m = calculate_warmup_start(
                            window_start, result_1m.warmup_bars, tf_minutes
                        )
                        df_1m = data_loader(symbol, "1m", effective_start_1m, window_end)
                        mapping_ok, err = _validate_exec_to_1m_mapping(
                            exec_tf=exec_tf_str,
                            window_start=window_start,
                            window_end=window_end,
                            df_1m=df_1m,
                        )
                        if not mapping_ok:
                            exec_to_1m_mapping_feasible = False
                            mapping_error = err
                            break
                    except Exception as e:
                        exec_to_1m_mapping_feasible = False
                        mapping_error = f"Failed to validate exec→1m mapping: {str(e)}"
                        break
                else:
                    exec_to_1m_mapping_feasible = False
                    mapping_error = f"1m data not available for {symbol}"
                    break

    # Determine overall status
    overall_passed = all(
        r.status != PreflightStatus.FAILED
        for r in tf_results.values()
    )

    # 1m coverage and mapping are now hard requirements
    if not has_1m_coverage or not exec_to_1m_mapping_feasible:
        overall_passed = False

    # Phase 6: Classify error for structured smoke test assertions
    error_code: str | None = None
    error_details: dict[str, Any] | None = None

    if not overall_passed:
        # Check 1m-specific failures first (highest priority)
        if not has_1m_coverage:
            error_code = "MISSING_1M_COVERAGE"
            # Find the failing 1m result
            for symbol in play.symbol_universe:
                key_1m = f"{symbol}:1m"
                result_1m = tf_results.get(key_1m)
                if result_1m and result_1m.status == PreflightStatus.FAILED:
                    error_details = {
                        "symbol": symbol,
                        "tf": "1m",
                        "reason": "missing_1m_data",
                        "required_start_ts_ms": _datetime_to_epoch_ms(result_1m.required_start),
                        "required_end_ts_ms": _datetime_to_epoch_ms(result_1m.required_end),
                        "db_start_ts_ms": _datetime_to_epoch_ms(result_1m.min_ts),
                        "db_end_ts_ms": _datetime_to_epoch_ms(result_1m.max_ts),
                        "fix_command": (
                            f"python trade_cli.py data sync-range --symbol {symbol} --tf 1m "
                            f"--start {result_1m.required_start.strftime('%Y-%m-%d') if result_1m.required_start else 'N/A'} "
                            f"--end {result_1m.required_end.strftime('%Y-%m-%d') if result_1m.required_end else 'N/A'}"
                        ),
                    }
                    break
        elif not exec_to_1m_mapping_feasible:
            error_code = "EXEC_1M_MAPPING_FAILED"
            error_details = {
                "reason": mapping_error or "Unknown mapping error",
                "exec_tf": exec_tf.tf if exec_tf else "unknown",
            }
        else:
            # Analyze other failures
            for key, tf_result in tf_results.items():
                if tf_result.status == PreflightStatus.FAILED:
                    if not tf_result.data_exists:
                        # No data at all for this symbol/tf
                        error_code = "HISTORY_UNAVAILABLE"
                        error_details = {
                            "symbol": tf_result.symbol,
                            "tf": tf_result.tf,
                            "reason": "no_data_exists",
                        }
                        break
                    elif not tf_result.covers_range:
                        # Data exists but doesn't cover required range
                        error_code = "INSUFFICIENT_COVERAGE"
                        error_details = {
                            "symbol": tf_result.symbol,
                            "tf": tf_result.tf,
                            "reason": "coverage_gap",
                            "required_start_ts_ms": _datetime_to_epoch_ms(tf_result.required_start),
                            "required_end_ts_ms": _datetime_to_epoch_ms(tf_result.required_end),
                            "db_start_ts_ms": _datetime_to_epoch_ms(tf_result.min_ts),
                            "db_end_ts_ms": _datetime_to_epoch_ms(tf_result.max_ts),
                        }
                        break
                    else:
                        # Other validation failure (gaps, alignment, etc.)
                        error_code = "DATA_QUALITY_ISSUE"
                        error_details = {
                            "symbol": tf_result.symbol,
                            "tf": tf_result.tf,
                            "errors": tf_result.errors,
                        }
                        break

    # Build report with computed warmup requirements (SOURCE OF TRUTH for downstream)
    report = PreflightReport(
        play_id=play.id,
        window_start=window_start,
        window_end=window_end,
        overall_status=PreflightStatus.PASSED if overall_passed else PreflightStatus.FAILED,
        tf_results=tf_results,
        auto_sync_result=auto_sync_result,
        computed_warmup_requirements=warmup_requirements,  # Pass to Runner/Engine
        error_code=error_code,
        error_details=error_details,
        # 1m Price Feed fields
        has_1m_coverage=has_1m_coverage,
        exec_to_1m_mapping_feasible=exec_to_1m_mapping_feasible,
        required_1m_bars=required_1m_bars,
    )
    
    return report


# Type alias for data loader callable
DataLoader = Callable[[str, str, datetime, datetime], pd.DataFrame]
