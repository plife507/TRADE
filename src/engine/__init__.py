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

GATE 4 - Unified Backtest Path:
    The create_backtest_engine() factory enables BacktestRunner to drive
    PlayEngine with pre-built FeedStore and SimulatedExchange components.
    This ensures deterministic trade results for the unified execution path.

Usage:
    from src.engine import PlayEngineFactory, create_backtest_engine

    # Create engine for any mode (auto-configures adapters)
    engine = PlayEngineFactory.create(play, mode="backtest")
    engine = PlayEngineFactory.create(play, mode="demo")
    engine = PlayEngineFactory.create(play, mode="live")

    # GATE 4: Create backtest engine with pre-built components
    engine = create_backtest_engine(
        play=play,
        feed_store=feed_store,
        sim_exchange=sim_exchange,
    )

    # Run with appropriate runner
    from src.engine.runners import BacktestRunner, LiveRunner
    runner = BacktestRunner(engine, feed_store, sim_exchange)
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

from .factory import PlayEngineFactory, create_backtest_engine

from .runners import BacktestRunner, BacktestResult

from .adapters.backtest import BacktestDataProvider, BacktestExchange, ShadowExchange

from .sizing import SizingModel, SizingConfig, SizingResult

from .manager import EngineManager, InstanceInfo, InstanceMode

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
    "create_backtest_engine",
    # Runners
    "BacktestRunner",
    "BacktestResult",
    # Adapters
    "BacktestDataProvider",
    "BacktestExchange",
    "ShadowExchange",
    # Sizing
    "SizingModel",
    "SizingConfig",
    "SizingResult",
    # Multi-instance manager
    "EngineManager",
    "InstanceInfo",
    "InstanceMode",
]
