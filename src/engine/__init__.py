"""
Unified Play Engine Package.

This package provides a unified engine for executing Plays across all modes:
- Backtest: Historical data with simulated execution
- Demo: Real-time data with Bybit demo API (fake money)
- Live: Real-time data with Bybit live API (real money)
- Shadow: Real-time data with signal logging only (no execution)

The key design principle is that signal generation logic is IDENTICAL across
all modes. Mode differences are isolated to adapter implementations.

Architecture:
    PlayEngine (core)
        |
        +-- DataProvider (protocol)
        |       +-- BacktestDataProvider (FeedStore arrays)
        |       +-- LiveDataProvider (WebSocket + cache)
        |
        +-- ExchangeAdapter (protocol)
        |       +-- BacktestExchange (SimulatedExchange)
        |       +-- LiveExchange (OrderExecutor)
        |
        +-- StateStore (protocol)
                +-- InMemoryStateStore (backtest)
                +-- FileStateStore (live recovery)

Usage:
    from src.engine import PlayEngineFactory

    # Create engine for any mode
    engine = PlayEngineFactory.create(play, mode="backtest")
    engine = PlayEngineFactory.create(play, mode="demo")
    engine = PlayEngineFactory.create(play, mode="live")

    # Run with appropriate runner
    from src.engine.runners import BacktestRunner, LiveRunner
    runner = BacktestRunner(engine)
    result = runner.run()
"""

from .interfaces import (
    DataProvider,
    ExchangeAdapter,
    StateStore,
    Candle,
    Order,
    OrderResult,
    Position,
    EngineState,
)

from .play_engine import PlayEngine

from .factory import PlayEngineFactory

__all__ = [
    # Protocols
    "DataProvider",
    "ExchangeAdapter",
    "StateStore",
    # Data types
    "Candle",
    "Order",
    "OrderResult",
    "Position",
    "EngineState",
    # Core engine
    "PlayEngine",
    # Factory
    "PlayEngineFactory",
]
