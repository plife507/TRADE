"""
Real-time WebSocket bootstrap and management.

This module initializes and manages WebSocket connections, subscribes to
topics, and feeds data into RealtimeState.

Features:
- Automatic subscription to configured symbols and topics
- Connection state management with reconnection support
- Callback normalization (converts raw Bybit payloads to domain models)
- Public and private stream management
- Graceful shutdown

Usage:
    from src.data.realtime_bootstrap import RealtimeBootstrap, get_realtime_bootstrap
    
    # Initialize and start
    bootstrap = get_realtime_bootstrap()
    bootstrap.start(symbols=["BTCUSDT", "ETHUSDT"])
    
    # Check status
    print(bootstrap.get_status())
    
    # Stop
    bootstrap.stop()
"""

import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING

from ..exchanges.bybit_client import BybitClient
from ..config.config import get_config
from ..config.constants import DataEnv, validate_data_env
from ..utils.logger import get_logger
from .realtime_state import (
    get_realtime_state,
    RealtimeState,
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
)

if TYPE_CHECKING:
    from .historical_data_store import HistoricalDataStore


class StreamType(Enum):
    """Types of streams to subscribe to."""
    TICKER = "ticker"
    ORDERBOOK = "orderbook"
    TRADES = "trades"
    KLINES = "klines"
    POSITIONS = "positions"
    ORDERS = "orders"
    EXECUTIONS = "executions"
    WALLET = "wallet"


@dataclass
class SubscriptionConfig:
    """
    Configuration for stream subscriptions.
    
    WebSocket Endpoint Modes (technical endpoints):
    - LIVE: stream.bybit.com (REAL MONEY)
    - DEMO: stream-demo.bybit.com (FAKE MONEY)
    
    For PUBLIC streams (market data), you can optionally use LIVE streams
    even when trading in DEMO mode since market data is identical.
    
    For PRIVATE streams (positions, orders), the stream must match your
    API environment since authentication is account-specific.
    """
    # Public streams
    enable_ticker: bool = True
    enable_orderbook: bool = False  # High frequency, enable only if needed
    enable_trades: bool = False     # High frequency, enable only if needed
    enable_klines: bool = True
    
    # Kline intervals to subscribe (Bybit format: 1, 5, 15, 60, etc.)
    kline_intervals: list[str] = field(default_factory=lambda: ["15"])
    
    # Orderbook depth (1, 25, 50, 100, 200)
    orderbook_depth: int = 50
    
    # Private streams
    enable_positions: bool = True
    enable_orders: bool = True
    enable_executions: bool = True
    enable_wallet: bool = True
    
    # Advanced: Use LIVE WebSocket for public market data even in DEMO mode
    # This can be useful if DEMO WebSocket streams have connectivity issues
    # Market data (tickers, orderbook, klines) is the same on LIVE and DEMO
    use_live_for_public_streams: bool = False
    
    @classmethod
    def market_data_only(cls) -> 'SubscriptionConfig':
        """Config for public market data only."""
        return cls(
            enable_ticker=True,
            enable_orderbook=False,
            enable_trades=False,
            enable_klines=True,
            enable_positions=False,
            enable_orders=False,
            enable_executions=False,
            enable_wallet=False,
        )
    
    @classmethod
    def full(cls) -> 'SubscriptionConfig':
        """Config for all streams."""
        return cls(
            enable_ticker=True,
            enable_orderbook=True,
            enable_trades=True,
            enable_klines=True,
            enable_positions=True,
            enable_orders=True,
            enable_executions=True,
            enable_wallet=True,
        )
    
    @classmethod
    def demo_safe(cls) -> 'SubscriptionConfig':
        """
        Config optimized for DEMO mode (FAKE MONEY).
        
        Uses LIVE streams for public data (more reliable) while keeping
        private streams on DEMO for account data.
        """
        return cls(
            enable_ticker=True,
            enable_orderbook=False,
            enable_trades=False,
            enable_klines=True,
            enable_positions=True,
            enable_orders=True,
            enable_executions=True,
            enable_wallet=True,
            use_live_for_public_streams=True,  # Use LIVE streams for market data
        )


