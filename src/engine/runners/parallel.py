"""
Parallel backtest execution utilities.

Provides helpers for running multiple backtests in separate processes
to avoid DuckDB locking issues and enable true parallelism.

Architecture:
    - Each process gets its own HistoricalDataStore singleton
    - Each process gets its own DuckDB connection
    - PlayEngine instances are fully isolated (no shared state)
    - Results are serialized and returned to the parent process

Usage:
    from src.engine.runners.parallel import run_backtests_parallel

    results = run_backtests_parallel(
        play_ids=["S_01_btc_ema", "S_02_eth_macd", "S_03_sol_rsi"],
        max_workers=3,
    )

Note:
    Live and Demo modes use global singletons (RealtimeState, RealtimeBootstrap)
    and cannot be run in parallel within the same process. Use separate processes
    for concurrent live/demo instances.
"""

from __future__ import annotations

import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ...backtest.play import Play


@dataclass
class ParallelBacktestResult:
    """
    Result from a parallel backtest execution.

    Contains the play_id, success status, and either results or error.
    """
    play_id: str
    success: bool
    result: dict[str, Any] | None = None
    error: str | None = None
    duration_seconds: float = 0.0


def _run_single_backtest_process(
    play_id: str,
    plays_dir: str | None,
    env: str,
    start: datetime | None,
    end: datetime | None,
) -> ParallelBacktestResult:
    """
    Run a single backtest in an isolated process.

    This function is called by ProcessPoolExecutor. Each call runs in a
    separate process with its own Python interpreter, ensuring complete
    isolation of:
    - HistoricalDataStore singleton
    - DuckDB connection
    - PlayEngine instance state
    - All caches and global state

    Args:
        play_id: Play identifier to backtest
        plays_dir: Optional override for plays directory
        env: Data environment ("backtest", "live", or "demo")
        start: Optional start datetime
        end: Optional end datetime

    Returns:
        ParallelBacktestResult with success/error and result dict
    """
    import time
    start_time = time.time()

    try:
        # CRITICAL: Reset singletons and enable read-only mode for all DB access
        # This must happen before any imports that touch the database
        # force_read_only=True enables concurrent readers (DuckDB allows multiple readers)
        from ...data.historical_data_store import reset_stores
        reset_stores(force_read_only=True)

        # Import inside the process to get fresh module state
        from ...backtest.play import load_play
        from ...tools.backtest_play_tools import backtest_run_play_tool

        # Convert plays_dir to Path if provided
        plays_path = Path(plays_dir) if plays_dir else None

        # Run the backtest using the standard tool
        # skip_preflight=True because parent process should sync data before parallel run
        tool_result = backtest_run_play_tool(
            play_id=play_id,
            env=env,
            start=start,
            end=end,
            plays_dir=plays_path,
            skip_preflight=True,  # Data should be synced before parallel run
        )

        duration = time.time() - start_time

        if tool_result.success:
            return ParallelBacktestResult(
                play_id=play_id,
                success=True,
                result=tool_result.data,
                duration_seconds=duration,
            )
        else:
            return ParallelBacktestResult(
                play_id=play_id,
                success=False,
                error=tool_result.error,
                duration_seconds=duration,
            )

    except Exception as e:
        import traceback
        duration = time.time() - start_time
        return ParallelBacktestResult(
            play_id=play_id,
            success=False,
            error=f"{type(e).__name__}: {e}\n{traceback.format_exc()}",
            duration_seconds=duration,
        )


def run_backtests_parallel(
    play_ids: list[str],
    max_workers: int | None = None,
    plays_dir: str | Path | None = None,
    env: str = "backtest",
    start: datetime | None = None,
    end: datetime | None = None,
    progress_callback: callable | None = None,
) -> list[ParallelBacktestResult]:
    """
    Run multiple backtests in parallel using separate processes.

    Each backtest runs in its own process with complete isolation:
    - Own HistoricalDataStore singleton and DuckDB connection
    - Own PlayEngine instance with unique engine_id
    - Own indicator computations (no shared cache)

    This avoids DuckDB locking issues and enables true parallelism.

    Args:
        play_ids: List of Play identifiers to backtest
        max_workers: Max parallel processes (default: CPU count - 1, min 1)
        plays_dir: Optional override for plays directory
        env: Data environment ("backtest", "live", or "demo")
        start: Optional start datetime for all backtests
        end: Optional end datetime for all backtests
        progress_callback: Optional callback(play_id, status, result) for progress

    Returns:
        List of ParallelBacktestResult objects (same order as play_ids)

    Example:
        results = run_backtests_parallel(
            play_ids=["S_01", "S_02", "S_03"],
            max_workers=3,
        )
        for r in results:
            if r.success:
                print(f"{r.play_id}: {r.result['metrics']['net_profit']}")
            else:
                print(f"{r.play_id}: FAILED - {r.error}")
    """
    if not play_ids:
        return []

    # Default max_workers to CPU count - 1, minimum 1
    if max_workers is None:
        max_workers = max(1, mp.cpu_count() - 1)

    # Convert plays_dir to string for serialization
    plays_dir_str = str(plays_dir) if plays_dir else None

    # Results dict keyed by play_id to preserve order
    results_map: dict[str, ParallelBacktestResult] = {}

    # Use ProcessPoolExecutor for true parallelism
    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        # Submit all backtests
        future_to_play = {
            executor.submit(
                _run_single_backtest_process,
                play_id,
                plays_dir_str,
                env,
                start,
                end,
            ): play_id
            for play_id in play_ids
        }

        # Collect results as they complete
        for future in as_completed(future_to_play):
            play_id = future_to_play[future]
            try:
                result = future.result()
                results_map[play_id] = result

                if progress_callback:
                    status = "completed" if result.success else "failed"
                    progress_callback(play_id, status, result)

            except Exception as e:
                # Should not happen since _run_single_backtest_process catches exceptions
                results_map[play_id] = ParallelBacktestResult(
                    play_id=play_id,
                    success=False,
                    error=f"Process error: {e}",
                )
                if progress_callback:
                    progress_callback(play_id, "error", results_map[play_id])

    # Return results in original order
    return [results_map[pid] for pid in play_ids]


# G1.19: run_backtest_isolated() removed (2026-01-27) - use run_backtests_parallel with max_workers=1