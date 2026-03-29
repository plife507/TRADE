"""
SharedFeedHub — one WebSocket connection per symbol, fan-out to N engines.

Bybit limits concurrent WS connections per IP. Running 50 plays on BTCUSDT
with separate connections = 50 connections. The feed hub maintains one
connection per symbol and fans out candle/ticker events to all registered
ShadowEngines.

Thread safety: RealtimeState uses copy-under-lock for callbacks (G6.2.1).
The hub registers a single callback per symbol, then iterates engines in
that callback. Engine.on_candle/on_ticker are designed for zero allocations.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from ..data.realtime_bootstrap import RealtimeBootstrap
from ..data.realtime_state import RealtimeState
from ..utils.logger import get_module_logger

if TYPE_CHECKING:
    from ..data.realtime_models import KlineData, TickerData
    from .engine import ShadowEngine

logger = get_module_logger(__name__)


class SharedFeedHub:
    """Manages shared WebSocket connections per symbol.

    One RealtimeBootstrap + RealtimeState per symbol. Multiple engines
    register as listeners on the same feed.
    """

    __slots__ = ("_feeds", "_states", "_listeners", "_subscribed_intervals")

    def __init__(self) -> None:
        self._feeds: dict[str, RealtimeBootstrap] = {}   # symbol -> WS
        self._states: dict[str, RealtimeState] = {}       # symbol -> state
        self._listeners: dict[str, list[ShadowEngine]] = {}  # symbol -> engines
        self._subscribed_intervals: dict[str, set[str]] = {}  # symbol -> bybit intervals

    def ensure_feed(self, symbol: str) -> RealtimeState:
        """Create WS connection for symbol if not exists.

        Returns the RealtimeState for the symbol (for direct queries).
        """
        if symbol in self._feeds:
            return self._states[symbol]

        # Shadow always uses LIVE WS (stream.bybit.com) for real market data.
        # Demo WS (stream-demo.bybit.com) returns 404 on public/linear.
        from ..exchanges.bybit_client import BybitClient
        from ..config.config import get_config

        app_config = get_config()
        api_key, api_secret = app_config.bybit.get_credentials()

        # Force live WS regardless of trading mode config
        client = BybitClient(
            api_key=api_key,
            api_secret=api_secret,
            use_demo=False,  # Always live for public market data
        )

        state = RealtimeState()
        bootstrap = RealtimeBootstrap(client=client, state=state, env="live")

        # Start WS with public-only (no private — sim handles orders)
        bootstrap.start(symbols=[symbol], include_private=False)

        self._feeds[symbol] = bootstrap
        self._states[symbol] = state
        self._listeners[symbol] = []
        self._subscribed_intervals[symbol] = set()

        # Register fan-out callbacks
        state.on_kline_update(lambda kline: self._on_kline(symbol, kline))
        state.on_ticker_update(lambda ticker: self._on_ticker(symbol, ticker))

        logger.info("SharedFeedHub: WS started for %s", symbol)
        return state

    def register_engine(self, symbol: str, engine: ShadowEngine) -> None:
        """Register engine to receive candles/tickers for this symbol.

        Also subscribes to kline intervals required by the engine's play
        (if not already subscribed).
        """
        if symbol not in self._listeners:
            raise ValueError(f"No feed for {symbol}. Call ensure_feed() first.")
        self._listeners[symbol].append(engine)

        # Subscribe kline intervals from the engine's play timeframes
        self._ensure_kline_subscriptions(symbol, engine)

        logger.info(
            "SharedFeedHub: registered engine %s on %s (%d listeners)",
            engine.instance_id, symbol, len(self._listeners[symbol]),
        )

    def unregister_engine(self, symbol: str, engine: ShadowEngine) -> None:
        """Remove engine from feed listeners.

        If no more listeners for this symbol, closes the WS connection.
        """
        if symbol not in self._listeners:
            return

        try:
            self._listeners[symbol].remove(engine)
        except ValueError:
            return  # Already unregistered

        logger.info(
            "SharedFeedHub: unregistered engine %s from %s (%d remaining)",
            engine.instance_id, symbol, len(self._listeners[symbol]),
        )

        # Close WS if no more listeners
        if not self._listeners[symbol]:
            self._close_feed(symbol)

    def stop(self) -> None:
        """Shut down all WS connections."""
        for symbol in list(self._feeds):
            self._close_feed(symbol)
        logger.info("SharedFeedHub: all feeds stopped")

    @property
    def active_symbols(self) -> list[str]:
        """List of symbols with active WS connections."""
        return list(self._feeds.keys())

    @property
    def total_listeners(self) -> int:
        """Total number of registered engine listeners."""
        return sum(len(engines) for engines in self._listeners.values())

    # ── Internal ───────────────────────────────────────────────

    def _ensure_kline_subscriptions(self, symbol: str, engine: ShadowEngine) -> None:
        """Subscribe to any kline intervals the engine needs that aren't active yet."""
        from ..config.constants import TIMEFRAME_TO_BYBIT

        play = engine._play
        tf_map = play.tf_mapping or {}

        # Collect unique concrete timeframes from the play
        unique_tfs: set[str] = set()
        for role in ("low_tf", "med_tf", "high_tf"):
            tf = tf_map.get(role)
            if tf:
                unique_tfs.add(tf)
        if not unique_tfs and play.exec_tf:
            unique_tfs.add(play.exec_tf)

        # Convert to Bybit interval format, skip already-subscribed
        already = self._subscribed_intervals.get(symbol, set())
        new_intervals: list[str] = []
        for tf in sorted(unique_tfs):
            bybit_iv = TIMEFRAME_TO_BYBIT.get(tf)
            if bybit_iv and bybit_iv not in already:
                new_intervals.append(bybit_iv)

        if not new_intervals:
            return

        bootstrap = self._feeds[symbol]
        bootstrap.subscribe_kline_intervals(symbol, new_intervals)
        already.update(new_intervals)

        logger.info(
            "SharedFeedHub: subscribed kline intervals %s for %s",
            new_intervals, symbol,
        )

    def _on_kline(self, symbol: str, kline: KlineData) -> None:
        """Fan-out kline to all engines for this symbol.

        Called from WS thread via RealtimeState callback. Must be fast.
        Only processes closed candles.
        """
        if not kline.is_closed:
            return

        engines = self._listeners.get(symbol)
        if not engines:
            return

        # Convert KlineData to Bar for engine consumption
        from datetime import datetime, timezone
        from ..backtest.runtime.types import Bar

        tf = kline.interval
        ts_open = datetime.fromtimestamp(kline.start_time / 1000, tz=timezone.utc).replace(tzinfo=None)
        ts_close = datetime.fromtimestamp(kline.end_time / 1000, tz=timezone.utc).replace(tzinfo=None) if kline.end_time else ts_open

        bar = Bar(
            symbol=symbol,
            tf=tf,
            ts_open=ts_open,
            ts_close=ts_close,
            open=kline.open,
            high=kline.high,
            low=kline.low,
            close=kline.close,
            volume=kline.volume,
        )
        for engine in engines:
            engine.on_candle(bar, tf)

    def _on_ticker(self, symbol: str, ticker: TickerData) -> None:
        """Fan-out ticker to all engines for this symbol.

        Updates mark/last/index prices for trigger_by evaluation.
        """
        engines = self._listeners.get(symbol)
        if not engines:
            return

        mark = ticker.mark_price or 0.0
        last = ticker.last_price or 0.0
        index = ticker.index_price or 0.0
        funding = ticker.funding_rate or 0.0

        for engine in engines:
            engine.on_ticker(mark, last, index, funding)

    def _close_feed(self, symbol: str) -> None:
        """Close WS connection for a symbol."""
        if symbol in self._feeds:
            try:
                self._feeds[symbol].stop()
            except Exception as e:
                logger.warning("Error stopping feed for %s: %s", symbol, e)
            del self._feeds[symbol]
            del self._states[symbol]
            del self._listeners[symbol]
            self._subscribed_intervals.pop(symbol, None)
            logger.info("SharedFeedHub: WS closed for %s", symbol)