class RealtimeBootstrap:
    """
    Manages WebSocket connections and feeds data into RealtimeState.
    
    This class handles:
    - Creating and managing WebSocket connections (public + private)
    - Subscribing to configured topics
    - Parsing raw Bybit messages into domain models
    - Updating RealtimeState with new data
    - Connection state tracking and reconnection
    
    Example:
        bootstrap = RealtimeBootstrap()
        bootstrap.start(symbols=["BTCUSDT", "ETHUSDT"])
        
        # Data is now flowing into RealtimeState
        state = get_realtime_state()
        ticker = state.get_ticker("BTCUSDT")
    """
    
    def __init__(
        self,
        client: BybitClient | None = None,
        state: RealtimeState | None = None,
        config: SubscriptionConfig | None = None,
        env: DataEnv | None = None,
    ):
        """
        Initialize bootstrap.
        
        Args:
            client: BybitClient instance (creates one if None)
            state: RealtimeState instance (uses global if None)
            config: Subscription configuration
            env: Data environment ("live" or "demo"). If None, inferred from use_demo config.
        """
        self.app_config = get_config()
        self.logger = get_logger()
        
        # Determine data environment
        # If not specified, infer from use_demo config (demo trading -> demo env)
        if env is None:
            self.env: DataEnv = "demo" if self.app_config.bybit.use_demo else "live"
        else:
            self.env = validate_data_env(env)
        
        # Initialize client
        if client:
            self.client = client
        else:
            api_key, api_secret = self.app_config.bybit.get_credentials()
            self.client = BybitClient(
                api_key=api_key,
                api_secret=api_secret,
                use_demo=self.app_config.bybit.use_demo,
            )
        
        # Log WebSocket environment (matches trading mode)
        ws_env = "DEMO (stream-demo.bybit.com)" if self.app_config.bybit.use_demo else "LIVE (stream.bybit.com)"
        account_type = "fake-money demo account" if self.app_config.bybit.use_demo else "real-money live account"
        self.logger.info(
            f"RealtimeBootstrap: data_env={self.env}, "
            f"WebSocket environment={ws_env}, account={account_type}"
        )
        
        # State management
        self.state = state or get_realtime_state()
        self.sub_config = config or SubscriptionConfig()
        
        # Tracking
        self._symbols: set[str] = set()
        self._running = False
        self._public_connected = False
        self._private_connected = False
        self._stale_logged = False

        # Real-time bar persistence configuration
        # When a closed bar is received:
        # 1. Append to in-memory buffer for hot-path access
        # 2. Persist to DuckDB for warm-up/recovery/history
        self._persist_closed_bars_to_memory: bool = True
        self._persist_closed_bars_to_db: bool = True

        # Database store for persistence (lazy initialized)
        self._db_store: "HistoricalDataStore | None" = None

        # Thread management
        self._lock = threading.Lock()
        self._monitor_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
    
    # ==========================================================================
    # Main Control
    # ==========================================================================
    
    def start(
        self,
        symbols: list[str] | None = None,
        include_private: bool = True,
    ):
        """
        Start WebSocket connections and subscriptions.
        
        Args:
            symbols: List of symbols to subscribe to
            include_private: Whether to include private streams
        """
        with self._lock:
            if self._running:
                self.logger.warning("RealtimeBootstrap already running")
                return
            
            self._running = True
            self._stop_event.clear()
        
        # Determine symbols
        if symbols:
            self._symbols = set(symbols)
        else:
            self._symbols = set(self.app_config.trading.default_symbols)
        
        if not self._symbols:
            self.logger.warning("No symbols configured for WebSocket streams")
        
        self.logger.info(f"Starting RealtimeBootstrap for symbols: {list(self._symbols)}")
        
        try:
            # Start public streams
            self._start_public_streams()
            
            # Start private streams if enabled and credentials available
            if include_private and self.client.api_key:
                self._start_private_streams()
            elif include_private:
                self.logger.warning("Private streams requested but no API credentials available")
            
            # Start monitor thread for connection health
            self._monitor_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="RealtimeBootstrapMonitor"
            )
            self._monitor_thread.start()
            
        except Exception as e:
            # Suppress verbose rate limit errors - already logged once
            error_msg = str(e)
            if "Too many connection attempts" not in error_msg:
                self.logger.error(f"Failed to start RealtimeBootstrap: {e}")
            self._running = False
            raise
    
    def stop(self):
        """Stop all WebSocket connections and clean up."""
        self.logger.info("Stopping RealtimeBootstrap...")
        
        with self._lock:
            self._running = False
            self._stop_event.set()
        
        # Small delay to allow pybit ping threads to finish gracefully
        time.sleep(0.5)
        
        # Close WebSocket connections (suppress pybit internal thread exceptions)
        try:
            self.client.close_websockets()
        except Exception as e:
            # Ignore WebSocket close errors (expected when connection already closing)
            if "closed" not in str(e).lower():
                self.logger.warning(f"Error closing WebSockets: {e}")
        
        # Wait for monitor thread
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
        
        # Update connection status
        self.state.set_public_ws_disconnected()
        self.state.set_private_ws_disconnected()
        
        self._public_connected = False
        self._private_connected = False
        
        self.logger.info("RealtimeBootstrap stopped")
    
    def add_symbol(self, symbol: str):
        """Add a symbol to track (requires restart to take effect)."""
        with self._lock:
            self._symbols.add(symbol)
    
    def remove_symbol(self, symbol: str):
        """Remove a symbol from tracking (requires restart to take effect)."""
        with self._lock:
            self._symbols.discard(symbol)
    
    def subscribe_symbol_dynamic(self, symbol: str) -> bool:
        """
        Dynamically subscribe to public streams for a symbol.

        Call this when opening a position on a new symbol to get
        real-time market data for it.

        Args:
            symbol: Symbol to subscribe to (e.g., "SOLUSDT")

        Returns:
            True if subscribed successfully, False otherwise
        """
        symbol = symbol.upper()

        # Hold the lock for the entire check-then-subscribe sequence
        # to prevent TOCTOU race where _ws_public disconnects between
        # the check and the actual subscribe calls.
        with self._lock:
            if symbol in self._symbols:
                return True  # Already tracking

            # Check if WebSocket is connected
            if not self._public_connected or not self.client._ws_public:
                self.logger.debug(f"WebSocket not connected - {symbol} will use REST")
                return False

            try:
                self.logger.info(f"Dynamically subscribing to {symbol}...")

                # Subscribe to ticker (most important for position tracking)
                if self.sub_config.enable_ticker:
                    self.client.subscribe_ticker(symbol, self._on_ticker)

                # Subscribe to other streams based on config
                if self.sub_config.enable_orderbook:
                    self.client.subscribe_orderbook(
                        symbol, self._on_orderbook,
                        depth=self.sub_config.orderbook_depth
                    )

                if self.sub_config.enable_trades:
                    self.client.subscribe_trades(symbol, self._on_trades)

                if self.sub_config.enable_klines:
                    for interval in self.sub_config.kline_intervals:
                        try:
                            interval_val: int | str = int(interval)
                        except ValueError:
                            # Non-numeric intervals like "D", "W"
                            interval_val = interval
                        self.client.subscribe_klines(symbol, interval_val, self._on_kline)

                # Track that we're now subscribed
                self._symbols.add(symbol)

                self.logger.info(f"Subscribed to {symbol} streams")
                return True

            except Exception as e:
                self.logger.warning(f"Failed to subscribe to {symbol}: {e}")
                return False
    
    def ensure_symbol_subscribed(self, symbol: str) -> bool:
        """
        Ensure a symbol is subscribed - either already tracked or dynamically add it.
        
        This is the main entry point for tools/agents to ensure market data
        is available for a symbol they're about to trade.
        
        Args:
            symbol: Symbol to ensure subscription for
            
        Returns:
            True if symbol is/will be tracked, False if WebSocket unavailable
        """
        symbol = symbol.upper()
        
        with self._lock:
            if symbol in self._symbols:
                return True
        
        # Try dynamic subscription
        return self.subscribe_symbol_dynamic(symbol)

    def subscribe_kline_intervals(self, symbol: str, intervals: list[str]) -> None:
        """
        Subscribe to additional kline intervals for a symbol.

        Call this when the engine needs kline data for timeframes not in the
        original subscription config (e.g., multi-timeframe strategies).

        Args:
            symbol: Symbol to subscribe klines for (e.g., "BTCUSDT")
            intervals: Bybit-format intervals (e.g., ["15", "60", "D"])
        """
        symbol = symbol.upper()

        # Hold the lock for the entire check-then-subscribe sequence
        # to prevent TOCTOU race where _ws_public disconnects between
        # the check and the actual subscribe calls.
        with self._lock:
            already = set(self.sub_config.kline_intervals)
            new_intervals = [iv for iv in intervals if iv not in already]

            if not new_intervals:
                return

            if not self._public_connected or not self.client._ws_public:
                self.logger.warning(
                    f"Cannot subscribe kline intervals {new_intervals} - "
                    "public WebSocket not connected"
                )
                return

            for interval in new_intervals:
                try:
                    interval_int: int | str = int(interval)
                except ValueError:
                    interval_int = interval
                self.client.subscribe_klines(symbol, interval_int, self._on_kline)
                self.logger.info(f"Subscribed to kline.{interval}.{symbol}")

            self.sub_config.kline_intervals.extend(new_intervals)

    # ==========================================================================
    # Public Streams
    # ==========================================================================
    
    def _start_public_streams(self):
        """
        Initialize public WebSocket streams.
        
        For DEMO mode, public streams (market data) can optionally use LIVE
        endpoints since the market data is the same. This is configured via
        sub_config.use_live_for_public_streams.
        """
        # Determine stream mode for logging using DEMO/LIVE terminology
        if self.sub_config.use_live_for_public_streams:
            stream_mode = "LIVE (market data shared)"
        elif self.app_config.bybit.is_demo:
            stream_mode = "DEMO"
        else:
            stream_mode = "LIVE"
        
        self.logger.info(f"Starting public WebSocket streams ({stream_mode})...")
        
        try:
            # Connect to public WebSocket with appropriate mode
            # This creates the WebSocket connection with correct endpoint
            self.client.connect_public_ws(
                channel_type="linear",
                use_live_for_market_data=self.sub_config.use_live_for_public_streams,
            )
            
            # Ticker streams
            if self.sub_config.enable_ticker and self._symbols:
                for symbol in self._symbols:
                    self.client.subscribe_ticker(symbol, self._on_ticker)
            
            # Orderbook streams
            if self.sub_config.enable_orderbook and self._symbols:
                for symbol in self._symbols:
                    self.client.subscribe_orderbook(
                        symbol,
                        self._on_orderbook,
                        depth=self.sub_config.orderbook_depth
                    )
            
            # Trade streams
            if self.sub_config.enable_trades and self._symbols:
                for symbol in self._symbols:
                    self.client.subscribe_trades(symbol, self._on_trades)
            
            # Kline streams
            if self.sub_config.enable_klines and self._symbols:
                for symbol in self._symbols:
                    for interval in self.sub_config.kline_intervals:
                        # Convert interval to int for pybit
                        try:
                            interval_int = int(interval)
                        except ValueError:
                            # Handle non-numeric intervals like "D", "W"
                            interval_int = interval
                        self.client.subscribe_klines(symbol, interval_int, self._on_kline)
            
            self._public_connected = True
            self.state.set_public_ws_connected()
            self.logger.info("Public WebSocket streams started")
            
        except Exception as e:
            # Log concisely - avoid flooding terminal with repeated errors
            error_msg = str(e)
            if "Too many connection attempts" in error_msg:
                self.logger.warning("WebSocket rate limited - using REST fallback")
            else:
                self.logger.error(f"Failed to start public streams: {e}")
            self.state.set_public_ws_disconnected(str(e))
            raise
    
    def _on_ticker(self, msg: dict):
        """Handle ticker update from WebSocket."""
        try:
            data = msg.get("data", {})

            if not data:
                return

            # Detect reconnection: data resumed but _public_connected was cleared
            if not self._public_connected:
                self._public_connected = True
                self.state.set_public_ws_connected()
                self._stale_logged = False
                self.logger.info("Public WebSocket reconnected (data resumed)")

            msg_type = msg.get("type", "")
            symbol = data.get("symbol", "")

            if msg_type == "delta" and symbol:
                # Delta messages only contain changed fields.
                # Merge into existing ticker to avoid zeroing out missing fields.
                existing = self.state.get_ticker(symbol)
                if existing:
                    ticker = existing.merge_delta(data)
                else:
                    # No existing ticker yet -- treat delta as snapshot
                    ticker = TickerData.from_bybit(data)
            else:
                # Snapshot: full replace
                ticker = TickerData.from_bybit(data)

            self.state.update_ticker(ticker)

        except Exception as e:
            self.logger.warning(f"Error processing ticker: {e}")
    
    def _on_orderbook(self, msg: dict):
        """Handle orderbook update from WebSocket."""
        try:
            topic = msg.get("topic", "")
            msg_type = msg.get("type", "")
            data = msg.get("data", {})
            
            if not data:
                return
            
            # Extract symbol from topic (e.g., "orderbook.50.BTCUSDT")
            parts = topic.split(".")
            symbol = parts[-1] if len(parts) >= 3 else ""
            
            if msg_type == "snapshot":
                orderbook = OrderbookData.from_bybit(data, symbol)
                self.state.update_orderbook(orderbook, is_snapshot=True)
            elif msg_type == "delta":
                # Apply delta to existing orderbook
                self.state.apply_orderbook_delta(symbol, data)
            
        except Exception as e:
            self.logger.warning(f"Error processing orderbook: {e}")
    
    def _on_trades(self, msg: dict):
        """Handle trade stream from WebSocket."""
        try:
            data = msg.get("data", [])
            
            if not isinstance(data, list):
                data = [data]
            
            for trade_data in data:
                trade = TradeData.from_bybit(trade_data)
                self.state.add_trade(trade)
            
        except Exception as e:
            self.logger.warning(f"Error processing trades: {e}")
    
    def _on_kline(self, msg: dict):
        """Handle kline update from WebSocket."""
        try:
            topic = msg.get("topic", "")
            data = msg.get("data", [])

            if not data:
                return

            # Detect reconnection: data resumed but _public_connected was cleared
            if not self._public_connected:
                self._public_connected = True
                self.state.set_public_ws_connected()
                self._stale_logged = False
                self.logger.info("Public WebSocket reconnected (data resumed)")

            # Handle list of klines
            if isinstance(data, list):
                for kline_data in data:
                    kline = KlineData.from_bybit(kline_data, topic)
                    self.state.update_kline(kline)
                    # Persist closed bars to memory and DB
                    if kline.is_closed:
                        self._on_bar_closed(kline)
            else:
                kline = KlineData.from_bybit(data, topic)
                self.state.update_kline(kline)
                # Persist closed bars to memory and DB
                if kline.is_closed:
                    self._on_bar_closed(kline)

        except Exception as e:
            self.logger.warning(f"Error processing kline: {e}")
    
    def _get_db_store(self) -> "HistoricalDataStore":
        """Lazy-initialize the database store for real-time persistence."""
        if self._db_store is None:
            from .historical_data_store import get_historical_store
            # Use env to get correct store (live or demo)
            self._db_store = get_historical_store(env=self.env)
        return self._db_store

    def _on_bar_closed(self, kline: KlineData):
        """
        Handle a closed bar - persist to memory and DuckDB.

        When a kline closes:
        1. Append to in-memory buffer for hot-path access
        2. Persist to DuckDB for warm-up/recovery/history
        """
        if not kline.is_closed:
            return

        # 1. Persist to in-memory buffer
        self._persist_bar_to_memory(kline)

        # 2. Persist to DuckDB
        self._persist_bar_to_db(kline)

    def _persist_bar_to_memory(self, kline: KlineData):
        """
        Append a closed bar to the in-memory buffer.

        This ensures the ring buffer stays up-to-date with new bars
        as they close during live execution.
        """
        if not self._persist_closed_bars_to_memory:
            return

        if not kline.is_closed:
            return

        try:
            # Convert to BarRecord and append
            bar = BarRecord.from_kline_data(kline)
            self.state.append_bar(
                env=self.env,
                symbol=kline.symbol,
                timeframe=kline.interval,
                bar=bar,
            )
        except Exception as e:
            self.logger.debug(f"Error appending to memory buffer: {e}")

    def _persist_bar_to_db(self, kline: KlineData):
        """
        Persist a closed bar to DuckDB.

        This enables:
        - Data recovery when moving out of active window
        - Warm-up on bot restart
        - Historical analysis of live execution
        """
        if not self._persist_closed_bars_to_db:
            return

        if not kline.is_closed:
            return

        try:
            store = self._get_db_store()
            # Convert start_time (int ms) to UTC-naive datetime for DuckDB
            ts_dt = datetime.fromtimestamp(
                kline.start_time / 1000, tz=timezone.utc
            ).replace(tzinfo=None)
            store.upsert_candle(
                symbol=kline.symbol,
                timeframe=kline.interval,
                timestamp=ts_dt,
                open_price=kline.open,
                high=kline.high,
                low=kline.low,
                close=kline.close,
                volume=kline.volume,
            )
        except Exception as e:
            self.logger.warning(f"Error persisting bar to DB: {e}")
    
    # ==========================================================================
    # Private Streams
    # ==========================================================================
    
    def _start_private_streams(self):
        """
        Initialize private WebSocket streams.
        
        IMPORTANT: Bybit WebSocket private streams do NOT send initial snapshots.
        Per Bybit docs: "There is no snapshot event given at the time when 
        the subscription is successful" (wallet stream docs).
        
        Therefore, we fetch initial state via REST API after subscribing.
        """
        self.logger.info("Starting private WebSocket streams...")
        
        try:
            # Position stream
            if self.sub_config.enable_positions:
                self.client.subscribe_positions(self._on_position)
            
            # Order stream
            if self.sub_config.enable_orders:
                self.client.subscribe_orders(self._on_order)
            
            # Execution stream
            if self.sub_config.enable_executions:
                self.client.subscribe_executions(self._on_execution)
            
            # Wallet stream
            if self.sub_config.enable_wallet:
                self.client.subscribe_wallet(self._on_wallet)
            
            # Fetch initial state via REST API BEFORE marking connected.
            # Bybit WebSocket does NOT send initial snapshots for private streams.
            # We must load the REST snapshot first so that WebSocket deltas
            # (which start arriving after set_private_ws_connected) don't
            # overwrite the REST snapshot with stale data.
            self._fetch_initial_private_state()

            self._private_connected = True
            self.state.set_private_ws_connected()
            self.logger.info("Private WebSocket streams started")
            
        except Exception as e:
            self.logger.error(f"Failed to start private streams: {e}")
            self.state.set_private_ws_disconnected(str(e))
            raise
    
    def _detect_private_reconnection(self):
        """Detect if private WS reconnected (pybit internal retry).

        Mirrors the public reconnection detection in _on_ticker/_on_kline.
        If data arrives but _private_connected was cleared (by stale handler),
        the connection has been restored by pybit's internal retry.
        """
        if not self._private_connected:
            self._private_connected = True
            self.state.set_private_ws_connected()
            self._stale_logged = False
            self.logger.info("Private WebSocket reconnected (data resumed)")

    def _on_position(self, msg: dict):
        """Handle position update from WebSocket."""
        try:
            data = msg.get("data", [])
            if not isinstance(data, list):
                data = [data]
            if not data:
                return

            self._detect_private_reconnection()

            for pos_data in data:
                position = PositionData.from_bybit(pos_data)
                self.state.update_position(position)

        except Exception as e:
            self.logger.warning(f"Error processing position: {e}")

    def _on_order(self, msg: dict):
        """Handle order update from WebSocket."""
        try:
            data = msg.get("data", [])
            if not isinstance(data, list):
                data = [data]
            if not data:
                return

            self._detect_private_reconnection()

            for order_data in data:
                order = OrderData.from_bybit(order_data)
                self.state.update_order(order)

        except Exception as e:
            self.logger.warning(f"Error processing order: {e}")

    def _on_execution(self, msg: dict):
        """Handle execution update from WebSocket."""
        try:
            data = msg.get("data", [])
            if not isinstance(data, list):
                data = [data]
            if not data:
                return

            self._detect_private_reconnection()

            for exec_data in data:
                execution = ExecutionData.from_bybit(exec_data)
                self.state.add_execution(execution)

        except Exception as e:
            self.logger.warning(f"Error processing execution: {e}")
    
    def _fetch_initial_private_state(self):
        """
        Fetch initial state for all private streams via REST API.
        
        IMPORTANT: Bybit WebSocket private streams do NOT send initial snapshots.
        Per Bybit docs: "There is no snapshot event given at the time when 
        the subscription is successful"
        
        This ensures we have the current state immediately after connecting,
        rather than waiting for the first update.
        """
        self.logger.info("Fetching initial private state via REST API...")
        
        # Fetch wallet/account balance
        if self.sub_config.enable_wallet:
            self._fetch_initial_wallet()
        
        # Fetch positions
        if self.sub_config.enable_positions:
            self._fetch_initial_positions()
        
        # Fetch open orders
        if self.sub_config.enable_orders:
            self._fetch_initial_orders()
    
    def _fetch_initial_wallet(self):
        """
        Fetch initial wallet balance via REST API.
        
        Uses BybitClient.get_balance() which properly handles the pybit
        response format (tuple of data, elapsed, headers) and extracts the account data.
        """
        try:
            self.logger.debug("Fetching initial wallet balance...")
            
            # Use the existing get_balance() method which handles response parsing correctly
            # This returns the first account dict from the list, not the raw response
            account_data = self.client.get_balance(account_type="UNIFIED")
            
            if not account_data:
                self.logger.warning("No wallet data returned from REST API")
                return False
            
            # Parse account-level metrics (same format as WebSocket)
            if account_data.get("accountType") or account_data.get("totalEquity"):
                account_metrics = AccountMetrics.from_bybit(account_data)
                self.state.update_account_metrics(account_metrics)
                self.logger.info(
                    f"Initial wallet: Equity=${account_metrics.total_equity:,.2f}, "
                    f"Available=${account_metrics.total_available_balance:,.2f}"
                )
            
            # Parse per-coin balances
            coins = account_data.get("coin", [])
            for coin_data in coins:
                wallet = WalletData.from_bybit(coin_data)
                self.state.update_wallet(wallet)
                if wallet.equity > 0:
                    self.logger.debug(f"  {wallet.coin}: ${wallet.equity:,.2f}")
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Could not fetch initial wallet: {e}")
            return False
    
    def _fetch_initial_positions(self):
        """
        Fetch initial positions via REST API.
        
        Uses BybitClient.get_positions() which properly handles the response.
        """
        try:
            self.logger.debug("Fetching initial positions...")
            
            # Get all positions for the symbols we're tracking
            positions = self.client.get_positions(settle_coin="USDT")
            
            if not positions:
                self.logger.debug("No open positions")
                return True
            
            count = 0
            for pos_data in positions:
                # Only process positions with size > 0
                size = float(pos_data.get("size", 0))
                if size > 0:
                    position = PositionData.from_bybit(pos_data)
                    self.state.update_position(position)
                    count += 1
                    self.logger.debug(
                        f"  {position.symbol}: {position.side} {position.size} "
                        f"@ ${position.entry_price:,.2f}"
                    )
            
            if count > 0:
                self.logger.info(f"Initial positions: {count} open position(s)")
            
            return True
            
        except Exception as e:
            self.logger.warning(f"Could not fetch initial positions: {e}")
            return False
    
    def _fetch_initial_orders(self):
        """
        Fetch initial open orders via REST API.
        
        Uses BybitClient.get_open_orders() which properly handles the response.
        """
        try:
            self.logger.debug("Fetching initial open orders...")
            
            # Get all open orders
            orders = self.client.get_open_orders()
            
            if not orders:
                self.logger.debug("No open orders")
                return True
            
            for order_data in orders:
                order = OrderData.from_bybit(order_data)
                self.state.update_order(order)
            
            self.logger.info(f"Initial orders: {len(orders)} open order(s)")
            return True
            
        except Exception as e:
            self.logger.warning(f"Could not fetch initial orders: {e}")
            return False
    
    def _on_wallet(self, msg: dict):
        """
        Handle wallet update from WebSocket.

        The wallet stream contains both:
        1. Account-level unified metrics (accountIMRate, totalEquity, etc.)
        2. Per-coin balances and margins

        We parse both and update RealtimeState accordingly.
        """
        try:
            data = msg.get("data", [])

            if not isinstance(data, list):
                data = [data]
            if not data:
                return

            self._detect_private_reconnection()

            for wallet_data in data:
                # Parse account-level metrics (unified account view)
                # These are at the top level of each wallet message
                if wallet_data.get("accountType") or wallet_data.get("totalEquity"):
                    account_metrics = AccountMetrics.from_bybit(wallet_data)
                    self.state.update_account_metrics(account_metrics)
                
                # Parse per-coin balances
                coins = wallet_data.get("coin", [])
                for coin_data in coins:
                    wallet = WalletData.from_bybit(coin_data)
                    self.state.update_wallet(wallet)
            
        except Exception as e:
            self.logger.warning(f"Error processing wallet: {e}")
    
    # ==========================================================================
    # Connection Monitoring
    # ==========================================================================
    
    def _monitor_loop(self):
        """Background thread to monitor connection health."""
        self.logger.debug("Starting connection monitor loop")
        
        last_update_counts = {}
        stale_check_count = 0
        
        while not self._stop_event.is_set():
            try:
                # Check connection health every 30 seconds
                self._stop_event.wait(30)
                
                if not self._running:
                    break
                
                # Get current stats
                stats = self.state.get_stats()
                current_update_counts = stats.get('update_counts', {})
                
                # Check if we're receiving data (stale check)
                if last_update_counts:
                    has_new_data = False
                    for key, count in current_update_counts.items():
                        if count > last_update_counts.get(key, 0):
                            has_new_data = True
                            break
                    
                    if not has_new_data:
                        stale_check_count += 1
                        if stale_check_count >= 2:  # 2 consecutive checks (60s) with no data
                            self._handle_stale_connection()
                            stale_check_count = 0
                    else:
                        stale_check_count = 0
                
                last_update_counts = dict(current_update_counts)
                
                # Log stats periodically (at debug level)
                self.logger.debug(
                    f"RealtimeState stats: updates={current_update_counts}, "
                    f"queue_size={stats.get('event_queue_size', 0)}"
                )
                
            except Exception as e:
                self.logger.warning(f"Error in monitor loop: {e}")
        
        self.logger.debug("Connection monitor loop stopped")
    
    def _handle_stale_connection(self):
        """Handle a potentially stale WebSocket connection.

        When no WS data has been received for 60s, refresh wallet/position
        data via REST so the risk manager and balance checks stay current.
        Also marks connections as reconnecting so the health check reflects
        the degraded state.
        """
        if not getattr(self, '_stale_logged', False):
            self.logger.warning(
                "WebSocket stale (60s no data) — refreshing via REST"
            )
            self._stale_logged = True
        else:
            self.logger.debug("WebSocket still stale — refreshing via REST")

        # Refresh wallet/positions via REST to keep data current
        try:
            self._fetch_initial_wallet()
        except Exception as e:
            self.logger.warning(f"REST wallet refresh failed: {e}")

        try:
            self._fetch_initial_positions()
        except Exception as e:
            self.logger.warning(f"REST position refresh failed: {e}")

        # Update connection status
        if self._public_connected:
            self.state.set_public_ws_reconnecting()
            self._public_connected = False

        if self._private_connected:
            self.state.set_private_ws_reconnecting()
            self._private_connected = False

        # Track last disconnect for agents
        self._last_disconnect_time = time.time()
        self._disconnect_count = getattr(self, '_disconnect_count', 0) + 1
    
    def get_health(self) -> dict[str, object]:
        """
        Get connection health status.
        
        Returns:
            Dict with health status information suitable for agents.
        """
        stats = self.state.get_stats()
        update_counts = stats.get('update_counts', {})
        
        # Check if we've received any data
        has_data = sum(update_counts.values()) > 0
        
        # Get connection status
        pub_status = self.state.get_public_ws_status()
        priv_status = self.state.get_private_ws_status()
        
        # Determine if using fallback
        using_rest_fallback = not (self._public_connected or self._private_connected)
        
        return {
            "healthy": has_data or using_rest_fallback,  # Healthy if has data OR using REST fallback
            "websocket_connected": self._public_connected or self._private_connected,
            "using_rest_fallback": using_rest_fallback,
            "public_connected": self._public_connected,
            "private_connected": self._private_connected,
            "public_uptime": pub_status.uptime_seconds if pub_status else 0,
            "private_uptime": priv_status.uptime_seconds if priv_status else 0,
            "disconnect_count": getattr(self, '_disconnect_count', 0),
            "last_disconnect_time": getattr(self, '_last_disconnect_time', None),
            "total_updates": sum(update_counts.values()),
            "update_counts": update_counts,
            "last_error": pub_status.last_error if pub_status else (priv_status.last_error if priv_status else None),
        }
    
    def is_healthy_for_trading(self) -> bool:
        """
        Quick check if system is healthy enough for trading.
        
        For agents/bots: call this before placing orders.
        Returns True if either WebSocket or REST fallback is working.
        """
        health = self.get_health()
        return bool(health["healthy"])
    
    # ==========================================================================
    # Status and Introspection
    # ==========================================================================
    
    def get_status(self) -> dict[str, object]:
        """Get current bootstrap status."""
        # Determine API modes using standardized DEMO/LIVE terminology
        if self.app_config.bybit.is_demo:
            rest_api_mode = "DEMO (FAKE MONEY)"
        else:
            rest_api_mode = "LIVE (REAL MONEY)"
        
        if self.sub_config.use_live_for_public_streams:
            public_ws_mode = "LIVE (shared market data)"
        elif self.app_config.bybit.is_demo:
            public_ws_mode = "DEMO"
        else:
            public_ws_mode = "LIVE"
        
        private_ws_mode = rest_api_mode  # Private WS must match REST API
        
        return {
            "running": self._running,
            "symbols": list(self._symbols),
            "public_connected": self._public_connected,
            "private_connected": self._private_connected,
            "api_modes": {
                "rest_api": rest_api_mode,
                "public_websocket": public_ws_mode,
                "private_websocket": private_ws_mode,
            },
            "subscription_config": {
                "ticker": self.sub_config.enable_ticker,
                "orderbook": self.sub_config.enable_orderbook,
                "trades": self.sub_config.enable_trades,
                "klines": self.sub_config.enable_klines,
                "kline_intervals": self.sub_config.kline_intervals,
                "positions": self.sub_config.enable_positions,
                "orders": self.sub_config.enable_orders,
                "executions": self.sub_config.enable_executions,
                "wallet": self.sub_config.enable_wallet,
                "use_live_for_public_streams": self.sub_config.use_live_for_public_streams,
            },
            "state_summary": self.state.get_summary(),
        }
    
    @property
    def is_running(self) -> bool:
        """Check if bootstrap is running."""
        return self._running
    
    @property
    def is_connected(self) -> bool:
        """Check if at least one stream is connected."""
        return self._public_connected or self._private_connected


