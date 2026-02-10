"""
Adapters package for PlayEngine.

Provides mode-specific implementations of:
- DataProvider: Market data access
- ExchangeAdapter: Order execution
- StateStore: State persistence

Backtest Adapters (backtest.py):
- BacktestDataProvider: Wraps FeedStore arrays
- BacktestExchange: Wraps SimulatedExchange
- ShadowExchange: No-op for shadow mode

Live Adapters (live.py):
- LiveDataProvider: WebSocket + indicator cache
- LiveExchange: OrderExecutor + PositionManager

State Adapters (state.py):
- InMemoryStateStore: Dict-based (backtest)
- FileStateStore: JSON file (live recovery)
"""

from .backtest import (
    BacktestDataProvider,
    BacktestExchange,
    ShadowExchange,
)

from .state import (
    InMemoryStateStore,
    FileStateStore,
)

from .live import LiveDataProvider, LiveExchange

__all__ = [
    # Backtest
    "BacktestDataProvider",
    "BacktestExchange",
    "ShadowExchange",
    # State
    "InMemoryStateStore",
    "FileStateStore",
    # Live
    "LiveDataProvider",
    "LiveExchange",
]
