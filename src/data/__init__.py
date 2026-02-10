"""
Data modules for market data and historical data storage.

Environment-aware data layer supporting live and demo trading:
- MarketData: Live market data with caching (env-aware)
- HistoricalDataStore: DuckDB-backed historical data (env-aware: live/demo)
- RealtimeState/RealtimeBootstrap: WebSocket real-time data with bar buffers
- Sessions: DemoSession/LiveSession for isolated trading environments
- Backend Protocol: Interface for future MongoDB backend support

Timeframe Terminology:
- low_tf: 1m, 3m, 5m, 15m (execution timing)
- med_tf: 30m, 1h, 2h, 4h (trade bias)
- high_tf: 6h, 12h, D, W (trend direction)
- exec: Play's execution timeframe pointer
- multi-timeframe: Cross-timeframe analysis (comparing low_tf/med_tf/high_tf)
"""

from .market_data import (
    MarketData,
    get_market_data,
    get_live_market_data,
    get_demo_market_data,
    reset_market_data,
)
from .historical_data_store import (
    HistoricalDataStore,
    get_historical_store,
    get_live_historical_store,
    get_demo_historical_store,
    # Module-level env-aware API
    get_ohlcv,
    get_latest_ohlcv,
    append_ohlcv,
    get_funding,
    get_open_interest,
    get_symbol_timeframe_ranges,
)
from .realtime_state import (
    RealtimeState,
    get_realtime_state,
    reset_realtime_state,
    TickerData,
    OrderbookData,
    TradeData,
    KlineData,
    BarRecord,
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
from .sessions import (
    SessionConfig,
    BaseSession,
    DemoSession,
    LiveSession,
    create_demo_session,
    create_live_session,
)
from .backend_protocol import (
    HistoricalBackend,
    MongoBackend,
)

__all__ = [
    # Market Data (env-aware)
    "MarketData",
    "get_market_data",
    "get_live_market_data",
    "get_demo_market_data",
    "reset_market_data",
    # Historical Data Store (DuckDB, env-aware)
    "HistoricalDataStore",
    "get_historical_store",
    "get_live_historical_store",
    "get_demo_historical_store",
    # Module-level env-aware data API
    "get_ohlcv",
    "get_latest_ohlcv",
    "append_ohlcv",
    "get_funding",
    "get_open_interest",
    "get_symbol_timeframe_ranges",
    # Real-time State
    "RealtimeState",
    "get_realtime_state",
    "reset_realtime_state",
    "TickerData",
    "OrderbookData",
    "TradeData",
    "KlineData",
    "BarRecord",
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
    # Sessions
    "SessionConfig",
    "BaseSession",
    "DemoSession",
    "LiveSession",
    "create_demo_session",
    "create_live_session",
    # Backend Protocol (future MongoDB)
    "HistoricalBackend",
    "MongoBackend",
]
