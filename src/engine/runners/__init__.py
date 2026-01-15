"""
Runners package for PlayEngine.

Runners drive the PlayEngine in different modes:
- BacktestRunner: Loop over historical bars
- LiveRunner: WebSocket event loop
- ShadowRunner: Log signals without executing

Usage:
    # Backtest
    runner = BacktestRunner(engine)
    result = runner.run()

    # Live (async)
    runner = LiveRunner(engine)
    await runner.start()
    # ... runs until stopped
    await runner.stop()

    # Shadow
    runner = ShadowRunner(engine)
    await runner.start()
"""

# Runners will be implemented in Phase 5
# For now, just define the package

__all__ = [
    # "BacktestRunner",  # Phase 5
    # "LiveRunner",      # Phase 5
    # "ShadowRunner",    # Phase 5
]
