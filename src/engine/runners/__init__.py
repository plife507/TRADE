"""
Runners package for PlayEngine.

Runners drive the PlayEngine in different modes:
- BacktestRunner: Loop over historical bars
- LiveRunner: WebSocket event loop (Phase 5)
- ShadowRunner: Log signals without executing (Phase 5)

Parallel execution:
- run_backtests_parallel: Run multiple backtests in separate processes
- run_backtest_isolated: Run single backtest in isolated process

Usage:
    # Single backtest
    runner = BacktestRunner(engine)
    result = runner.run()

    # Parallel backtests (separate processes, no DuckDB conflicts)
    from src.engine.runners import run_backtests_parallel
    results = run_backtests_parallel(["S_01", "S_02", "S_03"], max_workers=3)

    # Live (async) - Phase 5
    runner = LiveRunner(engine)
    await runner.start()
    # ... runs until stopped
    await runner.stop()

    # Shadow - Phase 5
    runner = ShadowRunner(engine)
    await runner.start()
"""

from .backtest_runner import (
    BacktestRunner,
    BacktestResult,
    # Professional aliases
    SimRunner,
    SimRunResult,
)
from .shadow_runner import ShadowRunner, ShadowStats, ShadowSignal
from .live_runner import LiveRunner, LiveRunnerStats, RunnerState
from .parallel import (
    run_backtests_parallel,
    ParallelBacktestResult,
)

__all__ = [
    # Backtest/Simulation
    "BacktestRunner",
    "BacktestResult",
    "SimRunner",  # Professional alias
    "SimRunResult",  # Professional alias
    # Parallel execution
    "run_backtests_parallel",
    "ParallelBacktestResult",
    # Shadow
    "ShadowRunner",
    "ShadowStats",
    "ShadowSignal",
    # Live
    "LiveRunner",
    "LiveRunnerStats",
    "RunnerState",
]
