"""
Live market data fetching module.

Uses Bybit PUBLIC endpoints only (no rate limit conflict with trading).
Implements aggressive caching to minimize API calls.

Now supports HYBRID mode:
- First attempts to read from RealtimeState (WebSocket-fed cache)
- Falls back to REST API if WebSocket data is unavailable or stale
- Seamlessly transitions between modes

Usage:
    from src.data.market_data import get_market_data
    
    data = get_market_data()
    
    # Get price (uses WebSocket if available, else REST)
    price = data.get_latest_price("BTCUSDT")
    
    # Check data source
    print(data.get_data_source("BTCUSDT"))  # "websocket" or "rest"
"""

import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from threading import Lock

import pandas as pd

from ..exchanges.bybit_client import BybitClient
from ..config.config import get_config
from ..utils.logger import get_logger
from ..utils.helpers import safe_float


class CacheEntry:
    """Simple cache entry with TTL."""
    
    def __init__(self, data: Any, ttl_seconds: float):
        self.data = data
        self.expires_at = time.time() + ttl_seconds
    
    @property
    def is_expired(self) -> bool:
        return time.time() > self.expires_at


class MarketDataCache:
    """Thread-safe cache for market data."""
    
    def __init__(self):
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = Lock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get cached value if not expired."""
        with self._lock:
            entry = self._cache.get(key)
            if entry and not entry.is_expired:
                return entry.data
            return None
    
    def set(self, key: str, data: Any, ttl_seconds: float):
        """Set cache value with TTL."""
        with self._lock:
            self._cache[key] = CacheEntry(data, ttl_seconds)
    
    def clear(self, key: str = None):
        """Clear specific key or entire cache."""
        with self._lock:
            if key:
                self._cache.pop(key, None)
            else:
                self._cache.clear()


class MarketData:
    """
    Live market data provider with hybrid WebSocket/REST support.
    
    Features:
    - Uses only PUBLIC endpoints (no trading rate limit impact)
    - Aggressive caching (configurable TTLs)
    - Thread-safe
    - Returns pandas DataFrames where applicable
    - HYBRID mode: Prefers WebSocket data, falls back to REST
    
    Data Source Priority:
    1. RealtimeState (WebSocket-fed cache) - if available and not stale
    2. REST API with caching - fallback
    """
    
    def __init__(self, prefer_websocket: bool = True):
        """
        Initialize market data provider.
        
        Args:
            prefer_websocket: If True, prefer WebSocket data when available
        """
        self.config = get_config()
        self.logger = get_logger()
        
        # WebSocket preference
        self._prefer_websocket = prefer_websocket
        
        # Lazy import to avoid circular dependency
        self._realtime_state = None
        
        # ALWAYS use LIVE API for market data fetching (for accuracy)
        # Market data must be accurate - DEMO API may return different prices
        data_key, data_secret = self.config.bybit.get_live_data_credentials()
        
        # Error if LIVE data credentials are not configured (STRICT - no fallback)
        if not data_key or not data_secret:
            self.logger.error(
                "MISSING REQUIRED KEY: BYBIT_LIVE_DATA_API_KEY/SECRET not configured! "
                "Market data requires LIVE API access for accurate data. "
                "No fallback to trading keys or generic keys is allowed."
            )
        
        # Initialize client with LIVE API (use_demo=False)
        # This ensures we get real market data regardless of trading mode
        self.client = BybitClient(
            api_key=data_key if data_key else None,
            api_secret=data_secret if data_secret else None,
            use_demo=False,  # ALWAYS use LIVE API for data accuracy
        )
        
        # Log detailed API environment info (STRICT - canonical keys only)
        key_status = "authenticated" if data_key else "NO KEY"
        # Determine key source - STRICT: only canonical key
        if self.config.bybit.live_data_api_key:
            key_source = "BYBIT_LIVE_DATA_API_KEY"
        else:
            key_source = "MISSING (BYBIT_LIVE_DATA_API_KEY required)"
        
        self.logger.info(
            f"MarketData initialized: "
            f"API=LIVE (api.bybit.com), "
            f"auth={key_status}, "
            f"key_source={key_source}, "
            f"prefer_websocket={prefer_websocket}"
        )
        
        # Cache with configurable TTLs (for REST fallback)
        self._cache = MarketDataCache()
        self._price_ttl = self.config.data.price_cache_seconds
        self._ohlcv_ttl = self.config.data.ohlcv_cache_seconds
        self._funding_ttl = self.config.data.funding_cache_seconds
        
        # Staleness thresholds for WebSocket data (seconds)
        self._ws_ticker_staleness = 5.0
        self._ws_kline_staleness = 60.0
        
        # Track data sources for diagnostics
        self._last_source: Dict[str, str] = {}
    
    # ==================== WebSocket State Access ====================
    
    @property
    def realtime_state(self):
        """Get RealtimeState instance (lazy import to avoid circular dependency)."""
        if self._realtime_state is None:
            try:
                from .realtime_state import get_realtime_state
                self._realtime_state = get_realtime_state()
            except ImportError:
                self._realtime_state = None
        return self._realtime_state
    
    def _has_fresh_ws_ticker(self, symbol: str) -> bool:
        """Check if we have fresh WebSocket ticker data."""
        if not self._prefer_websocket or not self.realtime_state:
            return False
        return not self.realtime_state.is_ticker_stale(symbol, self._ws_ticker_staleness)
    
    def _has_fresh_ws_kline(self, symbol: str, interval: str) -> bool:
        """Check if we have fresh WebSocket kline data."""
        if not self._prefer_websocket or not self.realtime_state:
            return False
        return not self.realtime_state.is_kline_stale(symbol, interval, self._ws_kline_staleness)
    
    def get_data_source(self, symbol: str) -> str:
        """Get the data source used for last query of this symbol."""
        return self._last_source.get(symbol, "not queried yet")
    
    def set_prefer_websocket(self, prefer: bool):
        """Enable or disable WebSocket preference."""
        self._prefer_websocket = prefer
        self.logger.info(f"WebSocket preference set to: {prefer}")
    
    # ==================== Price Data ====================
    
    def get_latest_price(self, symbol: str) -> float:
        """
        Get current market price.
        
        Uses WebSocket data if available and fresh, otherwise REST.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Last traded price
        """
        # Try WebSocket first
        if self._has_fresh_ws_ticker(symbol):
            ticker = self.realtime_state.get_ticker(symbol)
            if ticker and ticker.last_price > 0:
                self._last_source[symbol] = "websocket"
                return ticker.last_price
        
        # Fall back to REST with caching
        self._last_source[symbol] = "rest"
        
        cache_key = f"price:{symbol}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        ticker = self.client.get_ticker(symbol)
        price = safe_float(ticker.get("lastPrice"))
        
        self._cache.set(cache_key, price, self._price_ttl)
        return price
    
    def get_bid_ask(self, symbol: str) -> Dict[str, float]:
        """
        Get current bid/ask prices.
        
        Uses WebSocket data if available, otherwise REST.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Dict with 'bid', 'ask', 'spread', 'spread_percent'
        """
        # Try WebSocket first
        if self._has_fresh_ws_ticker(symbol):
            ticker = self.realtime_state.get_ticker(symbol)
            if ticker and ticker.bid_price > 0:
                bid = ticker.bid_price
                ask = ticker.ask_price
                spread = ask - bid
                spread_pct = (spread / bid * 100) if bid > 0 else 0
                
                self._last_source[symbol] = "websocket"
                return {
                    "bid": bid,
                    "ask": ask,
                    "spread": spread,
                    "spread_percent": spread_pct,
                }
        
        # Fall back to REST
        self._last_source[symbol] = "rest"
        
        cache_key = f"bidask:{symbol}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        ticker = self.client.get_ticker(symbol)
        bid = safe_float(ticker.get("bid1Price"))
        ask = safe_float(ticker.get("ask1Price"))
        
        spread = ask - bid
        spread_pct = (spread / bid * 100) if bid > 0 else 0
        
        result = {
            "bid": bid,
            "ask": ask,
            "spread": spread,
            "spread_percent": spread_pct,
        }
        
        self._cache.set(cache_key, result, self._price_ttl)
        return result
    
    def get_ticker(self, symbol: str) -> Dict[str, Any]:
        """
        Get full ticker data.
        
        Uses WebSocket data if available, otherwise REST.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Full ticker dict with price, volume, changes, etc.
        """
        # Try WebSocket first
        if self._has_fresh_ws_ticker(symbol):
            ws_ticker = self.realtime_state.get_ticker(symbol)
            if ws_ticker and ws_ticker.last_price > 0:
                self._last_source[symbol] = "websocket"
                return {
                    "symbol": symbol,
                    "last_price": ws_ticker.last_price,
                    "bid": ws_ticker.bid_price,
                    "ask": ws_ticker.ask_price,
                    "high_24h": ws_ticker.high_24h,
                    "low_24h": ws_ticker.low_24h,
                    "volume_24h": ws_ticker.volume_24h,
                    "turnover_24h": ws_ticker.turnover_24h,
                    "price_change_24h": ws_ticker.price_change_24h,
                    "mark_price": ws_ticker.mark_price,
                    "funding_rate": ws_ticker.funding_rate,
                    "_source": "websocket",
                    "_timestamp": ws_ticker.timestamp,
                }
        
        # Fall back to REST
        self._last_source[symbol] = "rest"
        
        cache_key = f"ticker:{symbol}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        ticker = self.client.get_ticker(symbol)
        
        result = {
            "symbol": symbol,
            "last_price": safe_float(ticker.get("lastPrice")),
            "bid": safe_float(ticker.get("bid1Price")),
            "ask": safe_float(ticker.get("ask1Price")),
            "high_24h": safe_float(ticker.get("highPrice24h")),
            "low_24h": safe_float(ticker.get("lowPrice24h")),
            "volume_24h": safe_float(ticker.get("volume24h")),
            "turnover_24h": safe_float(ticker.get("turnover24h")),
            "price_change_24h": safe_float(ticker.get("price24hPcnt")) * 100,
            "_source": "rest",
            "_timestamp": time.time(),
        }
        
        self._cache.set(cache_key, result, self._price_ttl)
        return result
    
    # ==================== OHLCV Data ====================
    
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str = "15",
        bars: int = 200,
    ) -> pd.DataFrame:
        """
        Get OHLCV candlestick data.
        
        Note: OHLCV data always comes from REST API since WebSocket
        provides only the current candle, not historical data.
        However, we can use WebSocket for the current (forming) candle.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle interval (1, 5, 15, 60, 240, D, etc.)
            bars: Number of candles to fetch (max 1000)
        
        Returns:
            DataFrame with timestamp, open, high, low, close, volume
        """
        # OHLCV historical data always from REST
        self._last_source[symbol] = "rest"
        
        cache_key = f"ohlcv:{symbol}:{timeframe}:{bars}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return self._update_current_candle_from_ws(cached.copy(), symbol, timeframe)
        
        df = self.client.get_klines(symbol, interval=timeframe, limit=bars)
        
        self._cache.set(cache_key, df, self._ohlcv_ttl)
        
        # Try to update current candle from WebSocket
        return self._update_current_candle_from_ws(df.copy(), symbol, timeframe)
    
    def _update_current_candle_from_ws(
        self,
        df: pd.DataFrame,
        symbol: str,
        interval: str
    ) -> pd.DataFrame:
        """
        Update the most recent candle in DataFrame with WebSocket data if available.
        
        This provides more up-to-date OHLCV data for the current forming candle.
        """
        if df.empty or not self._prefer_websocket or not self.realtime_state:
            return df
        
        # Try to get WebSocket kline
        ws_kline = self.realtime_state.get_kline(symbol, interval)
        if not ws_kline:
            return df
        
        # Check if the WebSocket kline matches the last candle in the DataFrame
        # by comparing start times
        if len(df) > 0:
            last_row_time = df.iloc[-1]["timestamp"]
            
            # Convert WebSocket start_time (ms) to pandas timestamp
            ws_start = pd.Timestamp(ws_kline.start_time, unit="ms", tz="UTC")
            
            # If times match, update the row
            if hasattr(last_row_time, 'timestamp'):
                # last_row_time is already a Timestamp
                if abs((last_row_time - ws_start).total_seconds()) < 60:
                    df.iloc[-1, df.columns.get_loc("high")] = max(
                        df.iloc[-1]["high"], ws_kline.high
                    )
                    df.iloc[-1, df.columns.get_loc("low")] = min(
                        df.iloc[-1]["low"], ws_kline.low
                    )
                    df.iloc[-1, df.columns.get_loc("close")] = ws_kline.close
                    df.iloc[-1, df.columns.get_loc("volume")] = ws_kline.volume
        
        return df
    
    def get_latest_candle(self, symbol: str, timeframe: str = "15") -> Dict[str, Any]:
        """
        Get the most recent completed candle.
        
        Uses WebSocket for the current candle if available.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle interval
        
        Returns:
            Dict with candle data
        """
        # Check WebSocket for current kline
        if self._has_fresh_ws_kline(symbol, timeframe):
            ws_kline = self.realtime_state.get_kline(symbol, timeframe)
            if ws_kline and ws_kline.is_closed:
                self._last_source[symbol] = "websocket"
                return {
                    "timestamp": pd.Timestamp(ws_kline.start_time, unit="ms", tz="UTC"),
                    "open": ws_kline.open,
                    "high": ws_kline.high,
                    "low": ws_kline.low,
                    "close": ws_kline.close,
                    "volume": ws_kline.volume,
                }
        
        # Fall back to REST
        self._last_source[symbol] = "rest"
        
        df = self.get_ohlcv(symbol, timeframe, bars=2)
        
        if df.empty or len(df) < 2:
            return {}
        
        # Return second-to-last (most recently completed)
        row = df.iloc[-2]
        return {
            "timestamp": row["timestamp"],
            "open": row["open"],
            "high": row["high"],
            "low": row["low"],
            "close": row["close"],
            "volume": row["volume"],
        }
    
    # ==================== Funding & OI ====================
    
    def get_funding_rate(self, symbol: str) -> Dict[str, Any]:
        """
        Get current funding rate.
        
        Uses WebSocket ticker data if available (contains funding info),
        otherwise REST.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Dict with funding rate info
        """
        # Check WebSocket ticker for funding rate
        if self._has_fresh_ws_ticker(symbol):
            ws_ticker = self.realtime_state.get_ticker(symbol)
            if ws_ticker and ws_ticker.funding_rate != 0:
                self._last_source[symbol] = "websocket"
                return {
                    "symbol": symbol,
                    "rate": ws_ticker.funding_rate,
                    "rate_percent": ws_ticker.funding_rate * 100,
                    "next_funding_time": ws_ticker.next_funding_time,
                    "_source": "websocket",
                }
        
        # Fall back to REST
        self._last_source[symbol] = "rest"
        
        cache_key = f"funding:{symbol}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        data = self.client.get_funding_rate(symbol, limit=1)
        
        if not data:
            return {"symbol": symbol, "rate": 0, "next_time": None}
        
        entry = data[0]
        result = {
            "symbol": symbol,
            "rate": safe_float(entry.get("fundingRate")),
            "rate_percent": safe_float(entry.get("fundingRate")) * 100,
            "timestamp": int(entry.get("fundingRateTimestamp", 0)),
            "_source": "rest",
        }
        
        self._cache.set(cache_key, result, self._funding_ttl)
        return result
    
    def get_open_interest(self, symbol: str) -> Dict[str, Any]:
        """
        Get open interest data.
        
        Uses WebSocket ticker data if available (contains OI),
        otherwise REST.
        
        Args:
            symbol: Trading symbol
        
        Returns:
            Dict with OI data
        """
        # Check WebSocket ticker for open interest
        if self._has_fresh_ws_ticker(symbol):
            ws_ticker = self.realtime_state.get_ticker(symbol)
            if ws_ticker and ws_ticker.open_interest > 0:
                self._last_source[symbol] = "websocket"
                return {
                    "symbol": symbol,
                    "open_interest": ws_ticker.open_interest,
                    "_source": "websocket",
                }
        
        # Fall back to REST
        self._last_source[symbol] = "rest"
        
        cache_key = f"oi:{symbol}"
        cached = self._cache.get(cache_key)
        if cached is not None:
            return cached
        
        data = self.client.get_open_interest(symbol, limit=1)
        
        if not data:
            return {"symbol": symbol, "oi": 0, "oi_value": 0}
        
        entry = data[0]
        result = {
            "symbol": symbol,
            "open_interest": safe_float(entry.get("openInterest")),
            "timestamp": int(entry.get("timestamp", 0)),
            "_source": "rest",
        }
        
        self._cache.set(cache_key, result, 60)  # 1 minute cache
        return result
    
    # ==================== Market Snapshot ====================
    
    def get_market_snapshot(self, symbols: List[str] = None) -> Dict[str, Dict]:
        """
        Get comprehensive market snapshot for multiple symbols.
        
        Uses WebSocket data where available for low latency.
        
        Args:
            symbols: List of symbols (None = use config defaults)
        
        Returns:
            Dict mapping symbol to market data
        """
        if symbols is None:
            symbols = self.config.trading.default_symbols
        
        snapshot = {}
        
        for symbol in symbols:
            try:
                ticker = self.get_ticker(symbol)
                funding = self.get_funding_rate(symbol)
                
                snapshot[symbol] = {
                    **ticker,
                    "funding_rate": funding.get("rate", 0),
                    "funding_rate_percent": funding.get("rate_percent", 0),
                }
            except Exception as e:
                self.logger.warning(f"Failed to get data for {symbol}: {e}")
                snapshot[symbol] = {"symbol": symbol, "error": str(e)}
        
        return snapshot
    
    # ==================== Multi-Timeframe Data ====================
    
    def get_multi_tf_ohlcv(
        self,
        symbol: str,
        htf: str = "4h",
        mtf: str = "1h",
        ltf: str = "15m",
        bars: int = 100,
    ) -> Dict[str, pd.DataFrame]:
        """
        Get OHLCV data for multiple timeframes at once.
        
        This is optimized for multi-timeframe strategies that need
        HTF (Higher), MTF (Medium), and LTF (Lower) timeframe data.
        
        Args:
            symbol: Trading symbol
            htf: Higher timeframe (default: 4h)
            mtf: Medium timeframe (default: 1h)
            ltf: Lower timeframe (default: 15m)
            bars: Number of bars per timeframe
        
        Returns:
            Dict with keys 'htf', 'mtf', 'ltf' mapping to DataFrames
        """
        return {
            "htf": self.get_ohlcv(symbol, htf, bars),
            "mtf": self.get_ohlcv(symbol, mtf, bars),
            "ltf": self.get_ohlcv(symbol, ltf, bars),
        }
    
    def get_multiple_timeframes(
        self,
        symbol: str,
        timeframes: List[str],
        bars: int = 100,
    ) -> Dict[str, pd.DataFrame]:
        """
        Get OHLCV data for arbitrary list of timeframes.
        
        Args:
            symbol: Trading symbol
            timeframes: List of timeframe strings (e.g., ["1d", "4h", "1h", "15m"])
            bars: Number of bars per timeframe
        
        Returns:
            Dict mapping timeframe string to DataFrame
        """
        result = {}
        for tf in timeframes:
            try:
                result[tf] = self.get_ohlcv(symbol, tf, bars)
            except Exception as e:
                self.logger.warning(f"Failed to get {tf} data for {symbol}: {e}")
                result[tf] = pd.DataFrame()
        return result
    
    # ==================== Cache Management ====================
    
    def clear_cache(self, symbol: str = None):
        """
        Clear cached data.
        
        Args:
            symbol: Specific symbol to clear (None = clear all)
        """
        if symbol:
            # Clear all cache keys for this symbol
            for prefix in ["price:", "bidask:", "ticker:", "ohlcv:", "funding:", "oi:"]:
                self._cache.clear(f"{prefix}{symbol}")
        else:
            self._cache.clear()
    
    # ==================== Diagnostics ====================
    
    def get_source_stats(self) -> Dict[str, Any]:
        """Get statistics on data sources used."""
        ws_count = sum(1 for s in self._last_source.values() if s == "websocket")
        rest_count = sum(1 for s in self._last_source.values() if s == "rest")
        
        return {
            "websocket_preference": self._prefer_websocket,
            "websocket_queries": ws_count,
            "rest_queries": rest_count,
            "last_sources": dict(self._last_source),
        }
    
    def get_realtime_status(self) -> Dict[str, Any]:
        """Get status of realtime data connection."""
        if not self.realtime_state:
            return {"available": False, "error": "RealtimeState not available"}
        
        return {
            "available": True,
            "public_ws_connected": self.realtime_state.is_public_ws_connected,
            "private_ws_connected": self.realtime_state.is_private_ws_connected,
            "ticker_count": len(self.realtime_state.get_all_tickers()),
            "stats": self.realtime_state.get_stats(),
        }


# Singleton instance
_market_data: Optional[MarketData] = None


def get_market_data() -> MarketData:
    """Get or create the global MarketData instance."""
    global _market_data
    if _market_data is None:
        _market_data = MarketData()
    return _market_data


def reset_market_data():
    """Reset the global MarketData instance (for testing)."""
    global _market_data
    _market_data = None
