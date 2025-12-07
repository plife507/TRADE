"""
Historical Data Store - DuckDB-backed market data storage.

Provides:
- Efficient columnar storage for OHLCV data
- Auto-sync with gap detection and filling
- Period-based data retrieval (1Y, 6M, 1W, 1D, etc.)
- DataFrame output for backtesting
"""

import duckdb
import pandas as pd
import time
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Union, Tuple, Callable, Any
from dataclasses import dataclass

from ..exchanges.bybit_client import BybitClient
from ..config.config import get_config
from ..utils.logger import get_logger


# Activity emojis for visual feedback
class ActivityEmoji:
    """Fun emojis for different activities."""
    # Data operations
    SYNC = "📡"
    DOWNLOAD = "⬇️"
    UPLOAD = "⬆️"
    CANDLE = "🕯️"
    CHART = "📊"
    DATABASE = "🗄️"
    
    # Money/Trading
    MONEY_BAG = "💰"
    DOLLAR = "💵"
    ROCKET = "🚀"
    STONKS = "📈"
    
    # Status
    LOADING = "⏳"
    SUCCESS = "✅"
    ERROR = "❌"
    WARNING = "⚠️"
    SEARCH = "🔍"
    REPAIR = "🔧"
    TRASH = "🗑️"
    SPARKLE = "✨"
    FIRE = "🔥"
    
    # Progress spinners
    SPINNERS = ["◐", "◓", "◑", "◒"]
    BARS = ["▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    DOTS = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


class ActivitySpinner:
    """
    Animated spinner for long-running operations.
    Shows user that something is happening!
    """
    
    def __init__(self, message: str = "Working", emoji: str = "💰"):
        self.message = message
        self.emoji = emoji
        self.running = False
        self.thread = None
        self.frame = 0
    
    def _spin(self):
        """Spinner animation loop."""
        spinners = ActivityEmoji.DOTS
        while self.running:
            frame = spinners[self.frame % len(spinners)]
            sys.stdout.write(f"\r  {self.emoji} {frame} {self.message}...   ")
            sys.stdout.flush()
            self.frame += 1
            time.sleep(0.1)
    
    def start(self):
        """Start the spinner."""
        self.running = True
        self.thread = threading.Thread(target=self._spin, daemon=True)
        self.thread.start()
    
    def stop(self, final_message: str = None, success: bool = True):
        """Stop the spinner and show final message."""
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        
        emoji = ActivityEmoji.SUCCESS if success else ActivityEmoji.ERROR
        msg = final_message or self.message
        sys.stdout.write(f"\r  {emoji} {msg}                    \n")
        sys.stdout.flush()
    
    def update(self, message: str):
        """Update the spinner message."""
        self.message = message


def print_activity(message: str, emoji: str = "💰", end: str = "\n"):
    """Print a message with activity emoji."""
    print(f"  {emoji} {message}", end=end, flush=True)


# Supported timeframes (Bybit format)
TIMEFRAMES = {
    "1m": "1",
    "5m": "5",
    "15m": "15",
    "1h": "60",
    "4h": "240",
    "1d": "D",
}

# Timeframe to minutes mapping (for edge candle calculations)
TIMEFRAME_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}

# Period parsing
PERIOD_MULTIPLIERS = {
    "Y": 365,      # Years
    "M": 30,       # Months
    "W": 7,        # Weeks
    "D": 1,        # Days
    "H": 1/24,     # Hours
}


@dataclass
class SyncStatus:
    """Status of a symbol/timeframe sync."""
    symbol: str
    timeframe: str
    first_timestamp: Optional[datetime]
    last_timestamp: Optional[datetime]
    candle_count: int
    gaps: List[Tuple[datetime, datetime]]
    is_current: bool


