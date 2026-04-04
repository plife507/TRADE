"""
Runners package for PlayEngine.

Runners drive the PlayEngine in different modes:
- BacktestRunner: Loop over historical bars
- LiveRunner: WebSocket event loop

Shadow mode uses the daemon at src/shadow/ (ShadowEngine + ShadowOrchestrator).

Parallel execution:
- run_backtests_parallel: Run multiple backtests in separate processes

Usage:
    # Single backtest
    runner = BacktestRunner(engine)
    result = runner.run()

    # Parallel backtests (separate processes, no DuckDB conflicts)
    from src.engine.runners import run_backtests_parallel
    results = run_backtests_parallel(["S_01", "S_02", "S_03"], max_workers=3)

    # Live (async)
    runner = LiveRunner(engine)
    await runner.start()
    await runner.stop()
"""

from .backtest_runner import BacktestRunner, BacktestResult
from .live_runner import LiveRunner, LiveRunnerStats, RunnerState
from .parallel import (
    run_backtests_parallel,
    ParallelBacktestResult,
)

__all__ = [
    # Backtest
    "BacktestRunner",
    "BacktestResult",
    # Parallel execution
    "run_backtests_parallel",
    "ParallelBacktestResult",
    # Live
    "LiveRunner",
    "LiveRunnerStats",
    "RunnerState",
]
