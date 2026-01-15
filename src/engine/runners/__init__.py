"""
Runners package for PlayEngine.

Runners drive the PlayEngine in different modes:
- BacktestRunner: Loop over historical bars
- LiveRunner: WebSocket event loop (Phase 5)
- ShadowRunner: Log signals without executing (Phase 5)

Usage:
    # Backtest
    runner = BacktestRunner(engine)
    result = runner.run()

    # Live (async) - Phase 5
    runner = LiveRunner(engine)
    await runner.start()
    # ... runs until stopped
    await runner.stop()

    # Shadow - Phase 5
    runner = ShadowRunner(engine)
    await runner.start()
"""

from .backtest_runner import BacktestRunner, BacktestResult

__all__ = [
    "BacktestRunner",
    "BacktestResult",
    # "LiveRunner",      # Phase 5
    # "ShadowRunner",    # Phase 5
]