# ==============================================================================
# Singleton Instance
# ==============================================================================

_realtime_bootstrap: RealtimeBootstrap | None = None
_bootstrap_lock = threading.Lock()


def get_realtime_bootstrap() -> RealtimeBootstrap:
    """
    Get or create the global RealtimeBootstrap instance.
    
    Creates a SubscriptionConfig based on the app's WebSocketConfig settings.
    """
    global _realtime_bootstrap
    with _bootstrap_lock:
        if _realtime_bootstrap is None:
            # Create subscription config from app config
            app_config = get_config()
            ws_config = app_config.websocket
            
            # In demo mode, auto-enable live public streams because
            # stream-demo.bybit.com/v5/public/linear returns 404.
            # Market data is identical on live vs demo.
            use_live_public = ws_config.use_live_for_public_streams
            if app_config.bybit.use_demo and not use_live_public:
                use_live_public = True

            sub_config = SubscriptionConfig(
                enable_ticker=ws_config.enable_ticker_stream,
                enable_orderbook=ws_config.enable_orderbook_stream,
                enable_trades=ws_config.enable_trades_stream,
                enable_klines=ws_config.enable_klines_stream,
                kline_intervals=ws_config.kline_intervals,
                enable_positions=ws_config.enable_position_stream,
                enable_orders=ws_config.enable_order_stream,
                enable_executions=ws_config.enable_execution_stream,
                enable_wallet=ws_config.enable_wallet_stream,
                use_live_for_public_streams=use_live_public,
            )
            
            _realtime_bootstrap = RealtimeBootstrap(config=sub_config)
        return _realtime_bootstrap


def reset_realtime_bootstrap():
    """Reset the global RealtimeBootstrap instance (for testing)."""
    global _realtime_bootstrap
    with _bootstrap_lock:
        if _realtime_bootstrap and _realtime_bootstrap.is_running:
            _realtime_bootstrap.stop()
        _realtime_bootstrap = None

