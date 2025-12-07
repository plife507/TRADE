"""
Data modules for market data and historical data storage.

- MarketData: Live market data with caching
- HistoricalDataStore: DuckDB-backed historical OHLCV, funding rates, and open interest
- RealtimeState/RealtimeBootstrap: WebSocket real-time data
"""

from .market_data import MarketData, get_market_data, reset_market_data
from .historical_data_store import HistoricalDataStore, get_historical_store
from .realtime_state import (
    RealtimeState,
    get_realtime_state,
    reset_realtime_state,
    TickerData,
    OrderbookData,
    TradeData,
    KlineData,
    PositionData,
    OrderData,
    ExecutionData,
    WalletData,
    AccountMetrics,
    PortfolioRiskSnapshot,
    RealtimeEvent,
    EventType,
    ConnectionState,
)
from .realtime_bootstrap import (
    RealtimeBootstrap,
    get_realtime_bootstrap,
    reset_realtime_bootstrap,
    SubscriptionConfig,
)

__all__ = [
    # Market Data
    "MarketData",
    "get_market_data",
    "reset_market_data",
    # Historical Data Store (DuckDB)
    "HistoricalDataStore",
    "get_historical_store",
    # Real-time State
    "RealtimeState",
    "get_realtime_state",
    "reset_realtime_state",
    "TickerData",
    "OrderbookData",
    "TradeData",
    "KlineData",
    "PositionData",
    "OrderData",
    "ExecutionData",
    "WalletData",
    "AccountMetrics",
    "PortfolioRiskSnapshot",
    "RealtimeEvent",
    "EventType",
    "ConnectionState",
    # Real-time Bootstrap
    "RealtimeBootstrap",
    "get_realtime_bootstrap",
    "reset_realtime_bootstrap",
    "SubscriptionConfig",
]
