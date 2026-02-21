"""
Real-time state management for WebSocket-driven data.

This module provides a thread-safe, centralized store for real-time market
and account data received via WebSocket streams. It serves as the single
source of truth for live data across the trading system.

Architecture:
- Domain models: Normalized event and state types (in realtime_models.py)
- State containers: Thread-safe storage for each data type
- RealtimeState: Central manager that coordinates all state updates
- Event queue: Optional queue for event-driven processing

Usage:
    from src.data.realtime_state import get_realtime_state
    
    state = get_realtime_state()
    
    # Read current data
    ticker = state.get_ticker("BTCUSDT")
    positions = state.get_positions()
    
    # Check staleness
    if state.is_ticker_stale("BTCUSDT", max_age_seconds=5):
        # Fall back to REST
        pass
"""

import time
import threading
from collections.abc import Callable
from collections import defaultdict, deque
from typing import Any

import pandas as pd

from ..utils.logger import get_logger
from ..config.constants import DataEnv, validate_data_env

# Import all models from realtime_models
from .realtime_models import (
    # Enums
    EventType,
    ConnectionState,
    STALENESS_THRESHOLDS,
    # Market data models
    TickerData,
    OrderbookLevel,
    OrderbookData,
    TradeData,
    KlineData,
    BarRecord,
    BAR_BUFFER_SIZES,
    get_bar_buffer_size,
    # Account data models
    PositionData,
    OrderData,
    ExecutionData,
    WalletData,
    AccountMetrics,
    PortfolioRiskSnapshot,
    # Utility classes
    RealtimeEvent,
    ConnectionStatus,
)

__all__ = [
    # Main class
    "RealtimeState",
    "get_realtime_state",
    "reset_realtime_state",
    # Enums
    "EventType",
    "ConnectionState",
    "STALENESS_THRESHOLDS",
    # Market data models
    "TickerData",
    "OrderbookLevel",
    "OrderbookData",
    "TradeData",
    "KlineData",
    "BarRecord",
    "BAR_BUFFER_SIZES",
    "get_bar_buffer_size",
    # Account data models
    "PositionData",
    "OrderData",
    "ExecutionData",
    "WalletData",
    "AccountMetrics",
    "PortfolioRiskSnapshot",
    # Utility classes
    "RealtimeEvent",
    "ConnectionStatus",
]


