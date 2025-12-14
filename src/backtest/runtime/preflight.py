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

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any, Callable
import json
import pandas as pd
import numpy as np


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
    params: Dict[str, Any]
    success: bool
    message: str = ""
    timestamp: datetime = field(default_factory=_utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
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
    sync_range_tool: Optional[Callable] = None
    fill_gaps_tool: Optional[Callable] = None
    heal_data_tool: Optional[Callable] = None


@dataclass
class AutoSyncResult:
    """Result of auto-sync attempt."""
    attempted: bool = False
    success: bool = False
    tool_calls: List[ToolCallRecord] = field(default_factory=list)
    attempts_made: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
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
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "start_ts": self.start_ts.isoformat(),
            "end_ts": self.end_ts.isoformat(),
            "expected_bars": self.expected_bars,
            "actual_bars": self.actual_bars,
            "gap_duration_minutes": self.gap_duration_minutes,
        }


@dataclass
class TFPreflightResult:
    """Preflight result for a single (symbol, tf) pair."""
    symbol: str
    tf: str
    status: PreflightStatus
    
    # Coverage info
    min_ts: Optional[datetime] = None
    max_ts: Optional[datetime] = None
    bar_count: int = 0
    
    # Required range
    required_start: Optional[datetime] = None
    required_end: Optional[datetime] = None
    warmup_bars: int = 0
    
    # Validation results
    data_exists: bool = False
    covers_range: bool = False
    is_monotonic: bool = False
    is_unique: bool = False
    alignment_ok: bool = False
    
    # Gaps
    gaps: List[GapInfo] = field(default_factory=list)
    max_gap_minutes: float = 0.0
    gap_threshold_minutes: float = 0.0
    gaps_within_threshold: bool = True
    
    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "symbol": self.symbol,
            "tf": self.tf,
            "status": self.status.value,
            "coverage": {
                "min_ts": self.min_ts.isoformat() if self.min_ts else None,
                "max_ts": self.max_ts.isoformat() if self.max_ts else None,
                "bar_count": self.bar_count,
            },
            "required_range": {
                "start": self.required_start.isoformat() if self.required_start else None,
                "end": self.required_end.isoformat() if self.required_end else None,
                "warmup_bars": self.warmup_bars,
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
    idea_card_id: str
    window_start: datetime
    window_end: datetime
    overall_status: PreflightStatus
    tf_results: Dict[str, TFPreflightResult]  # key: "symbol:tf"
    run_timestamp: datetime = field(default_factory=_utcnow)
    auto_sync_result: Optional[AutoSyncResult] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dict for serialization."""
        result = {
            "idea_card_id": self.idea_card_id,
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
        return result
    
    def write_json(self, path: Path) -> None:
        """Write report to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
    
    def print_summary(self) -> None:
        """Print summary to console."""
        status_icon = "[OK]" if self.overall_status == PreflightStatus.PASSED else "[FAIL]"
        print(f"\n{status_icon} Preflight Gate: {self.overall_status.value.upper()}")
        print(f"   IdeaCard: {self.idea_card_id}")
        print(f"   Window: {self.window_start.date()} -> {self.window_end.date()}")
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
    
    Supports: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1w
    """
    tf = tf.lower().strip()
    
    if tf.endswith("m"):
        return int(tf[:-1])
    elif tf.endswith("h"):
        return int(tf[:-1]) * 60
    elif tf.endswith("d"):
        return int(tf[:-1]) * 60 * 24
    elif tf.endswith("w"):
        return int(tf[:-1]) * 60 * 24 * 7
    else:
        raise ValueError(f"Unknown timeframe format: {tf}")


def calculate_warmup_start(
    window_start: datetime,
    warmup_bars: int,
    tf_minutes: int,
) -> datetime:
    """Calculate the start timestamp including warmup buffer."""
    warmup_minutes = warmup_bars * tf_minutes
    return window_start - timedelta(minutes=warmup_minutes)


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
    if min_ts <= eff_start_cmp and max_ts >= req_end_cmp:
        result.covers_range = True
    else:
        if min_ts > eff_start_cmp:
            result.errors.append(
                f"Data starts too late: {min_ts} > {eff_start_cmp} (need {warmup_bars} warmup bars)"
            )
        if max_ts < req_end_cmp:
            result.errors.append(
                f"Data ends too early: {max_ts} < {req_end_cmp}"
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


def _get_default_tools() -> Tuple[Callable, Callable, Callable]:
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
    pairs_to_sync: List[Tuple[str, str, datetime, datetime]],
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
    symbols_tfs: Dict[str, List[Tuple[str, datetime, datetime]]] = {}
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
    pairs_to_check: List[Tuple[str, str, int]],
    data_loader: "DataLoader",
    window_start: datetime,
    window_end: datetime,
    gap_threshold_multiplier: float,
) -> Tuple[Dict[str, TFPreflightResult], List[Tuple[str, str, datetime, datetime]]]:
    """
    Validate all (symbol, tf) pairs and collect failures.
    
    Returns:
        Tuple of (tf_results dict, list of failed pairs needing sync)
    """
    tf_results: Dict[str, TFPreflightResult] = {}
    failed_pairs: List[Tuple[str, str, datetime, datetime]] = []
    
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


def run_preflight_gate(
    idea_card: "IdeaCard",
    data_loader: "DataLoader",
    window_start: datetime,
    window_end: datetime,
    gap_threshold_multiplier: float = 3.0,
    auto_sync_missing: bool = False,
    auto_sync_config: Optional[AutoSyncConfig] = None,
) -> PreflightReport:
    """
    Run the data preflight gate for an IdeaCard.
    
    TOOL DISCIPLINE (MANDATORY):
    - When auto_sync_missing=True, preflight MUST call data tools to fix issues
    - All data fixes go through sync_range_tool, fill_gaps_tool, heal_data_tool
    - Simulator/backtest MUST NOT modify DuckDB directly
    
    Args:
        idea_card: The IdeaCard to validate data for
        data_loader: Callable that loads data for (symbol, tf, start, end) -> DataFrame
        window_start: Backtest window start
        window_end: Backtest window end
        gap_threshold_multiplier: Gaps larger than this * tf_minutes are flagged
        auto_sync_missing: If True, attempt to sync missing data via tools
        auto_sync_config: Configuration for auto-sync (optional, uses defaults)
        
    Returns:
        PreflightReport with all validation results and auto_sync info
    """
    # Collect all (symbol, tf) pairs from the IdeaCard
    pairs_to_check: List[Tuple[str, str, int]] = []  # (symbol, tf, warmup_bars)
    
    for symbol in idea_card.symbol_universe:
        for role, tf_config in idea_card.tf_configs.items():
            warmup = tf_config.effective_warmup_bars
            pairs_to_check.append((symbol, tf_config.tf, warmup))
    
    # First validation pass
    tf_results, failed_pairs = _validate_all_pairs(
        pairs_to_check=pairs_to_check,
        data_loader=data_loader,
        window_start=window_start,
        window_end=window_end,
        gap_threshold_multiplier=gap_threshold_multiplier,
    )
    
    auto_sync_result: Optional[AutoSyncResult] = None
    
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
    
    # Determine overall status
    overall_passed = all(
        r.status != PreflightStatus.FAILED 
        for r in tf_results.values()
    )
    
    # Build report
    report = PreflightReport(
        idea_card_id=idea_card.id,
        window_start=window_start,
        window_end=window_end,
        overall_status=PreflightStatus.PASSED if overall_passed else PreflightStatus.FAILED,
        tf_results=tf_results,
        auto_sync_result=auto_sync_result,
    )
    
    return report


# Type alias for data loader callable
from typing import Callable
DataLoader = Callable[[str, str, datetime, datetime], pd.DataFrame]