class HistoricalDataStore:
    """
    DuckDB-backed historical market data storage.
    
    Usage:
        store = HistoricalDataStore()
        
        # Sync data
        store.sync("BTCUSDT", period="3M")  # 3 months, all timeframes
        store.sync(["BTCUSDT", "ETHUSDT"], period="1M", timeframes=["15m", "1h", "4h"])
        
        # Query data
        df = store.get_ohlcv("BTCUSDT", "15m", period="1M")
        
        # Check status
        status = store.status("BTCUSDT")
    """
    
    DEFAULT_DB_PATH = "data/market_data.duckdb"
    
    def __init__(self, db_path: str = None):
        """Initialize the data store."""
        self.db_path = Path(db_path or self.DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        self.conn = duckdb.connect(str(self.db_path))
        self.config = get_config()
        self.logger = get_logger()
        
        # ALWAYS use LIVE API for historical data fetching (for accuracy)
        # Historical data must be accurate - DEMO API may return different data
        api_key, api_secret = self.config.bybit.get_live_data_credentials()
        
        # Error if LIVE data credentials are not configured (STRICT - no fallback)
        if not api_key or not api_secret:
            self.logger.error(
                "MISSING REQUIRED KEY: BYBIT_LIVE_DATA_API_KEY/SECRET not configured! "
                "Historical data sync requires LIVE API access for accurate data. "
                "No fallback to trading keys or generic keys is allowed."
            )
        
        # Initialize client with LIVE API (use_demo=False)
        # This ensures we get real market data regardless of trading mode
        self.client = BybitClient(
            api_key=api_key if api_key else None,
            api_secret=api_secret if api_secret else None,
            use_demo=False,  # ALWAYS use LIVE API for data accuracy
        )
        
        # Log detailed API environment info (STRICT - canonical keys only)
        key_status = "authenticated" if api_key else "NO KEY"
        # Determine key source - STRICT: only canonical key
        if self.config.bybit.live_data_api_key:
            key_source = "BYBIT_LIVE_DATA_API_KEY"
        else:
            key_source = "MISSING (BYBIT_LIVE_DATA_API_KEY required)"
        
        self.logger.info(
            f"HistoricalDataStore initialized: "
            f"API=LIVE (api.bybit.com), "
            f"auth={key_status}, "
            f"key_source={key_source}"
        )
        
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema."""
        # OHLCV candle data
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS ohlcv (
                symbol VARCHAR NOT NULL,
                timeframe VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                PRIMARY KEY (symbol, timeframe, timestamp)
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS sync_metadata (
                symbol VARCHAR NOT NULL,
                timeframe VARCHAR NOT NULL,
                first_timestamp TIMESTAMP,
                last_timestamp TIMESTAMP,
                candle_count INTEGER,
                last_sync TIMESTAMP,
                PRIMARY KEY (symbol, timeframe)
            )
        """)
        
        # Funding rates data
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS funding_rates (
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                funding_rate DOUBLE,
                funding_rate_interval_hours INTEGER DEFAULT 8,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS funding_metadata (
                symbol VARCHAR NOT NULL,
                first_timestamp TIMESTAMP,
                last_timestamp TIMESTAMP,
                record_count INTEGER,
                last_sync TIMESTAMP,
                PRIMARY KEY (symbol)
            )
        """)
        
        # Open interest data
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS open_interest (
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open_interest DOUBLE,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
        
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS open_interest_metadata (
                symbol VARCHAR NOT NULL,
                first_timestamp TIMESTAMP,
                last_timestamp TIMESTAMP,
                record_count INTEGER,
                last_sync TIMESTAMP,
                PRIMARY KEY (symbol)
            )
        """)
        
        # Create indexes for faster queries
        try:
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_tf 
                ON ohlcv(symbol, timeframe)
            """)
        except Exception:
            pass  # Index may already exist
        
        try:
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_ohlcv_timestamp 
                ON ohlcv(timestamp)
            """)
        except Exception:
            pass  # Index may already exist
        
        try:
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_funding_symbol 
                ON funding_rates(symbol)
            """)
        except Exception:
            pass
        
        try:
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_funding_timestamp 
                ON funding_rates(timestamp)
            """)
        except Exception:
            pass
        
        try:
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_oi_symbol 
                ON open_interest(symbol)
            """)
        except Exception:
            pass
        
        try:
            self.conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_oi_timestamp 
                ON open_interest(timestamp)
            """)
        except Exception:
            pass
    
    # ==================== PERIOD PARSING ====================
    
    @staticmethod
    def parse_period(period: str) -> timedelta:
        """
        Parse period string to timedelta.
        
        Args:
            period: Period string like "1Y", "6M", "2W", "3D", "12H"
        
        Returns:
            timedelta representing the period
        """
        if not period:
            raise ValueError("Period cannot be empty")
        
        # Extract numeric value and unit
        value = int(period[:-1])
        unit = period[-1].upper()
        
        if unit not in PERIOD_MULTIPLIERS:
            raise ValueError(f"Invalid period unit: {unit}. Use Y, M, W, D, or H")
        
        days = value * PERIOD_MULTIPLIERS[unit]
        return timedelta(days=days)
    
    @staticmethod
    def period_to_bars(period: str, timeframe: str) -> int:
        """Calculate approximate number of bars for a period and timeframe."""
        delta = HistoricalDataStore.parse_period(period)
        total_minutes = delta.total_seconds() / 60
        
        tf_minutes = {
            "1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440
        }
        
        interval = tf_minutes.get(timeframe, 15)
        return int(total_minutes / interval)
    
    # ==================== SYNC METHODS ====================
    
    def sync(
        self,
        symbols: Union[str, List[str]],
        period: str = "1M",
        timeframes: List[str] = None,
        progress_callback: Callable = None,
        show_spinner: bool = True,
    ) -> Dict[str, int]:
        """
        Sync historical data for symbols.
        
        Auto-detects existing data and only fetches what's missing.
        
        Args:
            symbols: Single symbol or list of symbols
            period: How far back to sync ("1Y", "6M", "3M", "1M", "2W", "1W", "3D", "1D", "12H")
            timeframes: List of timeframes or None for all
            progress_callback: Optional callback(symbol, timeframe, status)
            show_spinner: Show animated spinner during sync
        
        Returns:
            Dict mapping "symbol_timeframe" to number of candles synced
        """
        if isinstance(symbols, str):
            symbols = [symbols]
        
        # Normalize symbols to uppercase for consistency
        symbols = [s.upper() for s in symbols]
        
        timeframes = timeframes or list(TIMEFRAMES.keys())
        target_start = datetime.now() - self.parse_period(period)
        
        results = {}
        total_synced = 0
        
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol}_{tf}"
                
                if progress_callback:
                    progress_callback(symbol, tf, f"{ActivityEmoji.SYNC} starting")
                
                # Show spinner for individual sync
                spinner = None
                if show_spinner and not progress_callback:
                    spinner = ActivitySpinner(f"Fetching {symbol} {tf}", ActivityEmoji.CANDLE)
                    spinner.start()
                
                try:
                    count = self._sync_symbol_timeframe(
                        symbol, tf, target_start, datetime.now()
                    )
                    results[key] = count
                    total_synced += max(0, count)
                    
                    if spinner:
                        spinner.stop(f"{symbol} {tf}: {count} candles {ActivityEmoji.SPARKLE}")
                    elif progress_callback:
                        emoji = ActivityEmoji.SUCCESS if count > 0 else ActivityEmoji.CHART
                        progress_callback(symbol, tf, f"{emoji} done ({count:,} candles)")
                        
                except Exception as e:
                    self.logger.error(f"Failed to sync {key}: {e}")
                    results[key] = -1
                    
                    if spinner:
                        spinner.stop(f"{symbol} {tf}: error", success=False)
                    elif progress_callback:
                        progress_callback(symbol, tf, f"{ActivityEmoji.ERROR} error: {e}")
        
        return results
    
    def sync_range(
        self,
        symbols: Union[str, List[str]],
        start: datetime,
        end: datetime,
        timeframes: List[str] = None,
    ) -> Dict[str, int]:
        """Sync a specific date range."""
        if isinstance(symbols, str):
            symbols = [symbols]
        
        # Normalize symbols to uppercase for consistency
        symbols = [s.upper() for s in symbols]
        
        timeframes = timeframes or list(TIMEFRAMES.keys())
        results = {}
        
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol}_{tf}"
                try:
                    count = self._sync_symbol_timeframe(symbol, tf, start, end)
                    results[key] = count
                except Exception as e:
                    self.logger.error(f"Failed to sync {key}: {e}")
                    results[key] = -1
        
        return results
    
    def sync_forward(
        self,
        symbols: Union[str, List[str]],
        timeframes: List[str] = None,
        progress_callback: Callable = None,
        show_spinner: bool = True,
    ) -> Dict[str, int]:
        """
        Sync data forward from the last stored candle to now (no backfill).
        
        This is a lightweight sync that only fetches new data after the last
        stored timestamp, without scanning or backfilling older history.
        
        Args:
            symbols: Single symbol or list of symbols
            timeframes: List of timeframes or None for all
            progress_callback: Optional callback(symbol, timeframe, status)
            show_spinner: Show animated spinner during sync
        
        Returns:
            Dict mapping "symbol_timeframe" to number of candles synced
        """
        if isinstance(symbols, str):
            symbols = [symbols]
        
        # Normalize symbols to uppercase for consistency
        symbols = [s.upper() for s in symbols]
        
        timeframes = timeframes or list(TIMEFRAMES.keys())
        results = {}
        total_synced = 0
        
        for symbol in symbols:
            for tf in timeframes:
                key = f"{symbol}_{tf}"
                
                if progress_callback:
                    progress_callback(symbol, tf, f"{ActivityEmoji.SYNC} syncing forward")
                
                # Show spinner for individual sync
                spinner = None
                if show_spinner and not progress_callback:
                    spinner = ActivitySpinner(f"Syncing {symbol} {tf} forward", ActivityEmoji.CANDLE)
                    spinner.start()
                
                try:
                    count = self._sync_forward_symbol_timeframe(symbol, tf)
                    results[key] = count
                    total_synced += max(0, count)
                    
                    if spinner:
                        if count > 0:
                            spinner.stop(f"{symbol} {tf}: +{count} candles {ActivityEmoji.SPARKLE}")
                        else:
                            spinner.stop(f"{symbol} {tf}: already current {ActivityEmoji.SUCCESS}")
                    elif progress_callback:
                        emoji = ActivityEmoji.SUCCESS if count >= 0 else ActivityEmoji.ERROR
                        progress_callback(symbol, tf, f"{emoji} done (+{count} candles)")
                        
                except Exception as e:
                    self.logger.error(f"Failed to sync forward {key}: {e}")
                    results[key] = -1
                    
                    if spinner:
                        spinner.stop(f"{symbol} {tf}: error", success=False)
                    elif progress_callback:
                        progress_callback(symbol, tf, f"{ActivityEmoji.ERROR} error: {e}")
        
        return results
    
    def _sync_forward_symbol_timeframe(
        self,
        symbol: str,
        timeframe: str,
    ) -> int:
        """Sync a single symbol/timeframe forward from last timestamp to now."""
        # Normalize symbol to uppercase for consistency
        symbol = symbol.upper()
        bybit_tf = TIMEFRAMES.get(timeframe, timeframe)
        tf_minutes = TIMEFRAME_MINUTES.get(timeframe, 15)
        
        # Check what we already have
        existing = self.conn.execute("""
            SELECT MAX(timestamp) as last_ts
            FROM ohlcv
            WHERE symbol = ? AND timeframe = ?
        """, [symbol, timeframe]).fetchone()
        
        last_ts = existing[0] if existing and existing[0] else None
        
        if last_ts is None:
            # No data at all - nothing to sync forward from
            # User should use regular sync or build_symbol_history first
            return 0
        
        # Start from one interval after last_ts to avoid overlap
        start = last_ts + timedelta(minutes=tf_minutes)
        end = datetime.now()
        
        # If we're already current (less than one interval behind), skip
        if start >= end:
            return 0
        
        # Fetch new data
        df = self._fetch_from_api(symbol, bybit_tf, start, end)
        
        if not df.empty:
            self._store_dataframe(symbol, timeframe, df)
            self._update_metadata(symbol, timeframe)
            return len(df)
        
        return 0
    
    def _sync_symbol_timeframe(
        self,
        symbol: str,
        timeframe: str,
        target_start: datetime,
        target_end: datetime,
    ) -> int:
        """Sync a single symbol/timeframe combination."""
        # Normalize symbol to uppercase for consistency
        symbol = symbol.upper()
        bybit_tf = TIMEFRAMES.get(timeframe, timeframe)
        tf_minutes = TIMEFRAME_MINUTES.get(timeframe, 15)
        
        # Check what we already have
        existing = self.conn.execute("""
            SELECT MIN(timestamp) as first_ts, MAX(timestamp) as last_ts
            FROM ohlcv
            WHERE symbol = ? AND timeframe = ?
        """, [symbol, timeframe]).fetchone()
        
        first_ts, last_ts = existing
        total_synced = 0
        
        # Determine what ranges to fetch
        ranges_to_fetch = []
        
        if first_ts is None:
            # No data at all - fetch entire range
            ranges_to_fetch.append((target_start, target_end))
        else:
            # Fetch older data if needed (up to but not including first_ts to avoid overlap)
            if target_start < first_ts:
                # End at one interval before first_ts to avoid re-fetching that candle
                older_end = first_ts - timedelta(minutes=tf_minutes)
                if target_start <= older_end:
                    ranges_to_fetch.append((target_start, older_end))
            
            # Fetch newer data if needed (start after last_ts to avoid overlap)
            if target_end > last_ts:
                # Start from one interval after last_ts to avoid re-fetching that candle
                newer_start = last_ts + timedelta(minutes=tf_minutes)
                if newer_start <= target_end:
                    ranges_to_fetch.append((newer_start, target_end))
        
        # Fetch each range
        for range_start, range_end in ranges_to_fetch:
            df = self._fetch_from_api(symbol, bybit_tf, range_start, range_end)
            
            if not df.empty:
                self._store_dataframe(symbol, timeframe, df)
                total_synced += len(df)
        
        # Only update metadata if we have data (either new or existing)
        # This prevents invalid symbols from creating empty metadata entries
        has_data = self.conn.execute("""
            SELECT COUNT(*) FROM ohlcv WHERE symbol = ? AND timeframe = ?
        """, [symbol, timeframe]).fetchone()[0] > 0
        
        if has_data:
            self._update_metadata(symbol, timeframe)
        
        return total_synced
    
    def _fetch_from_api(
        self,
        symbol: str,
        bybit_tf: str,
        start: datetime,
        end: datetime,
        show_progress: bool = True,
    ) -> pd.DataFrame:
        """Fetch data from Bybit API with visual progress."""
        all_data = []
        current_end = end
        request_count = 0
        
        # Convert start/end to pandas Timestamps for consistent comparison with UTC-aware API data
        start_ts = pd.Timestamp(start, tz='UTC') if start.tzinfo is None else pd.Timestamp(start)
        end_ts = pd.Timestamp(end, tz='UTC') if end.tzinfo is None else pd.Timestamp(end)
        current_end_ts = end_ts
        
        # Bybit returns max 1000 candles per request
        while current_end_ts > start_ts:
            try:
                # Show inline progress
                if show_progress:
                    dots = ActivityEmoji.DOTS[request_count % len(ActivityEmoji.DOTS)]
                    sys.stdout.write(f"\r    {ActivityEmoji.DOWNLOAD} {dots} Fetching candles... ({request_count * 1000}+)   ")
                    sys.stdout.flush()
                
                df = self.client.get_klines(
                    symbol=symbol,
                    interval=bybit_tf,
                    limit=1000,
                    end=int(current_end_ts.timestamp() * 1000),
                )
                
                if df.empty:
                    break
                
                all_data.append(df)
                request_count += 1
                
                # Move window back
                earliest = df["timestamp"].min()
                if earliest >= current_end_ts:
                    break
                current_end_ts = earliest - timedelta(minutes=1)
                
                # Rate limiting
                time.sleep(0.1)
                
            except Exception as e:
                self.logger.warning(f"API fetch error: {e}")
                break
        
        # Clear progress line
        if show_progress and request_count > 0:
            sys.stdout.write(f"\r    {ActivityEmoji.SUCCESS} Fetched {request_count} batches                    \n")
            sys.stdout.flush()
        
        if not all_data:
            return pd.DataFrame()
        
        combined = pd.concat(all_data, ignore_index=True)
        combined = combined.drop_duplicates(subset=["timestamp"])
        combined = combined[combined["timestamp"] >= start_ts]
        combined = combined[combined["timestamp"] <= end_ts]
        
        return combined.sort_values("timestamp").reset_index(drop=True)
    
    def _store_dataframe(self, symbol: str, timeframe: str, df: pd.DataFrame):
        """Store DataFrame in DuckDB."""
        if df.empty:
            return
        
        # Normalize symbol to uppercase for consistency
        symbol = symbol.upper()
        
        # Add symbol and timeframe columns
        df = df.copy()
        df["symbol"] = symbol
        df["timeframe"] = timeframe
        
        # Remove timezone info from timestamp for DuckDB storage (store as UTC-naive)
        # This ensures consistent storage regardless of source timezone
        if df["timestamp"].dt.tz is not None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(None)
        
        # Ensure column order
        df = df[["symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume"]]
        
        # Insert or replace (handles duplicates)
        self.conn.execute("""
            INSERT OR REPLACE INTO ohlcv 
            SELECT * FROM df
        """)
    
    def _update_metadata(self, symbol: str, timeframe: str):
        """Update sync metadata for a symbol/timeframe."""
        stats = self.conn.execute("""
            SELECT 
                MIN(timestamp) as first_ts,
                MAX(timestamp) as last_ts,
                COUNT(*) as count
            FROM ohlcv
            WHERE symbol = ? AND timeframe = ?
        """, [symbol, timeframe]).fetchone()
        
        self.conn.execute("""
            INSERT OR REPLACE INTO sync_metadata 
            VALUES (?, ?, ?, ?, ?, ?)
        """, [symbol, timeframe, stats[0], stats[1], stats[2], datetime.now()])
    
    # ==================== FUNDING RATE SYNC ====================
    
    def sync_funding(
        self,
        symbols: Union[str, List[str]],
        period: str = "3M",
        progress_callback: Callable = None,
        show_spinner: bool = True,
    ) -> Dict[str, int]:
        """
        Sync funding rate history for symbols.
        
        Args:
            symbols: Single symbol or list of symbols
            period: How far back to sync ("1Y", "6M", "3M", "1M", "2W", "1W")
            progress_callback: Optional callback(symbol, status)
            show_spinner: Show animated spinner during sync
        
        Returns:
            Dict mapping symbol to number of records synced
        """
        if isinstance(symbols, str):
            symbols = [symbols]
        
        symbols = [s.upper() for s in symbols]
        target_start = datetime.now() - self.parse_period(period)
        
        results = {}
        
        for symbol in symbols:
            if progress_callback:
                progress_callback(symbol, f"{ActivityEmoji.SYNC} syncing funding rates")
            
            spinner = None
            if show_spinner and not progress_callback:
                spinner = ActivitySpinner(f"Fetching {symbol} funding rates", ActivityEmoji.DOLLAR)
                spinner.start()
            
            try:
                count = self._sync_funding_symbol(symbol, target_start)
                results[symbol] = count
                
                if spinner:
                    spinner.stop(f"{symbol} funding: {count} records {ActivityEmoji.SPARKLE}")
                elif progress_callback:
                    emoji = ActivityEmoji.SUCCESS if count > 0 else ActivityEmoji.CHART
                    progress_callback(symbol, f"{emoji} done ({count:,} records)")
                    
            except Exception as e:
                self.logger.error(f"Failed to sync funding for {symbol}: {e}")
                results[symbol] = -1
                
                if spinner:
                    spinner.stop(f"{symbol} funding: error", success=False)
                elif progress_callback:
                    progress_callback(symbol, f"{ActivityEmoji.ERROR} error: {e}")
        
        return results
    
    def _sync_funding_symbol(self, symbol: str, target_start: datetime) -> int:
        """Sync funding rate data for a single symbol."""
        symbol = symbol.upper()
        
        # Check existing data
        existing = self.conn.execute("""
            SELECT MAX(timestamp) as last_ts
            FROM funding_rates
            WHERE symbol = ?
        """, [symbol]).fetchone()
        
        last_ts = existing[0] if existing[0] else None
        
        # Determine start point
        if last_ts and last_ts > target_start:
            # Only fetch newer data
            fetch_start = last_ts
        else:
            fetch_start = target_start
        
        # Fetch from API
        all_records = []
        current_end = datetime.now()
        
        # Bybit funding API returns max 200 records per request
        while current_end > fetch_start:
            try:
                records = self.client.get_funding_rate(
                    symbol=symbol,
                    limit=200,
                )
                
                if not records:
                    break
                
                # Parse records
                for r in records:
                    ts = datetime.fromtimestamp(int(r.get("fundingRateTimestamp", 0)) / 1000)
                    if ts >= fetch_start and ts <= current_end:
                        all_records.append({
                            "symbol": symbol,
                            "timestamp": ts,
                            "funding_rate": float(r.get("fundingRate", 0)),
                        })
                
                # Move window back
                if records:
                    earliest_ts = min(
                        int(r.get("fundingRateTimestamp", 0)) for r in records
                    )
                    current_end = datetime.fromtimestamp(earliest_ts / 1000) - timedelta(hours=1)
                else:
                    break
                
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                self.logger.warning(f"Funding API error for {symbol}: {e}")
                break
        
        if not all_records:
            return 0
        
        # Store in DuckDB
        df = pd.DataFrame(all_records)
        self._store_funding(symbol, df)
        
        return len(all_records)
    
    def _store_funding(self, symbol: str, df: pd.DataFrame):
        """Store funding rate DataFrame in DuckDB."""
        if df.empty:
            return
        
        symbol = symbol.upper()
        df = df.copy()
        df["symbol"] = symbol
        
        # Remove timezone if present
        if df["timestamp"].dt.tz is not None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(None)
        
        # Ensure columns
        df = df[["symbol", "timestamp", "funding_rate"]]
        
        # Insert or replace
        self.conn.execute("""
            INSERT OR REPLACE INTO funding_rates (symbol, timestamp, funding_rate)
            SELECT symbol, timestamp, funding_rate FROM df
        """)
        
        # Update metadata
        self._update_funding_metadata(symbol)
    
    def _update_funding_metadata(self, symbol: str):
        """Update funding metadata for a symbol."""
        stats = self.conn.execute("""
            SELECT 
                MIN(timestamp) as first_ts,
                MAX(timestamp) as last_ts,
                COUNT(*) as count
            FROM funding_rates
            WHERE symbol = ?
        """, [symbol]).fetchone()
        
        self.conn.execute("""
            INSERT OR REPLACE INTO funding_metadata 
            VALUES (?, ?, ?, ?, ?)
        """, [symbol, stats[0], stats[1], stats[2], datetime.now()])
    
    def get_funding(
        self,
        symbol: str,
        period: str = None,
        start: datetime = None,
        end: datetime = None,
    ) -> pd.DataFrame:
        """
        Get funding rate data as DataFrame.
        
        Args:
            symbol: Trading symbol
            period: Period string ("1M", "2W", etc.) - alternative to start/end
            start: Start datetime
            end: End datetime
        
        Returns:
            DataFrame with timestamp, funding_rate
        """
        symbol = symbol.upper()
        
        query = """
            SELECT timestamp, funding_rate
            FROM funding_rates
            WHERE symbol = ?
        """
        params = [symbol]
        
        if period:
            start = datetime.now() - self.parse_period(period)
        
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        
        query += " ORDER BY timestamp"
        
        return self.conn.execute(query, params).df()
    
    # ==================== OPEN INTEREST SYNC ====================
    
    def sync_open_interest(
        self,
        symbols: Union[str, List[str]],
        period: str = "1M",
        interval: str = "1h",
        progress_callback: Callable = None,
        show_spinner: bool = True,
    ) -> Dict[str, int]:
        """
        Sync open interest history for symbols.
        
        Args:
            symbols: Single symbol or list of symbols
            period: How far back to sync ("1Y", "6M", "3M", "1M", "2W", "1W")
            interval: Data interval (5min, 15min, 30min, 1h, 4h, 1d)
            progress_callback: Optional callback(symbol, status)
            show_spinner: Show animated spinner during sync
        
        Returns:
            Dict mapping symbol to number of records synced
        """
        if isinstance(symbols, str):
            symbols = [symbols]
        
        symbols = [s.upper() for s in symbols]
        target_start = datetime.now() - self.parse_period(period)
        
        results = {}
        
        for symbol in symbols:
            if progress_callback:
                progress_callback(symbol, f"{ActivityEmoji.SYNC} syncing open interest")
            
            spinner = None
            if show_spinner and not progress_callback:
                spinner = ActivitySpinner(f"Fetching {symbol} open interest", ActivityEmoji.CHART)
                spinner.start()
            
            try:
                count = self._sync_open_interest_symbol(symbol, target_start, interval)
                results[symbol] = count
                
                if spinner:
                    spinner.stop(f"{symbol} OI: {count} records {ActivityEmoji.SPARKLE}")
                elif progress_callback:
                    emoji = ActivityEmoji.SUCCESS if count > 0 else ActivityEmoji.CHART
                    progress_callback(symbol, f"{emoji} done ({count:,} records)")
                    
            except Exception as e:
                self.logger.error(f"Failed to sync OI for {symbol}: {e}")
                results[symbol] = -1
                
                if spinner:
                    spinner.stop(f"{symbol} OI: error", success=False)
                elif progress_callback:
                    progress_callback(symbol, f"{ActivityEmoji.ERROR} error: {e}")
        
        return results
    
    def _sync_open_interest_symbol(self, symbol: str, target_start: datetime, interval: str) -> int:
        """Sync open interest data for a single symbol."""
        symbol = symbol.upper()
        
        # Check existing data
        existing = self.conn.execute("""
            SELECT MAX(timestamp) as last_ts
            FROM open_interest
            WHERE symbol = ?
        """, [symbol]).fetchone()
        
        last_ts = existing[0] if existing[0] else None
        
        # Determine start point
        if last_ts and last_ts > target_start:
            fetch_start = last_ts
        else:
            fetch_start = target_start
        
        # Fetch from API
        all_records = []
        current_end = datetime.now()
        
        # Bybit OI API returns max 200 records per request
        while current_end > fetch_start:
            try:
                records = self.client.get_open_interest(
                    symbol=symbol,
                    interval=interval,
                    limit=200,
                )
                
                if not records:
                    break
                
                # Parse records
                for r in records:
                    ts = datetime.fromtimestamp(int(r.get("timestamp", 0)) / 1000)
                    if ts >= fetch_start and ts <= current_end:
                        all_records.append({
                            "symbol": symbol,
                            "timestamp": ts,
                            "open_interest": float(r.get("openInterest", 0)),
                        })
                
                # Move window back
                if records:
                    earliest_ts = min(int(r.get("timestamp", 0)) for r in records)
                    current_end = datetime.fromtimestamp(earliest_ts / 1000) - timedelta(hours=1)
                else:
                    break
                
                time.sleep(0.1)  # Rate limiting
                
            except Exception as e:
                self.logger.warning(f"OI API error for {symbol}: {e}")
                break
        
        if not all_records:
            return 0
        
        # Store in DuckDB
        df = pd.DataFrame(all_records)
        self._store_open_interest(symbol, df)
        
        return len(all_records)
    
    def _store_open_interest(self, symbol: str, df: pd.DataFrame):
        """Store open interest DataFrame in DuckDB."""
        if df.empty:
            return
        
        symbol = symbol.upper()
        df = df.copy()
        df["symbol"] = symbol
        
        # Remove timezone if present
        if df["timestamp"].dt.tz is not None:
            df["timestamp"] = df["timestamp"].dt.tz_localize(None)
        
        # Ensure columns
        df = df[["symbol", "timestamp", "open_interest"]]
        
        # Insert or replace
        self.conn.execute("""
            INSERT OR REPLACE INTO open_interest (symbol, timestamp, open_interest)
            SELECT symbol, timestamp, open_interest FROM df
        """)
        
        # Update metadata
        self._update_oi_metadata(symbol)
    
    def _update_oi_metadata(self, symbol: str):
        """Update open interest metadata for a symbol."""
        stats = self.conn.execute("""
            SELECT 
                MIN(timestamp) as first_ts,
                MAX(timestamp) as last_ts,
                COUNT(*) as count
            FROM open_interest
            WHERE symbol = ?
        """, [symbol]).fetchone()
        
        self.conn.execute("""
            INSERT OR REPLACE INTO open_interest_metadata 
            VALUES (?, ?, ?, ?, ?)
        """, [symbol, stats[0], stats[1], stats[2], datetime.now()])
    
    def get_open_interest(
        self,
        symbol: str,
        period: str = None,
        start: datetime = None,
        end: datetime = None,
    ) -> pd.DataFrame:
        """
        Get open interest data as DataFrame.
        
        Args:
            symbol: Trading symbol
            period: Period string ("1M", "2W", etc.) - alternative to start/end
            start: Start datetime
            end: End datetime
        
        Returns:
            DataFrame with timestamp, open_interest
        """
        symbol = symbol.upper()
        
        query = """
            SELECT timestamp, open_interest
            FROM open_interest
            WHERE symbol = ?
        """
        params = [symbol]
        
        if period:
            start = datetime.now() - self.parse_period(period)
        
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        
        query += " ORDER BY timestamp"
        
        return self.conn.execute(query, params).df()
    
    # ==================== GAP DETECTION & FILLING ====================
    
    def detect_gaps(self, symbol: str, timeframe: str) -> List[Tuple[datetime, datetime]]:
        """
        Detect gaps in data for a symbol/timeframe.
        
        Returns:
            List of (gap_start, gap_end) tuples
        """
        # Normalize symbol to uppercase for consistency
        symbol = symbol.upper()
        
        df = self.conn.execute("""
            SELECT timestamp FROM ohlcv
            WHERE symbol = ? AND timeframe = ?
            ORDER BY timestamp
        """, [symbol, timeframe]).df()
        
        if df.empty or len(df) < 2:
            return []
        
        # Calculate expected interval
        tf_minutes = {"1m": 1, "5m": 5, "15m": 15, "1h": 60, "4h": 240, "1d": 1440}
        expected_interval = timedelta(minutes=tf_minutes.get(timeframe, 15))
        
        gaps = []
        timestamps = df["timestamp"].tolist()
        
        for i in range(1, len(timestamps)):
            actual_gap = timestamps[i] - timestamps[i-1]
            
            # If gap is more than 1.5x expected, it's a gap
            if actual_gap > expected_interval * 1.5:
                gaps.append((timestamps[i-1], timestamps[i]))
        
        return gaps
    
    def fill_gaps(
        self,
        symbol: str = None,
        timeframe: str = None,
        progress_callback: Callable = None,
    ) -> Dict[str, int]:
        """
        Detect and fill gaps in data.
        
        Args:
            symbol: Specific symbol or None for all
            timeframe: Specific timeframe or None for all
            progress_callback: Optional callback(symbol, timeframe, gap_info)
        
        Returns:
            Dict mapping "symbol_timeframe" to number of candles filled
        """
        # Normalize symbol to uppercase for consistency
        if symbol:
            symbol = symbol.upper()
        
        # Get list of symbol/timeframe combinations to check
        if symbol and timeframe:
            combinations = [(symbol, timeframe)]
        elif symbol:
            combinations = [(symbol, tf) for tf in TIMEFRAMES.keys()]
        else:
            # Get all from metadata
            rows = self.conn.execute("""
                SELECT DISTINCT symbol, timeframe FROM sync_metadata
            """).fetchall()
            combinations = [(r[0], r[1]) for r in rows]
        
        results = {}
        
        print_activity(f"Scanning {len(combinations)} symbol/timeframe combinations...", ActivityEmoji.SEARCH)
        
        for sym, tf in combinations:
            key = f"{sym}_{tf}"
            
            # Show scanning progress
            sys.stdout.write(f"\r  {ActivityEmoji.SEARCH} Checking {sym} {tf}...          ")
            sys.stdout.flush()
            
            gaps = self.detect_gaps(sym, tf)
            
            if not gaps:
                results[key] = 0
                continue
            
            print(f"\n  {ActivityEmoji.WARNING} Found {len(gaps)} gap(s) in {sym} {tf}")
            
            total_filled = 0
            
            for i, (gap_start, gap_end) in enumerate(gaps, 1):
                if progress_callback:
                    progress_callback(sym, tf, f"{ActivityEmoji.REPAIR} Filling gap {i}/{len(gaps)}: {gap_start} → {gap_end}")
                else:
                    print_activity(f"Filling gap {i}/{len(gaps)}: {gap_start} → {gap_end}", ActivityEmoji.REPAIR)
                
                count = self._sync_symbol_timeframe(sym, tf, gap_start, gap_end)
                total_filled += count
            
            results[key] = total_filled
        
        # Clear scanning line
        sys.stdout.write(f"\r  {ActivityEmoji.SUCCESS} Scan complete!                    \n")
        sys.stdout.flush()
        
        return results
    
    def heal(
        self,
        symbol: str = None,
        fix_issues: bool = True,
        fill_gaps_after: bool = True,
    ) -> Dict[str, Any]:
        """
        Comprehensive data integrity check and repair.
        
        Checks for:
        - Duplicate timestamps
        - Invalid OHLCV (high < low, open/close outside high-low range)
        - Negative/zero volumes
        - NULL values in critical columns
        - Symbol casing inconsistencies
        - Time gaps
        
        Args:
            symbol: Specific symbol to heal, or None for all
            fix_issues: If True, automatically fix found issues
            fill_gaps_after: If True, fill gaps after fixing other issues
        
        Returns:
            Dict with detailed report of issues found and fixed
        """
        # Normalize symbol if provided
        if symbol:
            symbol = symbol.upper()
        
        print_activity("Starting data integrity check...", ActivityEmoji.SEARCH)
        
        report = {
            "checked_at": datetime.now().isoformat(),
            "symbol_filter": symbol,
            "issues_found": 0,
            "issues_fixed": 0,
            "details": {},
        }
        
        # Build WHERE clause for symbol filter
        where_clause = f"WHERE symbol = '{symbol}'" if symbol else ""
        and_clause = f"AND symbol = '{symbol}'" if symbol else ""
        
        # 1. Check for duplicates (should be 0 due to PRIMARY KEY)
        print_activity("Checking for duplicate timestamps...", ActivityEmoji.SEARCH)
        dupes = self.conn.execute(f"""
            SELECT symbol, timeframe, timestamp, COUNT(*) as cnt
            FROM ohlcv
            {where_clause}
            GROUP BY symbol, timeframe, timestamp
            HAVING COUNT(*) > 1
        """).fetchall()
        
        report["details"]["duplicates"] = {
            "found": len(dupes),
            "fixed": 0,
            "samples": [{"symbol": d[0], "timeframe": d[1], "timestamp": str(d[2])} for d in dupes[:5]]
        }
        report["issues_found"] += len(dupes)
        
        if dupes and fix_issues:
            # Remove duplicates by keeping one (DuckDB doesn't have ROWID, so we recreate)
            print_activity(f"Removing {len(dupes)} duplicate entries...", ActivityEmoji.REPAIR)
            # The PRIMARY KEY constraint should prevent this, but if somehow there are dupes:
            for sym, tf, ts, cnt in dupes:
                self.conn.execute("""
                    DELETE FROM ohlcv 
                    WHERE symbol = ? AND timeframe = ? AND timestamp = ?
                """, [sym, tf, ts])
                # Re-insert one copy (we lost data, but at least it's consistent)
            report["details"]["duplicates"]["fixed"] = len(dupes)
            report["issues_fixed"] += len(dupes)
        
        # 2. Check for invalid OHLCV (high < low)
        print_activity("Checking for invalid high < low...", ActivityEmoji.SEARCH)
        invalid_hl = self.conn.execute(f"""
            SELECT symbol, timeframe, timestamp, open, high, low, close
            FROM ohlcv
            WHERE high < low {and_clause.replace('AND', 'AND' if where_clause else '')}
        """.replace('AND  AND', 'AND')).fetchall()
        
        report["details"]["invalid_high_low"] = {
            "found": len(invalid_hl),
            "fixed": 0,
            "samples": [{"symbol": r[0], "timeframe": r[1], "timestamp": str(r[2])} for r in invalid_hl[:5]]
        }
        report["issues_found"] += len(invalid_hl)
        
        if invalid_hl and fix_issues:
            print_activity(f"Removing {len(invalid_hl)} invalid high<low rows...", ActivityEmoji.REPAIR)
            if symbol:
                self.conn.execute(f"DELETE FROM ohlcv WHERE high < low AND symbol = ?", [symbol])
            else:
                self.conn.execute("DELETE FROM ohlcv WHERE high < low")
            report["details"]["invalid_high_low"]["fixed"] = len(invalid_hl)
            report["issues_fixed"] += len(invalid_hl)
        
        # 3. Check for negative volumes
        print_activity("Checking for negative volumes...", ActivityEmoji.SEARCH)
        neg_vol_count = self.conn.execute(f"""
            SELECT COUNT(*) FROM ohlcv WHERE volume < 0 {and_clause.replace('AND', 'AND' if where_clause else '')}
        """.replace('AND  AND', 'AND')).fetchone()[0]
        
        report["details"]["negative_volumes"] = {
            "found": neg_vol_count,
            "fixed": 0,
        }
        report["issues_found"] += neg_vol_count
        
        if neg_vol_count > 0 and fix_issues:
            print_activity(f"Setting {neg_vol_count} negative volumes to 0...", ActivityEmoji.REPAIR)
            if symbol:
                self.conn.execute("UPDATE ohlcv SET volume = 0 WHERE volume < 0 AND symbol = ?", [symbol])
            else:
                self.conn.execute("UPDATE ohlcv SET volume = 0 WHERE volume < 0")
            report["details"]["negative_volumes"]["fixed"] = neg_vol_count
            report["issues_fixed"] += neg_vol_count
        
        # 4. Check for NULL values in critical columns
        print_activity("Checking for NULL values...", ActivityEmoji.SEARCH)
        null_counts = self.conn.execute(f"""
            SELECT 
                SUM(CASE WHEN open IS NULL THEN 1 ELSE 0 END) as null_open,
                SUM(CASE WHEN high IS NULL THEN 1 ELSE 0 END) as null_high,
                SUM(CASE WHEN low IS NULL THEN 1 ELSE 0 END) as null_low,
                SUM(CASE WHEN close IS NULL THEN 1 ELSE 0 END) as null_close,
                SUM(CASE WHEN volume IS NULL THEN 1 ELSE 0 END) as null_volume,
                SUM(CASE WHEN timestamp IS NULL THEN 1 ELSE 0 END) as null_ts
            FROM ohlcv
            {where_clause}
        """).fetchone()
        
        total_nulls = sum(n or 0 for n in null_counts)
        report["details"]["null_values"] = {
            "found": total_nulls,
            "fixed": 0,
            "breakdown": {
                "open": null_counts[0] or 0,
                "high": null_counts[1] or 0,
                "low": null_counts[2] or 0,
                "close": null_counts[3] or 0,
                "volume": null_counts[4] or 0,
                "timestamp": null_counts[5] or 0,
            }
        }
        report["issues_found"] += total_nulls
        
        if total_nulls > 0 and fix_issues:
            print_activity(f"Removing {total_nulls} rows with NULL values...", ActivityEmoji.REPAIR)
            if symbol:
                self.conn.execute("""
                    DELETE FROM ohlcv 
                    WHERE (open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR timestamp IS NULL)
                    AND symbol = ?
                """, [symbol])
            else:
                self.conn.execute("""
                    DELETE FROM ohlcv 
                    WHERE open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR timestamp IS NULL
                """)
            report["details"]["null_values"]["fixed"] = total_nulls
            report["issues_fixed"] += total_nulls
        
        # 5. Check for symbol casing inconsistencies (non-uppercase)
        print_activity("Checking symbol casing...", ActivityEmoji.SEARCH)
        # DuckDB doesn't have easy regex, so we check if symbol != UPPER(symbol)
        bad_casing = self.conn.execute(f"""
            SELECT DISTINCT symbol FROM ohlcv 
            WHERE symbol != UPPER(symbol)
            {and_clause.replace('AND', 'AND' if where_clause else '')}
        """.replace('AND  AND', 'AND')).fetchall()
        
        report["details"]["symbol_casing"] = {
            "found": len(bad_casing),
            "fixed": 0,
            "symbols": [r[0] for r in bad_casing]
        }
        report["issues_found"] += len(bad_casing)
        
        if bad_casing and fix_issues:
            print_activity(f"Normalizing {len(bad_casing)} symbol(s) to uppercase...", ActivityEmoji.REPAIR)
            for (bad_sym,) in bad_casing:
                # Update to uppercase
                self.conn.execute("""
                    UPDATE ohlcv SET symbol = UPPER(symbol) WHERE symbol = ?
                """, [bad_sym])
                self.conn.execute("""
                    UPDATE sync_metadata SET symbol = UPPER(symbol) WHERE symbol = ?
                """, [bad_sym])
            report["details"]["symbol_casing"]["fixed"] = len(bad_casing)
            report["issues_fixed"] += len(bad_casing)
        
        # 6. Check for price anomalies (open/close outside high-low range)
        print_activity("Checking for price anomalies...", ActivityEmoji.SEARCH)
        price_anomalies = self.conn.execute(f"""
            SELECT COUNT(*) FROM ohlcv 
            WHERE (open > high OR open < low OR close > high OR close < low)
            {and_clause.replace('AND', 'AND' if where_clause else '')}
        """.replace('AND  AND', 'AND')).fetchone()[0]
        
        report["details"]["price_anomalies"] = {
            "found": price_anomalies,
            "fixed": 0,
            "note": "Open/close outside high-low range"
        }
        report["issues_found"] += price_anomalies
        
        if price_anomalies > 0 and fix_issues:
            print_activity(f"Removing {price_anomalies} rows with price anomalies...", ActivityEmoji.REPAIR)
            if symbol:
                self.conn.execute("""
                    DELETE FROM ohlcv 
                    WHERE (open > high OR open < low OR close > high OR close < low)
                    AND symbol = ?
                """, [symbol])
            else:
                self.conn.execute("""
                    DELETE FROM ohlcv 
                    WHERE open > high OR open < low OR close > high OR close < low
                """)
            report["details"]["price_anomalies"]["fixed"] = price_anomalies
            report["issues_fixed"] += price_anomalies
        
        # 7. Update metadata after fixes
        if fix_issues and report["issues_fixed"] > 0:
            print_activity("Updating metadata...", ActivityEmoji.DATABASE)
            # Get all symbol/timeframe combinations
            if symbol:
                combos = self.conn.execute("""
                    SELECT DISTINCT symbol, timeframe FROM ohlcv WHERE symbol = ?
                """, [symbol]).fetchall()
            else:
                combos = self.conn.execute("""
                    SELECT DISTINCT symbol, timeframe FROM ohlcv
                """).fetchall()
            
            for sym, tf in combos:
                self._update_metadata(sym, tf)
        
        # 8. Check and fill gaps
        print_activity("Checking for time gaps...", ActivityEmoji.SEARCH)
        if symbol:
            combos = [(symbol, tf) for tf in TIMEFRAMES.keys()]
        else:
            combos = self.conn.execute("""
                SELECT DISTINCT symbol, timeframe FROM sync_metadata
            """).fetchall()
        
        total_gaps = 0
        gap_details = {}
        for sym, tf in combos:
            gaps = self.detect_gaps(sym, tf)
            if gaps:
                total_gaps += len(gaps)
                gap_details[f"{sym}_{tf}"] = len(gaps)
        
        report["details"]["gaps"] = {
            "found": total_gaps,
            "filled": 0,
            "by_symbol_tf": gap_details
        }
        report["issues_found"] += total_gaps
        
        if total_gaps > 0 and fix_issues and fill_gaps_after:
            print_activity(f"Filling {total_gaps} gaps...", ActivityEmoji.REPAIR)
            fill_results = self.fill_gaps(symbol=symbol)
            filled = sum(v for v in fill_results.values() if v > 0)
            report["details"]["gaps"]["filled"] = filled
            report["issues_fixed"] += filled
        
        # Summary
        print("\n" + "=" * 60)
        if report["issues_found"] == 0:
            print_activity("Data is healthy! No issues found.", ActivityEmoji.SUCCESS)
        else:
            emoji = ActivityEmoji.SUCCESS if report["issues_fixed"] == report["issues_found"] else ActivityEmoji.WARNING
            print_activity(
                f"Found {report['issues_found']} issues, fixed {report['issues_fixed']}", 
                emoji
            )
        print("=" * 60 + "\n")
        
        return report
    
    # ==================== QUERY METHODS ====================
    
    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        period: str = None,
        start: datetime = None,
        end: datetime = None,
    ) -> pd.DataFrame:
        """
        Get OHLCV data as DataFrame.
        
        Args:
            symbol: Trading symbol
            timeframe: Candle timeframe
            period: Period string ("1M", "2W", etc.) - alternative to start/end
            start: Start datetime
            end: End datetime
        
        Returns:
            DataFrame with timestamp, open, high, low, close, volume
        """
        # Normalize symbol to uppercase for consistency
        symbol = symbol.upper()
        
        query = """
            SELECT timestamp, open, high, low, close, volume
            FROM ohlcv
            WHERE symbol = ? AND timeframe = ?
        """
        params = [symbol, timeframe]
        
        if period:
            start = datetime.now() - self.parse_period(period)
        
        if start:
            query += " AND timestamp >= ?"
            params.append(start)
        
        if end:
            query += " AND timestamp <= ?"
            params.append(end)
        
        query += " ORDER BY timestamp"
        
        return self.conn.execute(query, params).df()
    
    def get_mtf_data(
        self,
        symbol: str,
        preset: str = "day",
        period: str = "1M",
    ) -> Dict[str, pd.DataFrame]:
        """
        Get multi-timeframe data for backtesting.
        
        Args:
            symbol: Trading symbol
            preset: MTF preset ("swing", "day", "intraday", "scalp")
            period: How far back
        
        Returns:
            Dict with "htf", "mtf", "ltf" DataFrames
        """
        # Normalize symbol to uppercase for consistency
        symbol = symbol.upper()
        
        presets = {
            "swing":    ("1d", "4h", "1h"),
            "day":      ("4h", "1h", "15m"),
            "intraday": ("1h", "15m", "5m"),
            "scalp":    ("15m", "5m", "1m"),
        }
        
        if preset not in presets:
            raise ValueError(f"Invalid preset: {preset}. Use: {list(presets.keys())}")
        
        htf, mtf, ltf = presets[preset]
        
        return {
            "htf": self.get_ohlcv(symbol, htf, period=period),
            "mtf": self.get_ohlcv(symbol, mtf, period=period),
            "ltf": self.get_ohlcv(symbol, ltf, period=period),
            "_meta": {
                "symbol": symbol,
                "preset": preset,
                "htf_tf": htf,
                "mtf_tf": mtf,
                "ltf_tf": ltf,
                "period": period,
            }
        }
    
    # ==================== STATUS METHODS ====================
    
    def status(self, symbol: str = None) -> Dict:
        """
        Get status of cached data.
        
        Args:
            symbol: Specific symbol or None for all
        
        Returns:
            Dict with status information
        """
        # Normalize symbol to uppercase for consistency
        if symbol:
            symbol = symbol.upper()
            rows = self.conn.execute("""
                SELECT * FROM sync_metadata WHERE symbol = ?
            """, [symbol]).fetchall()
        else:
            rows = self.conn.execute("""
                SELECT * FROM sync_metadata ORDER BY symbol, timeframe
            """).fetchall()
        
        status = {}
        
        for row in rows:
            sym, tf, first_ts, last_ts, count, last_sync = row
            key = f"{sym}_{tf}"
            
            gaps = self.detect_gaps(sym, tf)
            
            status[key] = {
                "symbol": sym,
                "timeframe": tf,
                "first_timestamp": first_ts,
                "last_timestamp": last_ts,
                "candle_count": count,
                "last_sync": last_sync,
                "gaps": len(gaps),
                "is_current": last_ts and (datetime.now() - last_ts).total_seconds() < 3600,
            }
        
        return status
    
    def list_symbols(self) -> List[str]:
        """List all symbols with cached data."""
        rows = self.conn.execute("""
            SELECT DISTINCT symbol FROM sync_metadata ORDER BY symbol
        """).fetchall()
        return [r[0] for r in rows]
    
    def get_database_stats(self) -> Dict:
        """Get overall database statistics."""
        # OHLCV stats
        ohlcv_stats = self.conn.execute("""
            SELECT 
                COUNT(DISTINCT symbol) as symbols,
                COUNT(DISTINCT symbol || '_' || timeframe) as combinations,
                COUNT(*) as total_candles
            FROM ohlcv
        """).fetchone()
        
        # Funding stats
        funding_stats = self.conn.execute("""
            SELECT 
                COUNT(DISTINCT symbol) as symbols,
                COUNT(*) as total_records
            FROM funding_rates
        """).fetchone()
        
        # Open interest stats
        oi_stats = self.conn.execute("""
            SELECT 
                COUNT(DISTINCT symbol) as symbols,
                COUNT(*) as total_records
            FROM open_interest
        """).fetchone()
        
        file_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        
        return {
            "db_path": str(self.db_path),
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "ohlcv": {
                "symbols": ohlcv_stats[0],
                "symbol_timeframe_combinations": ohlcv_stats[1],
                "total_candles": ohlcv_stats[2],
            },
            "funding_rates": {
                "symbols": funding_stats[0],
                "total_records": funding_stats[1],
            },
            "open_interest": {
                "symbols": oi_stats[0],
                "total_records": oi_stats[1],
            },
            # Legacy fields for backwards compatibility
            "symbols": ohlcv_stats[0],
            "symbol_timeframe_combinations": ohlcv_stats[1],
            "total_candles": ohlcv_stats[2],
        }
    
    # ==================== MAINTENANCE ====================
    
    def delete_symbol(self, symbol: str) -> int:
        """
        Delete all data for a symbol.
        
        Returns:
            Number of candles deleted
        """
        # Normalize symbol to uppercase for consistency
        symbol = symbol.upper()
        
        # Get count before delete
        count = self.conn.execute("""
            SELECT COUNT(*) FROM ohlcv WHERE symbol = ?
        """, [symbol]).fetchone()[0]
        
        self.conn.execute("DELETE FROM ohlcv WHERE symbol = ?", [symbol])
        self.conn.execute("DELETE FROM sync_metadata WHERE symbol = ?", [symbol])
        
        return count
    
    def delete_symbol_timeframe(self, symbol: str, timeframe: str) -> int:
        """
        Delete data for a specific symbol/timeframe combination.
        
        Returns:
            Number of candles deleted
        """
        # Normalize symbol to uppercase for consistency
        symbol = symbol.upper()
        
        count = self.conn.execute("""
            SELECT COUNT(*) FROM ohlcv WHERE symbol = ? AND timeframe = ?
        """, [symbol, timeframe]).fetchone()[0]
        
        self.conn.execute("DELETE FROM ohlcv WHERE symbol = ? AND timeframe = ?", [symbol, timeframe])
        self.conn.execute("DELETE FROM sync_metadata WHERE symbol = ? AND timeframe = ?", [symbol, timeframe])
        
        return count
    
    def cleanup_empty_symbols(self) -> List[str]:
        """
        Remove symbols that have metadata but no actual data.
        This cleans up invalid symbol entries.
        
        Returns:
            List of symbols that were cleaned up
        """
        # Find symbols with metadata but no data
        orphaned = self.conn.execute("""
            SELECT DISTINCT m.symbol 
            FROM sync_metadata m 
            LEFT JOIN ohlcv o ON m.symbol = o.symbol 
            WHERE o.symbol IS NULL
        """).fetchall()
        
        cleaned = []
        for row in orphaned:
            symbol = row[0]
            self.conn.execute("DELETE FROM sync_metadata WHERE symbol = ?", [symbol])
            cleaned.append(symbol)
        
        # Also find symbols with 0 candles in metadata
        zero_count = self.conn.execute("""
            SELECT DISTINCT symbol FROM sync_metadata WHERE candle_count = 0 OR candle_count IS NULL
        """).fetchall()
        
        for row in zero_count:
            symbol = row[0]
            if symbol not in cleaned:
                self.conn.execute("DELETE FROM sync_metadata WHERE symbol = ?", [symbol])
                cleaned.append(symbol)
        
        return cleaned
    
    def get_symbol_summary(self) -> List[Dict]:
        """
        Get summary of all symbols with their data status.
        Useful for displaying in delete menu.
        
        Returns:
            List of dicts with symbol info
        """
        rows = self.conn.execute("""
            SELECT 
                symbol,
                COUNT(DISTINCT timeframe) as timeframes,
                SUM(candle_count) as total_candles,
                MIN(first_timestamp) as earliest,
                MAX(last_timestamp) as latest
            FROM sync_metadata
            GROUP BY symbol
            ORDER BY symbol
        """).fetchall()
        
        return [
            {
                "symbol": r[0],
                "timeframes": r[1],
                "total_candles": r[2] or 0,
                "earliest": r[3],
                "latest": r[4],
            }
            for r in rows
        ]
    
    def vacuum(self):
        """Reclaim disk space after deletions."""
        self.conn.execute("VACUUM")
    
    def close(self):
        """Close database connection."""
        self.conn.close()


# Singleton instance
_store: Optional[HistoricalDataStore] = None


def get_historical_store() -> HistoricalDataStore:
    """Get or create the global HistoricalDataStore instance."""
    global _store
    if _store is None:
        _store = HistoricalDataStore()
    return _store

