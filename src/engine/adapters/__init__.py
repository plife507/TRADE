"""
Adapters package for PlayEngine.

Provides mode-specific implementations of:
- DataProvider: Market data access
- ExchangeAdapter: Order execution
- StateStore: State persistence

Backtest Adapters (backtest.py):
- BacktestDataProvider: Wraps FeedStore arrays
- BacktestExchange: Wraps SimulatedExchange

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
    # State
    "InMemoryStateStore",
    "FileStateStore",
    # Live
    "LiveDataProvider",
    "LiveExchange",
]
