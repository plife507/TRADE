"""
Determinism Checker: Proves same inputs yield identical outputs.

Determinism is critical for:
- Reproducible backtest results
- Debugging (same run = same bug)
- Trust in optimization results

This module validates determinism by:
1. Running the same backtest N times
2. Computing hashes of trades, equity, signals
3. Verifying all hashes match

Usage:
    from src.testing_agent.determinism_checker import run_determinism_check

    result = run_determinism_check(play_id="my_play", runs=5)
    if result.passed:
        print("Backtest is deterministic")
    else:
        print(f"Non-determinism detected: {result.violations}")
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import hashlib
import json
import time

import pandas as pd

from ..utils.logger import get_logger

logger = get_logger()


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class RunHash:
    """Hash values from a single backtest run."""
    run_number: int
    trades_hash: str
    equity_hash: str
    signals_hash: str
    results_hash: str
    trades_count: int = 0
    final_equity: float = 0.0
    duration_ms: int = 0


@dataclass
class DeterminismViolation:
    """A single determinism violation between runs."""
    artifact: str  # "trades", "equity", "signals", "results"
    run_a: int
    run_b: int
    hash_a: str
    hash_b: str
    notes: str = ""


@dataclass
class DeterminismResult:
    """Result from determinism check."""
    passed: bool
    runs_completed: int = 0
    runs_requested: int = 0
    run_hashes: list[RunHash] = field(default_factory=list)
    violations: list[DeterminismViolation] = field(default_factory=list)
    trades_match: bool = True
    equity_match: bool = True
    signals_match: bool = True
    results_match: bool = True
    duration_seconds: float = 0.0
    error: str | None = None


# =============================================================================
# Hash Functions
# =============================================================================

def compute_trades_hash(trades: list[dict[str, Any]]) -> str:
    """
    Compute deterministic hash of trades list.

    The hash is based on key trade fields in a canonical order,
    ignoring timing/metadata that may vary.

    Args:
        trades: List of trade dicts

    Returns:
        SHA256 hex digest
    """
    if not trades:
        return hashlib.sha256(b"empty").hexdigest()

    # Sort by entry bar to ensure order
    sorted_trades = sorted(trades, key=lambda t: (t.get("entry_bar", 0), t.get("trade_id", "")))

    # Extract key fields for hashing
    canonical_data = []
    for trade in sorted_trades:
        trade_tuple = (
            trade.get("entry_bar", 0),
            trade.get("exit_bar", 0),
            round(trade.get("entry_price", 0), 8),
            round(trade.get("exit_price", 0), 8),
            trade.get("direction", ""),
            round(trade.get("pnl", 0), 8),
            round(trade.get("size_usdt", 0), 8),
        )
        canonical_data.append(trade_tuple)

    # Serialize and hash
    data_str = json.dumps(canonical_data, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()


def compute_equity_hash(equity_curve: pd.DataFrame | list[float]) -> str:
    """
    Compute deterministic hash of equity curve.

    Args:
        equity_curve: DataFrame with 'equity' column or list of equity values

    Returns:
        SHA256 hex digest
    """
    if isinstance(equity_curve, pd.DataFrame):
        if "equity" in equity_curve.columns:
            values = equity_curve["equity"].tolist()
        else:
            values = equity_curve.iloc[:, 0].tolist()
    elif isinstance(equity_curve, pd.Series):
        values = equity_curve.tolist()
    else:
        values = list(equity_curve)

    if not values:
        return hashlib.sha256(b"empty").hexdigest()

    # Round to avoid floating-point noise
    rounded = [round(v, 8) for v in values]
    data_str = json.dumps(rounded)
    return hashlib.sha256(data_str.encode()).hexdigest()


def compute_signals_hash(signals: list[dict[str, Any]]) -> str:
    """
    Compute deterministic hash of signal sequence.

    Only the (bar_idx, direction) tuples matter for determinism,
    not the timestamp or other metadata.

    Args:
        signals: List of signal dicts with bar_idx and direction

    Returns:
        SHA256 hex digest
    """
    if not signals:
        return hashlib.sha256(b"empty").hexdigest()

    # Sort by bar
    sorted_signals = sorted(signals, key=lambda s: s.get("bar_idx", s.get("bar", 0)))

    # Extract (bar, direction) tuples
    tuples = [(s.get("bar_idx", s.get("bar", 0)), s.get("direction", "")) for s in sorted_signals]

    data_str = json.dumps(tuples)
    return hashlib.sha256(data_str.encode()).hexdigest()


def compute_results_hash(results: dict[str, Any]) -> str:
    """
    Compute deterministic hash of results summary.

    Args:
        results: Results dict with metrics

    Returns:
        SHA256 hex digest
    """
    if not results:
        return hashlib.sha256(b"empty").hexdigest()

    # Select key metrics for comparison
    key_fields = [
        "trades_count",
        "winning_trades",
        "losing_trades",
        "net_pnl_usdt",
        "net_return_pct",
        "max_drawdown_pct",
        "sharpe",
        "profit_factor",
    ]

    canonical = {}
    for field in key_fields:
        val = results.get(field)
        if isinstance(val, float):
            val = round(val, 8)
        canonical[field] = val

    data_str = json.dumps(canonical, sort_keys=True)
    return hashlib.sha256(data_str.encode()).hexdigest()


# =============================================================================
# Determinism Check Functions
# =============================================================================

def run_determinism_check(
    play_id: str,
    runs: int = 3,
    plays_dir: Path | None = None,
    fix_gaps: bool = True,
    start: datetime | None = None,
    end: datetime | None = None,
) -> DeterminismResult:
    """
    Run determinism check by executing the same backtest multiple times.

    Args:
        play_id: Play identifier to test
        runs: Number of times to run (default: 3)
        plays_dir: Optional Play directory override
        fix_gaps: Whether to fix data gaps
        start: Optional start date
        end: Optional end date

    Returns:
        DeterminismResult with pass/fail and hashes
    """
    start_time = time.time()
    result = DeterminismResult(passed=True, runs_requested=runs)

    try:
        from ..backtest.play import load_play
        from ..backtest.engine_factory import create_engine_from_play, run_engine_with_play

        # Load play once
        play = load_play(play_id, base_dir=plays_dir)
        symbol = play.symbol_universe[0] if play.symbol_universe else "BTCUSDT"

        # Determine window
        if start is None or end is None:
            # For plays with synthetic config, let the engine handle data
            # For real data plays, find available data range
            if play.synthetic is not None:
                # Synthetic plays generate their own data - use a fixed window
                # The engine will generate synthetic data based on play config
                start = datetime(2025, 1, 15)  # Within typical synthetic range
                end = datetime(2025, 2, 15)
                logger.info(f"Determinism check: synthetic play, using fixed window {start} to {end}")
            else:
                from ..data.historical_data_store import get_historical_store
                store = get_historical_store(env="live")
                exec_tf = play.execution_tf
                # Query to find what data exists
                df = store.get_ohlcv(symbol, exec_tf, start=datetime(2024, 1, 1), end=datetime(2025, 12, 31))
                if df is not None and len(df) >= 100:
                    start = df["timestamp"].iloc[-100]
                    end = df["timestamp"].iloc[-1]
                    logger.info(f"Determinism check window: {start} to {end} ({len(df)} bars available)")
                else:
                    result.passed = False
                    result.error = f"Insufficient data for smoke test (got {len(df) if df is not None else 0} bars)"
                    return result

        for run_num in range(1, runs + 1):
            run_start = time.time()

            logger.info(f"Determinism check run {run_num}/{runs} for {play_id}")

            # Run backtest using engine factory directly
            engine = create_engine_from_play(
                play=play,
                window_start=start,
                window_end=end,
                data_env="live",
            )
            bt_result = run_engine_with_play(engine, play)

            # Extract data for hashing - trades are Trade dataclass objects
            trades = []
            for t in bt_result.trades:
                trades.append({
                    "entry_bar": getattr(t, "entry_bar_index", 0),
                    "exit_bar": getattr(t, "exit_bar_index", 0),
                    "entry_price": round(getattr(t, "entry_price", 0), 8),
                    "exit_price": round(getattr(t, "exit_price", 0) or 0, 8),
                    "direction": getattr(t, "side", "long"),
                    "pnl": round(getattr(t, "realized_pnl", 0), 8),
                    "size_usdt": round(getattr(t, "entry_size_usdt", 0), 8),
                })

            # Extract equity curve - may be list of floats, dicts, or dataclass objects
            raw_equity = bt_result.equity_curve if bt_result.equity_curve else []
            equity = []
            for e in raw_equity:
                if isinstance(e, (int, float)):
                    equity.append(float(e))
                elif isinstance(e, dict):
                    equity.append(float(e.get("equity", e.get("value", 0))))
                elif hasattr(e, "equity"):
                    equity.append(float(getattr(e, "equity", 0)))
                else:
                    equity.append(0.0)

            signals = []  # Signals inferred from trades
            for t in bt_result.trades:
                signals.append({
                    "bar_idx": getattr(t, "entry_bar_index", 0),
                    "direction": getattr(t, "side", "long"),
                })

            summary = {
                "trades_count": len(bt_result.trades),
                "final_equity": bt_result.final_equity,
            }

            # Compute hashes
            run_hash = RunHash(
                run_number=run_num,
                trades_hash=compute_trades_hash(trades),
                equity_hash=compute_equity_hash(equity),
                signals_hash=compute_signals_hash(signals),
                results_hash=compute_results_hash(summary),
                trades_count=len(trades),
                final_equity=summary.get("final_equity", 0.0),
                duration_ms=int((time.time() - run_start) * 1000),
            )

            result.run_hashes.append(run_hash)
            result.runs_completed += 1

        # Compare all runs
        if result.runs_completed >= 2:
            first = result.run_hashes[0]

            for run_hash in result.run_hashes[1:]:
                # Compare trades
                if run_hash.trades_hash != first.trades_hash:
                    result.trades_match = False
                    result.passed = False
                    result.violations.append(DeterminismViolation(
                        artifact="trades",
                        run_a=first.run_number,
                        run_b=run_hash.run_number,
                        hash_a=first.trades_hash[:16],
                        hash_b=run_hash.trades_hash[:16],
                        notes=f"Trades differ between runs {first.run_number} and {run_hash.run_number}",
                    ))

                # Compare equity
                if run_hash.equity_hash != first.equity_hash:
                    result.equity_match = False
                    result.passed = False
                    result.violations.append(DeterminismViolation(
                        artifact="equity",
                        run_a=first.run_number,
                        run_b=run_hash.run_number,
                        hash_a=first.equity_hash[:16],
                        hash_b=run_hash.equity_hash[:16],
                        notes=f"Equity curve differs between runs",
                    ))

                # Compare signals
                if run_hash.signals_hash != first.signals_hash:
                    result.signals_match = False
                    result.passed = False
                    result.violations.append(DeterminismViolation(
                        artifact="signals",
                        run_a=first.run_number,
                        run_b=run_hash.run_number,
                        hash_a=first.signals_hash[:16],
                        hash_b=run_hash.signals_hash[:16],
                        notes=f"Signals differ between runs",
                    ))

                # Compare results
                if run_hash.results_hash != first.results_hash:
                    result.results_match = False
                    result.passed = False
                    result.violations.append(DeterminismViolation(
                        artifact="results",
                        run_a=first.run_number,
                        run_b=run_hash.run_number,
                        hash_a=first.results_hash[:16],
                        hash_b=run_hash.results_hash[:16],
                        notes=f"Results summary differs between runs",
                    ))

    except Exception as e:
        result.passed = False
        result.error = str(e)
        logger.error(f"Determinism check failed: {e}")

    result.duration_seconds = time.time() - start_time
    return result


def quick_determinism_check(
    run_a: dict[str, Any],
    run_b: dict[str, Any],
) -> tuple[bool, list[str]]:
    """
    Quick comparison of two backtest runs for determinism.

    Args:
        run_a: First run data dict (with trades, equity, signals, summary)
        run_b: Second run data dict

    Returns:
        Tuple of (passed, list of failed artifact names)
    """
    failed = []

    # Compare trades
    hash_a = compute_trades_hash(run_a.get("trades", []))
    hash_b = compute_trades_hash(run_b.get("trades", []))
    if hash_a != hash_b:
        failed.append("trades")

    # Compare equity
    hash_a = compute_equity_hash(run_a.get("equity_curve", []))
    hash_b = compute_equity_hash(run_b.get("equity_curve", []))
    if hash_a != hash_b:
        failed.append("equity")

    # Compare signals
    hash_a = compute_signals_hash(run_a.get("signals", []))
    hash_b = compute_signals_hash(run_b.get("signals", []))
    if hash_a != hash_b:
        failed.append("signals")

    # Compare results
    hash_a = compute_results_hash(run_a.get("summary", {}))
    hash_b = compute_results_hash(run_b.get("summary", {}))
    if hash_a != hash_b:
        failed.append("results")

    return (len(failed) == 0, failed)


def verify_reproducibility(
    trades_file: Path,
    expected_hash: str,
) -> bool:
    """
    Verify a trades file matches an expected hash.

    Useful for regression testing against known-good outputs.

    Args:
        trades_file: Path to trades parquet or JSON file
        expected_hash: Expected SHA256 hash

    Returns:
        True if hash matches
    """
    if not trades_file.exists():
        return False

    if trades_file.suffix == ".parquet":
        df = pd.read_parquet(trades_file)
        trades = df.to_dict("records")
    else:
        with open(trades_file, "r", newline="\n") as f:
            trades = json.load(f)

    actual_hash = compute_trades_hash(trades)
    return actual_hash == expected_hash


# =============================================================================
# Reporting
# =============================================================================

def format_determinism_report(result: DeterminismResult) -> str:
    """
    Format determinism result as human-readable report.

    Args:
        result: DeterminismResult to format

    Returns:
        Formatted string report
    """
    lines = []
    lines.append("=" * 60)
    lines.append("DETERMINISM CHECK REPORT")
    lines.append("=" * 60)

    status = "PASS" if result.passed else "FAIL"
    lines.append(f"Status: {status}")
    lines.append(f"Runs: {result.runs_completed}/{result.runs_requested}")
    lines.append(f"Duration: {result.duration_seconds:.1f}s")
    lines.append("")

    if result.error:
        lines.append(f"Error: {result.error}")
        lines.append("")

    # Hash comparison
    lines.append("Artifact Comparison:")
    lines.append(f"  Trades:  {'MATCH' if result.trades_match else 'DIFFER'}")
    lines.append(f"  Equity:  {'MATCH' if result.equity_match else 'DIFFER'}")
    lines.append(f"  Signals: {'MATCH' if result.signals_match else 'DIFFER'}")
    lines.append(f"  Results: {'MATCH' if result.results_match else 'DIFFER'}")
    lines.append("")

    # Run details
    if result.run_hashes:
        lines.append("Run Details:")
        for rh in result.run_hashes:
            lines.append(f"  Run {rh.run_number}: {rh.trades_count} trades, "
                        f"equity ${rh.final_equity:,.2f}, "
                        f"{rh.duration_ms}ms")
            lines.append(f"    Trades:  {rh.trades_hash[:16]}...")
            lines.append(f"    Equity:  {rh.equity_hash[:16]}...")
            lines.append(f"    Signals: {rh.signals_hash[:16]}...")
        lines.append("")

    # Violations
    if result.violations:
        lines.append("Violations:")
        for v in result.violations:
            lines.append(f"  - {v.artifact}: runs {v.run_a} vs {v.run_b}")
            lines.append(f"    {v.hash_a} != {v.hash_b}")
            lines.append(f"    {v.notes}")

    lines.append("=" * 60)

    return "\n".join(lines)