class RealtimeState:
    """
    Thread-safe centralized state manager for real-time data.
    
    This is the single source of truth for all WebSocket-delivered data.
    It provides:
    - Thread-safe read/write access to all state
    - Staleness detection for all data types
    - Event queue for event-driven processing
    - Connection status tracking
    - Callbacks for state changes
    
    Usage:
        state = RealtimeState()
        
        # Update from WebSocket callback
        state.update_ticker(TickerData.from_bybit(msg["data"]))
        
        # Read current state
        ticker = state.get_ticker("BTCUSDT")
        
        # Check staleness
        if state.is_ticker_stale("BTCUSDT"):
            # Fall back to REST
            pass
        
        # Register callbacks
        state.on_ticker_update(lambda t: print(f"New price: {t.last_price}"))
    """
    
    def __init__(self):
        """Initialize realtime state manager."""
        self.logger = get_logger()

        # Locks for thread-safety
        self._lock = threading.RLock()
        self._callback_lock = threading.Lock()

        # Public market data state
        self._tickers: dict[str, TickerData] = {}
        self._orderbooks: dict[str, OrderbookData] = {}
        self._klines: dict[str, dict[str, KlineData]] = defaultdict(dict)  # {symbol: {interval: kline}}
        self._recent_trades: dict[str, deque[TradeData]] = defaultdict(lambda: deque(maxlen=100))

        # Private account data state
        self._positions: dict[str, PositionData] = {}  # {symbol: position}
        self._orders: dict[str, OrderData] = {}  # {order_id: order}
        self._executions: deque[ExecutionData] = deque(maxlen=500)
        self._wallet: dict[str, WalletData] = {}  # {coin: wallet}
        self._account_metrics: AccountMetrics | None = None  # Unified account-level metrics

        # Connection status
        self._public_ws_status = ConnectionStatus()
        self._private_ws_status = ConnectionStatus()

        # Callbacks
        self._ticker_callbacks: list[Callable[[TickerData], None]] = []
        self._orderbook_callbacks: list[Callable[[OrderbookData], None]] = []
        self._trade_callbacks: list[Callable[[TradeData], None]] = []
        self._kline_callbacks: list[Callable[[KlineData], None]] = []
        self._position_callbacks: list[Callable[[PositionData], None]] = []
        self._order_callbacks: list[Callable[[OrderData], None]] = []
        self._execution_callbacks: list[Callable[[ExecutionData], None]] = []
        self._wallet_callbacks: list[Callable[[WalletData], None]] = []
        self._account_metrics_callbacks: list[Callable[[AccountMetrics], None]] = []

        # Stats
        self._update_counts: dict[str, int] = defaultdict(int)
        self._started_at = time.time()
        
        # Configuration
        self._max_recent_trades = 100
        self._max_executions = 500
        
        # ==============================================================================
        # Bar Buffers - Environment-scoped bar storage for any timeframe
        # ==============================================================================
        # Structure: env -> symbol -> timeframe -> deque[BarRecord]
        # Used for strategy warm-up and lookback during live execution
        self._bar_buffers: dict[str, dict[str, dict[str, deque[BarRecord]]]] = {
            "live": defaultdict(lambda: defaultdict(deque)),
            "demo": defaultdict(lambda: defaultdict(deque)),
        }
    
    # ==========================================================================
    # Public Data - Tickers
    # ==========================================================================
    
    def update_ticker(self, ticker: TickerData):
        """Update ticker state (thread-safe)."""
        with self._lock:
            self._tickers[ticker.symbol] = ticker
            self._update_counts["ticker"] += 1
        

        self._invoke_callbacks(self._ticker_callbacks, ticker)
    
    def get_ticker(self, symbol: str) -> TickerData | None:
        """Get ticker for a symbol (thread-safe)."""
        with self._lock:
            return self._tickers.get(symbol)

    def get_all_tickers(self) -> dict[str, TickerData]:
        """Get all tickers (thread-safe copy)."""
        with self._lock:
            return dict(self._tickers)
    
    def is_ticker_stale(self, symbol: str, max_age_seconds: float | None = None) -> bool:
        """Check if ticker is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["ticker"]
        with self._lock:
            ticker = self._tickers.get(symbol)
            if not ticker:
                return True
            return (time.time() - ticker.timestamp) > max_age
    
    
    # ==========================================================================
    # Public Data - Orderbooks
    # ==========================================================================
    
    def update_orderbook(self, orderbook: OrderbookData, is_snapshot: bool = True):
        """Update orderbook state (thread-safe)."""
        with self._lock:
            if is_snapshot:
                self._orderbooks[orderbook.symbol] = orderbook
            else:
                # Apply delta to existing orderbook
                existing = self._orderbooks.get(orderbook.symbol)
                if existing:
                    existing.apply_delta({
                        "b": [[l.price, l.size] for l in orderbook.bids],
                        "a": [[l.price, l.size] for l in orderbook.asks],
                        "u": orderbook.update_id,
                    })
                else:
                    self._orderbooks[orderbook.symbol] = orderbook

            self._update_counts["orderbook"] += 1
            callback_data = self._orderbooks.get(orderbook.symbol)

        self._invoke_callbacks(self._orderbook_callbacks, callback_data)
    
    def apply_orderbook_delta(self, symbol: str, delta: dict):
        """Apply delta update to orderbook."""
        with self._lock:
            existing = self._orderbooks.get(symbol)
            if existing:
                existing.apply_delta(delta)
                self._update_counts["orderbook"] += 1

                self._invoke_callbacks(self._orderbook_callbacks, existing)
    
    
    # ==========================================================================
    # Public Data - Klines
    # ==========================================================================
    
    def update_kline(self, kline: KlineData):
        """Update kline state (thread-safe)."""
        with self._lock:
            self._klines[kline.symbol][kline.interval] = kline
            self._update_counts["kline"] += 1
        
        self._invoke_callbacks(self._kline_callbacks, kline)
    
    def get_kline(self, symbol: str, interval: str) -> KlineData | None:
        """Get latest kline for symbol and interval."""
        with self._lock:
            return self._klines.get(symbol, {}).get(interval)

    def get_all_klines(self, symbol: str) -> dict[str, KlineData]:
        """Get all klines for a symbol."""
        with self._lock:
            return dict(self._klines.get(symbol, {}))
    
    def is_kline_stale(self, symbol: str, interval: str, max_age_seconds: float | None = None) -> bool:
        """Check if kline is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["kline"]
        with self._lock:
            kline = self._klines.get(symbol, {}).get(interval)
            if not kline:
                return True
            return (time.time() - kline.timestamp) > max_age
    
    def on_kline_update(self, callback: Callable[[KlineData], None]):
        """Register callback for kline updates."""
        with self._callback_lock:
            self._kline_callbacks.append(callback)
    
    # ==========================================================================
    # Bar Buffers - Environment-scoped bar storage for any timeframe
    # ==========================================================================

    def init_bar_buffer(
        self,
        env: DataEnv,
        symbol: str,
        timeframe: str,
        bars_df: pd.DataFrame,
        max_size: int | None = None,
    ) -> int:
        """
        Initialize a bar ring buffer from historical DataFrame.

        Args:
            env: Data environment ("live" or "demo")
            symbol: Trading symbol (e.g., "BTCUSDT")
            timeframe: Bar timeframe (e.g., "15m", "1h", "4h")
            bars_df: DataFrame with OHLCV data
            max_size: Maximum buffer size (default: auto-sized based on timeframe)

        Returns:
            Number of bars loaded into the buffer
        """
        env = validate_data_env(env)
        symbol = symbol.upper()

        if max_size is None:
            max_size = get_bar_buffer_size(timeframe)

        with self._lock:
            buffer: deque[BarRecord] = deque(maxlen=max_size)

            count = 0
            for _, row in bars_df.iterrows():
                try:
                    bar = BarRecord.from_df_row(row)
                    buffer.append(bar)
                    count += 1
                except (KeyError, ValueError, TypeError) as e:
                    self.logger.debug(f"Skipping malformed row in bar buffer init: {e}")
                    continue

            self._bar_buffers[env][symbol][timeframe] = buffer

            self.logger.debug(
                f"Initialized bar buffer: env={env}, symbol={symbol}, "
                f"tf={timeframe}, bars={count}, max_size={max_size}"
            )

            return count

    def append_bar(
        self,
        env: DataEnv,
        symbol: str,
        timeframe: str,
        bar: BarRecord,
    ) -> bool:
        """Append a closed bar to a ring buffer."""
        env = validate_data_env(env)
        symbol = symbol.upper()

        with self._lock:
            if symbol not in self._bar_buffers[env]:
                self._bar_buffers[env][symbol] = defaultdict(deque)

            if timeframe not in self._bar_buffers[env][symbol]:
                self._bar_buffers[env][symbol][timeframe] = deque(
                    maxlen=get_bar_buffer_size(timeframe)
                )
                self.logger.warning(
                    f"Auto-initialized bar buffer: env={env}, symbol={symbol}, tf={timeframe}"
                )

            buffer = self._bar_buffers[env][symbol][timeframe]
            buffer.append(bar)

            return True

    def get_bar_buffer(
        self,
        env: DataEnv,
        symbol: str,
        timeframe: str,
        limit: int | None = None,
    ) -> list[BarRecord]:
        """Get bars from a ring buffer."""
        env = validate_data_env(env)
        symbol = symbol.upper()

        with self._lock:
            if symbol not in self._bar_buffers[env]:
                return []
            if timeframe not in self._bar_buffers[env][symbol]:
                return []

            buffer = self._bar_buffers[env][symbol][timeframe]

            if limit is None:
                return list(buffer)
            else:
                return list(buffer)[-limit:]

    def get_bar_buffer_as_df(
        self,
        env: DataEnv,
        symbol: str,
        timeframe: str,
        limit: int | None = None,
    ) -> pd.DataFrame:
        """Get bar buffer as a pandas DataFrame (OHLCV format)."""
        bars = self.get_bar_buffer(env, symbol, timeframe, limit)

        if not bars:
            return pd.DataFrame(columns=pd.Index(["timestamp", "open", "high", "low", "close", "volume"]))

        data = [
            {
                "timestamp": b.timestamp,
                "open": b.open, "high": b.high, "low": b.low,
                "close": b.close, "volume": b.volume,
            }
            for b in bars
        ]

        return pd.DataFrame(data)

    def get_bar_buffer_stats(self, env: DataEnv | None = None) -> dict[str, Any]:
        """Get statistics about bar buffers."""
        with self._lock:
            stats = {}
            envs = [env] if env else ["live", "demo"]

            for e in envs:
                stats[e] = {}
                for symbol, tf_buffers in self._bar_buffers[e].items():
                    stats[e][symbol] = {}
                    for tf, buffer in tf_buffers.items():
                        if len(buffer) > 0:
                            stats[e][symbol][tf] = {
                                "count": len(buffer),
                                "max_size": buffer.maxlen,
                                "oldest": buffer[0].timestamp.isoformat() if buffer else None,
                                "newest": buffer[-1].timestamp.isoformat() if buffer else None,
                            }

            return stats

    # ==========================================================================
    # Public Data - Trades
    # ==========================================================================
    
    def add_trade(self, trade: TradeData):
        """Add a public trade (thread-safe)."""
        with self._lock:
            self._recent_trades[trade.symbol].append(trade)
            self._update_counts["trade"] += 1

        self._invoke_callbacks(self._trade_callbacks, trade)
    
    
    # ==========================================================================
    # Private Data - Positions
    # ==========================================================================
    
    def update_position(self, position: PositionData):
        """Update position state (thread-safe)."""
        with self._lock:
            if position.is_open:
                self._positions[position.symbol] = position
            else:
                self._positions.pop(position.symbol, None)
            self._update_counts["position"] += 1

        self._invoke_callbacks(self._position_callbacks, position)
    
    def get_position(self, symbol: str) -> PositionData | None:
        """Get position for a symbol."""
        with self._lock:
            return self._positions.get(symbol)

    def get_all_positions(self) -> dict[str, PositionData]:
        """Get all open positions."""
        with self._lock:
            return dict(self._positions)
    
    
    # ==========================================================================
    # Private Data - Orders
    # ==========================================================================
    
    def update_order(self, order: OrderData):
        """Update order state (thread-safe)."""
        with self._lock:
            if order.is_open:
                self._orders[order.order_id] = order
            else:
                self._orders.pop(order.order_id, None)
            self._update_counts["order"] += 1

        self._invoke_callbacks(self._order_callbacks, order)
    
    def get_open_orders(self, symbol: str | None = None) -> list[OrderData]:
        """Get open orders, optionally filtered by symbol."""
        with self._lock:
            orders = list(self._orders.values())
            if symbol:
                orders = [o for o in orders if o.symbol == symbol]
            return orders
    
    
    # ==========================================================================
    # Private Data - Executions
    # ==========================================================================
    
    def add_execution(self, execution: ExecutionData):
        """Add an execution (thread-safe)."""
        with self._lock:
            self._executions.append(execution)
            self._update_counts["execution"] += 1

        self._invoke_callbacks(self._execution_callbacks, execution)
    
    
    # ==========================================================================
    # Private Data - Wallet
    # ==========================================================================
    
    def update_wallet(self, wallet: WalletData):
        """Update wallet state (thread-safe)."""
        with self._lock:
            self._wallet[wallet.coin] = wallet
            self._update_counts["wallet"] += 1

        self._invoke_callbacks(self._wallet_callbacks, wallet)
    
    def get_wallet(self, coin: str = "USDT") -> WalletData | None:
        """Get wallet for a coin."""
        with self._lock:
            return self._wallet.get(coin)

    def is_wallet_stale(self, coin: str = "USDT", max_age_seconds: float | None = None) -> bool:
        """Check if wallet data is stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["wallet"]
        with self._lock:
            wallet = self._wallet.get(coin)
            if not wallet:
                return True
            return (time.time() - wallet.timestamp) > max_age
    
    
    # ==========================================================================
    # Private Data - Account Metrics (Unified Account-Level)
    # ==========================================================================
    
    def update_account_metrics(self, metrics: AccountMetrics):
        """Update unified account metrics (thread-safe)."""
        with self._lock:
            self._account_metrics = metrics
            self._update_counts["account_metrics"] += 1

        self._invoke_callbacks(self._account_metrics_callbacks, metrics)
    
    def get_account_metrics(self) -> AccountMetrics | None:
        """Get unified account metrics."""
        with self._lock:
            return self._account_metrics
    
    def is_account_metrics_stale(self, max_age_seconds: float | None = None) -> bool:
        """Check if account metrics are stale."""
        max_age = max_age_seconds or STALENESS_THRESHOLDS["wallet"]
        with self._lock:
            if not self._account_metrics:
                return True
            return (time.time() - self._account_metrics.timestamp) > max_age
    
    
    # ==========================================================================
    # Connection Status
    # ==========================================================================
    
    def set_public_ws_connected(self):
        """Mark public WebSocket as connected."""
        with self._lock:
            self._public_ws_status.state = ConnectionState.CONNECTED
            self._public_ws_status.connected_at = time.time()

    def set_public_ws_disconnected(self, error: str | None = None):
        """Mark public WebSocket as disconnected."""
        with self._lock:
            self._public_ws_status.state = ConnectionState.DISCONNECTED
            self._public_ws_status.disconnected_at = time.time()
            if error:
                self._public_ws_status.last_error = error

    def set_public_ws_reconnecting(self):
        """Mark public WebSocket as reconnecting."""
        with self._lock:
            self._public_ws_status.state = ConnectionState.RECONNECTING
            self._public_ws_status.reconnect_count += 1

    def set_private_ws_connected(self):
        """Mark private WebSocket as connected."""
        with self._lock:
            self._private_ws_status.state = ConnectionState.CONNECTED
            self._private_ws_status.connected_at = time.time()

    def set_private_ws_disconnected(self, error: str | None = None):
        """Mark private WebSocket as disconnected."""
        with self._lock:
            self._private_ws_status.state = ConnectionState.DISCONNECTED
            self._private_ws_status.disconnected_at = time.time()
            if error:
                self._private_ws_status.last_error = error

    def set_private_ws_reconnecting(self):
        """Mark private WebSocket as reconnecting."""
        with self._lock:
            self._private_ws_status.state = ConnectionState.RECONNECTING
            self._private_ws_status.reconnect_count += 1

    def get_public_ws_status(self) -> ConnectionStatus:
        """Get public WebSocket status."""
        return self._public_ws_status
    
    def get_private_ws_status(self) -> ConnectionStatus:
        """Get private WebSocket status."""
        return self._private_ws_status
    
    @property
    def is_public_ws_connected(self) -> bool:
        with self._lock:
            return self._public_ws_status.is_connected

    @property
    def is_private_ws_connected(self) -> bool:
        with self._lock:
            return self._private_ws_status.is_connected

    def is_websocket_healthy(self, max_stale_seconds: float = 30.0) -> bool:  # noqa: ARG002
        """
        G1-4: Check if WebSocket connections are healthy.

        Healthy means:
        - Private WebSocket is connected
        - We have received wallet/account data at least once

        NOTE: Bybit private streams are event-driven — wallet updates only
        arrive when the balance actually changes. We cannot use data freshness
        as a health signal because idle accounts won't receive updates for
        minutes or hours. Connection state is the only reliable indicator.

        Args:
            max_stale_seconds: Not used for health (kept for API compat).
                Use is_wallet_stale() / is_account_metrics_stale() directly
                when you need data-freshness checks.

        Returns:
            True if private WebSocket is connected and has seeded data
        """
        # Check private WebSocket connection (needed for trading)
        if not self.is_private_ws_connected:
            self.logger.debug(
                "WS health: private WS not connected "
                f"(state={self._private_ws_status.state.value}, "
                f"last_error={self._private_ws_status.last_error})"
            )
            return False

        # Require that we received wallet data at least once (REST seed or WS)
        with self._lock:
            has_wallet = bool(self._wallet.get("USDT"))
            has_metrics = self._account_metrics is not None

        if not has_wallet and not has_metrics:
            self.logger.debug(
                "WS health: no wallet or account metrics data received yet"
            )
            return False

        return True

    # ==========================================================================
    # Callbacks
    # ==========================================================================
    
    def _invoke_callbacks(self, callbacks: list[Callable], data):
        """Invoke all registered callbacks (copy-under-lock for thread safety)."""
        with self._callback_lock:
            callbacks_copy = list(callbacks)
        for callback in callbacks_copy:
            try:
                callback(data)
            except Exception as e:
                self.logger.error(f"Callback error: {e}")
    
    # ==========================================================================
    # State Management
    # ==========================================================================

    def clear_all(self):
        """Clear all state data."""
        with self._lock:
            self._tickers.clear()
            self._orderbooks.clear()
            self._klines.clear()
            self._recent_trades.clear()
            self._positions.clear()
            self._orders.clear()
            self._executions.clear()
            self._wallet.clear()
            self._account_metrics = None
            self._update_counts.clear()

        self.logger.info("RealtimeState cleared")
    
    # ==========================================================================
    # Portfolio Risk Snapshot
    # ==========================================================================
    
    def build_portfolio_snapshot(self, config=None) -> PortfolioRiskSnapshot:
        """
        Build a comprehensive portfolio risk snapshot.
        
        This aggregates all position and account data into a single,
        point-in-time view suitable for risk analysis and agent consumption.
        """
        with self._lock:
            return PortfolioRiskSnapshot.from_state(
                account_metrics=self._account_metrics,
                positions=dict(self._positions),
                config=config,
            )
    
    # ==========================================================================
    # Statistics and Status
    # ==========================================================================
    
    def get_stats(self) -> dict:
        """Get state statistics."""
        with self._lock:
            return {
                "uptime_seconds": time.time() - self._started_at,
                "ticker_count": len(self._tickers),
                "orderbook_count": len(self._orderbooks),
                "position_count": len(self._positions),
                "open_order_count": len(self._orders),
                "execution_count": len(self._executions),
                "update_counts": dict(self._update_counts),
                "public_ws": self._public_ws_status.to_dict(),
                "private_ws": self._private_ws_status.to_dict(),
            }
    
    def get_summary(self) -> dict:
        """Get a summary of current state."""
        with self._lock:
            total_unrealized_pnl = sum(p.unrealized_pnl for p in self._positions.values())
            usdt_wallet = self._wallet.get("USDT")
            
            return {
                "connected": {
                    "public": self.is_public_ws_connected,
                    "private": self.is_private_ws_connected,
                },
                "market_data": {
                    "symbols_tracked": list(self._tickers.keys()),
                    "ticker_count": len(self._tickers),
                },
                "account": {
                    "positions": len(self._positions),
                    "open_orders": len(self._orders),
                    "unrealized_pnl": total_unrealized_pnl,
                    "balance": usdt_wallet.wallet_balance if usdt_wallet else 0,
                    "available": usdt_wallet.available_balance if usdt_wallet else 0,
                },
                "updates": dict(self._update_counts),
            }


# ==============================================================================
# Singleton Instance
# ==============================================================================

_realtime_state: RealtimeState | None = None
_state_lock = threading.Lock()


def get_realtime_state() -> RealtimeState:
    """Get or create the global RealtimeState instance."""
    global _realtime_state
    with _state_lock:
        if _realtime_state is None:
            _realtime_state = RealtimeState()
        return _realtime_state


def reset_realtime_state():
    """Reset the global RealtimeState instance (for testing)."""
    global _realtime_state
    with _state_lock:
        if _realtime_state:
            _realtime_state.clear_all()
        _realtime_state = None
