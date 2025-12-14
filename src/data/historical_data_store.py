"""
Historical Data Store - DuckDB-backed market data storage.

Provides:
- Efficient columnar storage for OHLCV data
- Auto-sync with gap detection and filling
- Period-based data retrieval (1Y, 6M, 1W, 1D, etc.)
- DataFrame output for backtesting
- Environment-aware storage (live vs demo)

Architecture:
- Each data environment (live/demo) has its own DuckDB file
- Table names are env-specific (e.g., ohlcv_live, ohlcv_demo)
- Live history is canonical for research/backtests
- Demo history is isolated for demo testing sessions
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
from ..config.constants import (
    DataEnv,
    DEFAULT_DATA_ENV,
    validate_data_env,
    resolve_db_path,
    resolve_table_name,
)
from ..utils.logger import get_logger


# Activity emojis for visual feedback (with Windows-safe fallbacks)
import sys
import os

# Detect if we're on Windows with a non-UTF8 console
_USE_ASCII = (
    sys.platform == "win32" 
    and os.environ.get("PYTHONIOENCODING", "").lower() != "utf-8"
    and not os.environ.get("WT_SESSION")  # Windows Terminal supports UTF-8
)


class ActivityEmoji:
    """Fun emojis for different activities. Falls back to ASCII on Windows."""
    # Data operations
    SYNC = "[SYNC]" if _USE_ASCII else "📡"
    DOWNLOAD = "[DL]" if _USE_ASCII else "⬇️"
    UPLOAD = "[UL]" if _USE_ASCII else "⬆️"
    CANDLE = "[C]" if _USE_ASCII else "🕯️"
    CHART = "[CHART]" if _USE_ASCII else "📊"
    DATABASE = "[DB]" if _USE_ASCII else "🗄️"
    
    # Money/Trading
    MONEY_BAG = "[$]" if _USE_ASCII else "💰"
    DOLLAR = "[$]" if _USE_ASCII else "💵"
    ROCKET = "[^]" if _USE_ASCII else "🚀"
    STONKS = "[+]" if _USE_ASCII else "📈"
    
    # Status
    LOADING = "[...]" if _USE_ASCII else "⏳"
    SUCCESS = "[OK]" if _USE_ASCII else "✅"
    ERROR = "[ERR]" if _USE_ASCII else "❌"
    WARNING = "[WARN]" if _USE_ASCII else "⚠️"
    SEARCH = "[?]" if _USE_ASCII else "🔍"
    REPAIR = "[FIX]" if _USE_ASCII else "🔧"
    TRASH = "[DEL]" if _USE_ASCII else "🗑️"
    SPARKLE = "[*]" if _USE_ASCII else "✨"
    FIRE = "[!]" if _USE_ASCII else "🔥"
    
    # Progress spinners (ASCII-safe versions)
    SPINNERS = ["|", "/", "-", "\\"] if _USE_ASCII else ["◐", "◓", "◑", "◒"]
    BARS = ["#"] * 8 if _USE_ASCII else ["▏", "▎", "▍", "▌", "▋", "▊", "▉", "█"]
    DOTS = ["."] * 10 if _USE_ASCII else ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]


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
TF_MINUTES = {
    "1m": 1,
    "5m": 5,
    "15m": 15,
    "1h": 60,
    "4h": 240,
    "1d": 1440,
}
# Alias for backward compatibility
TIMEFRAME_MINUTES = TF_MINUTES

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
    """Status of a symbol/tf sync."""
    symbol: str
    tf: str
    first_timestamp: Optional[datetime]
    last_timestamp: Optional[datetime]
    candle_count: int
    gaps: List[Tuple[datetime, datetime]]
    is_current: bool


class HistoricalDataStore:
    """
    DuckDB-backed historical market data storage.
    
    Environment-aware: each env (live/demo) has its own database file
    with env-specific table names (e.g., ohlcv_live, ohlcv_demo).
    
    Usage:
        # Default: live environment
        store = HistoricalDataStore()
        
        # Explicit environment
        live_store = HistoricalDataStore(env="live")
        demo_store = HistoricalDataStore(env="demo")
        
        # Sync data
        store.sync("BTCUSDT", period="3M")  # 3 months, all timeframes
        store.sync(["BTCUSDT", "ETHUSDT"], period="1M", timeframes=["15m", "1h", "4h"])
        
        # Query data
        df = store.get_ohlcv("BTCUSDT", "15m", period="1M")
        
        # Check status
        status = store.status("BTCUSDT")
    
    Attributes:
        env: Data environment ("live" or "demo")
        db_path: Path to the DuckDB file
        table_ohlcv: Name of OHLCV table (e.g., "ohlcv_live")
        table_sync_metadata: Name of sync metadata table
        table_funding: Name of funding rates table
        table_funding_metadata: Name of funding metadata table
        table_oi: Name of open interest table
        table_oi_metadata: Name of open interest metadata table
    """
    
    def __init__(self, env: DataEnv = DEFAULT_DATA_ENV, db_path: str = None):
        """
        Initialize the data store.
        
        Args:
            env: Data environment ("live" or "demo"). Defaults to "live".
            db_path: Optional explicit DB path (overrides env-based resolution).
        """
        # Validate and store environment
        self.env: DataEnv = validate_data_env(env)
        
        # Resolve DB path based on environment (or use explicit path)
        if db_path:
            self.db_path = Path(db_path)
        else:
            self.db_path = resolve_db_path(self.env)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Resolve table names for this environment
        self.table_ohlcv = resolve_table_name("ohlcv", self.env)
        self.table_sync_metadata = resolve_table_name("sync_metadata", self.env)
        self.table_funding = resolve_table_name("funding_rates", self.env)
        self.table_funding_metadata = resolve_table_name("funding_metadata", self.env)
        self.table_oi = resolve_table_name("open_interest", self.env)
        self.table_oi_metadata = resolve_table_name("open_interest_metadata", self.env)
        
        self.conn = duckdb.connect(str(self.db_path))
        self.config = get_config()
        self.logger = get_logger()
        
        # Select API and credentials based on data environment
        # - live: Use LIVE API with LIVE data keys (canonical backtest history)
        # - demo: Use DEMO API with DEMO data keys (demo-only history)
        if self.env == "live":
            # LIVE environment: use LIVE API with dedicated data credentials
            api_key, api_secret = self.config.bybit.get_live_data_credentials()
            use_demo_api = False
            api_name = "LIVE"
            api_url = "api.bybit.com"
            
            if not api_key or not api_secret:
                self.logger.error(
                    "MISSING REQUIRED KEY: BYBIT_LIVE_DATA_API_KEY/SECRET not configured! "
                    "Historical LIVE data sync requires LIVE data API access. "
                    "No fallback to trading keys."
                )
            key_source = "BYBIT_LIVE_DATA_API_KEY" if api_key else "MISSING"
        else:
            # DEMO environment: use DEMO API with dedicated DEMO data credentials
            api_key, api_secret = self.config.bybit.get_demo_data_credentials()
            use_demo_api = True
            api_name = "DEMO"
            api_url = "api-demo.bybit.com"
            
            if not api_key or not api_secret:
                self.logger.error(
                    "MISSING REQUIRED KEY: BYBIT_DEMO_DATA_API_KEY/SECRET not configured! "
                    "Historical DEMO data sync requires DEMO data API access. "
                    "No fallback to trading keys."
                )
            key_source = "BYBIT_DEMO_DATA_API_KEY" if api_key else "MISSING"
        
        # Initialize client with appropriate API endpoint
        self.client = BybitClient(
            api_key=api_key if api_key else None,
            api_secret=api_secret if api_secret else None,
            use_demo=use_demo_api,
        )
        
        # Cancellation flag for graceful interruption
        self._cancelled = False
        
        # Log API environment info
        key_status = "authenticated" if api_key else "NO KEY"
        
        self.logger.info(
            f"HistoricalDataStore initialized: "
            f"env={self.env}, "
            f"db={self.db_path}, "
            f"API={api_name} ({api_url}), "
            f"auth={key_status}, "
            f"key_source={key_source}"
        )
        
        self._init_schema()
    
    def _init_schema(self):
        """Initialize database schema with env-specific table names."""
        # OHLCV candle data
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_ohlcv} (
                symbol VARCHAR NOT NULL,
                timeframe VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open DOUBLE,
                high DOUBLE,
                low DOUBLE,
                close DOUBLE,
                volume DOUBLE,
                turnover DOUBLE,
                PRIMARY KEY (symbol, timeframe, timestamp)
            )
        """)
        
        # Schema migration: add turnover column if missing from existing table
        try:
            self.conn.execute(f"""
                ALTER TABLE {self.table_ohlcv} ADD COLUMN turnover DOUBLE
            """)
        except Exception:
            pass  # Column already exists
        
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_sync_metadata} (
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
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_funding} (
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                funding_rate DOUBLE,
                funding_rate_interval_hours INTEGER DEFAULT 8,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
        
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_funding_metadata} (
                symbol VARCHAR NOT NULL,
                first_timestamp TIMESTAMP,
                last_timestamp TIMESTAMP,
                record_count INTEGER,
                last_sync TIMESTAMP,
                PRIMARY KEY (symbol)
            )
        """)
        
        # Open interest data
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_oi} (
                symbol VARCHAR NOT NULL,
                timestamp TIMESTAMP NOT NULL,
                open_interest DOUBLE,
                PRIMARY KEY (symbol, timestamp)
            )
        """)
        
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_oi_metadata} (
                symbol VARCHAR NOT NULL,
                first_timestamp TIMESTAMP,
                last_timestamp TIMESTAMP,
                record_count INTEGER,
                last_sync TIMESTAMP,
                PRIMARY KEY (symbol)
            )
        """)
        
        # Extremes metadata table (Phase -1: bounds per symbol/tf after bootstrap)
        self.table_extremes = resolve_table_name("data_extremes", self.env)
        self.conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.table_extremes} (
                symbol VARCHAR NOT NULL,
                data_type VARCHAR NOT NULL,
                timeframe VARCHAR,
                earliest_ts TIMESTAMP,
                latest_ts TIMESTAMP,
                row_count INTEGER,
                gap_count_after_heal INTEGER DEFAULT 0,
                resolved_launch_time TIMESTAMP,
                source VARCHAR,
                last_updated TIMESTAMP,
                PRIMARY KEY (symbol, data_type, timeframe)
            )
        """)
        
        # Create indexes for faster queries (env-specific index names)
        idx_suffix = f"_{self.env}"
        try:
            self.conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_ohlcv_symbol_tf{idx_suffix}
                ON {self.table_ohlcv}(symbol, timeframe)
            """)
        except Exception:
            pass  # Index may already exist
        
        try:
            self.conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_ohlcv_timestamp{idx_suffix}
                ON {self.table_ohlcv}(timestamp)
            """)
        except Exception:
            pass  # Index may already exist
        
        try:
            self.conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_funding_symbol{idx_suffix}
                ON {self.table_funding}(symbol)
            """)
        except Exception:
            pass
        
        try:
            self.conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_funding_timestamp{idx_suffix}
                ON {self.table_funding}(timestamp)
            """)
        except Exception:
            pass
        
        try:
            self.conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_oi_symbol{idx_suffix}
                ON {self.table_oi}(symbol)
            """)
        except Exception:
            pass
        
        try:
            self.conn.execute(f"""
                CREATE INDEX IF NOT EXISTS idx_oi_timestamp{idx_suffix}
                ON {self.table_oi}(timestamp)
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
    
    def cancel(self):
        """Cancel ongoing data fetching operations."""
        self._cancelled = True
    
    def reset_cancellation(self):
        """Reset cancellation flag."""
        self._cancelled = False
    
    def sync(
        self,
        symbols: Union[str, List[str]],
        period: str = "1M",
        timeframes: List[str] = None,
        progress_callback: Callable = None,
        show_spinner: bool = True,
    ) -> Dict[str, int]:
        """Sync historical data for symbols. See module docstring for details."""
        from . import historical_sync
        return historical_sync.sync(
            self, symbols, period, timeframes, progress_callback, show_spinner
        )
    
    def sync_range(
        self,
        symbols: Union[str, List[str]],
        start: datetime,
        end: datetime,
        timeframes: List[str] = None,
    ) -> Dict[str, int]:
        """Sync a specific date range."""
        from . import historical_sync
        return historical_sync.sync_range(self, symbols, start, end, timeframes)
    
    def sync_forward(
        self,
        symbols: Union[str, List[str]],
        timeframes: List[str] = None,
        progress_callback: Callable = None,
        show_spinner: bool = True,
    ) -> Dict[str, int]:
        """Sync data forward from the last stored candle to now."""
        from . import historical_sync
        return historical_sync.sync_forward(
            self, symbols, timeframes, progress_callback, show_spinner
        )
    
    def _sync_forward_symbol_timeframe(self, symbol: str, timeframe: str) -> int:
        """Sync a single symbol/timeframe forward from last timestamp to now."""
        from . import historical_sync
        return historical_sync._sync_forward_symbol_timeframe(self, symbol, timeframe)
    
    def _sync_symbol_timeframe(
        self,
        symbol: str,
        timeframe: str,
        target_start: datetime,
        target_end: datetime,
    ) -> int:
        """Sync a single symbol/timeframe combination."""
        from . import historical_sync
        return historical_sync._sync_symbol_timeframe(
            self, symbol, timeframe, target_start, target_end
        )
    
    def _fetch_from_api(
        self,
        symbol: str,
        bybit_tf: str,
        start: datetime,
        end: datetime,
        show_progress: bool = True,
        progress_prefix: str = None,
    ) -> pd.DataFrame:
        """Fetch data from Bybit API with visual progress."""
        from . import historical_sync
        return historical_sync._fetch_from_api(
            self, symbol, bybit_tf, start, end, show_progress, progress_prefix
        )
    
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
        self.conn.execute(f"""
            INSERT OR REPLACE INTO {self.table_ohlcv} 
            SELECT * FROM df
        """)
    
    def _update_metadata(self, symbol: str, timeframe: str):
        """Update sync metadata for a symbol/timeframe."""
        stats = self.conn.execute(f"""
            SELECT 
                MIN(timestamp) as first_ts,
                MAX(timestamp) as last_ts,
                COUNT(*) as count
            FROM {self.table_ohlcv}
            WHERE symbol = ? AND timeframe = ?
        """, [symbol, timeframe]).fetchone()
        
        self.conn.execute(f"""
            INSERT OR REPLACE INTO {self.table_sync_metadata} 
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
            # Check for cancellation
            if self._cancelled:
                self.logger.info("Funding sync cancelled by user")
                break
            
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
                    
            except KeyboardInterrupt:
                self._cancelled = True
                self.logger.info("Funding sync interrupted by user")
                if spinner:
                    spinner.stop(f"{symbol} funding: cancelled", success=False)
                elif progress_callback:
                    progress_callback(symbol, f"{ActivityEmoji.WARNING} cancelled")
                break
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
        existing = self.conn.execute(f"""
            SELECT MAX(timestamp) as last_ts
            FROM {self.table_funding}
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
        request_count = 0
        
        # Bybit funding API returns max 200 records per request
        while current_end > fetch_start:
            # Check for cancellation
            if self._cancelled:
                break
            
            try:
                # Show progress
                dots = ActivityEmoji.DOTS[request_count % len(ActivityEmoji.DOTS)]
                records_count = request_count * 200
                sys.stdout.write(f"\r    {ActivityEmoji.DOWNLOAD} {dots} {symbol} funding: Fetching records... ({records_count}+)   ")
                sys.stdout.flush()
                
                # Pass endTime to paginate backwards through history
                # Bybit: "Passing only endTime returns 200 records up till endTime"
                records = self.client.get_funding_rate(
                    symbol=symbol,
                    limit=200,
                    end_time=int(current_end.timestamp() * 1000),
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
                
                request_count += 1
                
                # Move window back
                if records:
                    earliest_ts = min(
                        int(r.get("fundingRateTimestamp", 0)) for r in records
                    )
                    current_end = datetime.fromtimestamp(earliest_ts / 1000) - timedelta(hours=1)
                else:
                    break
                
                time.sleep(0.1)  # Rate limiting
                
            except KeyboardInterrupt:
                self._cancelled = True
                if request_count > 0:
                    sys.stdout.write(f"\r    {ActivityEmoji.WARNING} Interrupted fetching {symbol} funding                    \n")
                    sys.stdout.flush()
                break
            except Exception as e:
                self.logger.warning(f"Funding API error for {symbol}: {e}")
                break
        
        # Clear progress line
        if request_count > 0 and not self._cancelled:
            sys.stdout.write(f"\r    {ActivityEmoji.SUCCESS} {symbol} funding: Fetched {request_count} batches ({len(all_records):,} records)                    \n")
            sys.stdout.flush()
        elif self._cancelled and request_count > 0:
            sys.stdout.write(f"\r    {ActivityEmoji.WARNING} Cancelled fetching {symbol} funding                    \n")
            sys.stdout.flush()
        
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
        self.conn.execute(f"""
            INSERT OR REPLACE INTO {self.table_funding} (symbol, timestamp, funding_rate)
            SELECT symbol, timestamp, funding_rate FROM df
        """)
        
        # Update metadata
        self._update_funding_metadata(symbol)
    
    def _update_funding_metadata(self, symbol: str):
        """Update funding metadata for a symbol."""
        stats = self.conn.execute(f"""
            SELECT 
                MIN(timestamp) as first_ts,
                MAX(timestamp) as last_ts,
                COUNT(*) as count
            FROM {self.table_funding}
            WHERE symbol = ?
        """, [symbol]).fetchone()
        
        self.conn.execute(f"""
            INSERT OR REPLACE INTO {self.table_funding_metadata} 
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
        
        query = f"""
            SELECT timestamp, funding_rate
            FROM {self.table_funding}
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
            # Check for cancellation
            if self._cancelled:
                self.logger.info("Open interest sync cancelled by user")
                break
            
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
                    
            except KeyboardInterrupt:
                self._cancelled = True
                self.logger.info("Open interest sync interrupted by user")
                if spinner:
                    spinner.stop(f"{symbol} OI: cancelled", success=False)
                elif progress_callback:
                    progress_callback(symbol, f"{ActivityEmoji.WARNING} cancelled")
                break
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
        existing = self.conn.execute(f"""
            SELECT MAX(timestamp) as last_ts
            FROM {self.table_oi}
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
        request_count = 0
        
        # Bybit OI API returns max 200 records per request
        while current_end > fetch_start:
            # Check for cancellation
            if self._cancelled:
                break
            
            try:
                # Show progress
                dots = ActivityEmoji.DOTS[request_count % len(ActivityEmoji.DOTS)]
                records_count = request_count * 200
                sys.stdout.write(f"\r    {ActivityEmoji.DOWNLOAD} {dots} {symbol} OI ({interval}): Fetching records... ({records_count}+)   ")
                sys.stdout.flush()
                
                # Pass endTime to paginate backwards through history
                records = self.client.get_open_interest(
                    symbol=symbol,
                    interval=interval,
                    limit=200,
                    end_time=int(current_end.timestamp() * 1000),
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
                
                request_count += 1
                
                # Move window back
                if records:
                    earliest_ts = min(int(r.get("timestamp", 0)) for r in records)
                    current_end = datetime.fromtimestamp(earliest_ts / 1000) - timedelta(hours=1)
                else:
                    break
                
                time.sleep(0.1)  # Rate limiting
                
            except KeyboardInterrupt:
                self._cancelled = True
                if request_count > 0:
                    sys.stdout.write(f"\r    {ActivityEmoji.WARNING} Interrupted fetching {symbol} OI                    \n")
                    sys.stdout.flush()
                break
            except Exception as e:
                self.logger.warning(f"OI API error for {symbol}: {e}")
                break
        
        # Clear progress line
        if request_count > 0 and not self._cancelled:
            sys.stdout.write(f"\r    {ActivityEmoji.SUCCESS} {symbol} OI ({interval}): Fetched {request_count} batches ({len(all_records):,} records)                    \n")
            sys.stdout.flush()
        elif self._cancelled and request_count > 0:
            sys.stdout.write(f"\r    {ActivityEmoji.WARNING} Cancelled fetching {symbol} OI                    \n")
            sys.stdout.flush()
        
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
        self.conn.execute(f"""
            INSERT OR REPLACE INTO {self.table_oi} (symbol, timestamp, open_interest)
            SELECT symbol, timestamp, open_interest FROM df
        """)
        
        # Update metadata
        self._update_oi_metadata(symbol)
    
    def _update_oi_metadata(self, symbol: str):
        """Update open interest metadata for a symbol."""
        stats = self.conn.execute(f"""
            SELECT 
                MIN(timestamp) as first_ts,
                MAX(timestamp) as last_ts,
                COUNT(*) as count
            FROM {self.table_oi}
            WHERE symbol = ?
        """, [symbol]).fetchone()
        
        self.conn.execute(f"""
            INSERT OR REPLACE INTO {self.table_oi_metadata} 
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
        
        query = f"""
            SELECT timestamp, open_interest
            FROM {self.table_oi}
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
        """Detect gaps in data for a symbol/timeframe."""
        from . import historical_maintenance
        return historical_maintenance.detect_gaps(self, symbol, timeframe)
    
    def fill_gaps(
        self,
        symbol: str = None,
        timeframe: str = None,
        progress_callback: Callable = None,
    ) -> Dict[str, int]:
        """Detect and fill gaps in data."""
        from . import historical_maintenance
        return historical_maintenance.fill_gaps(self, symbol, timeframe, progress_callback)
    
    def heal(
        self,
        symbol: str = None,
        fix_issues: bool = True,
        fill_gaps_after: bool = True,
    ) -> Dict[str, Any]:
        """Comprehensive data integrity check and repair."""
        from . import historical_maintenance
        return historical_maintenance.heal_comprehensive(
            self, symbol, fix_issues, fill_gaps_after
        )
    
    # ==================== QUERY METHODS ====================
    
    def get_ohlcv(
        self,
        symbol: str,
        tf: str,
        period: str = None,
        start: datetime = None,
        end: datetime = None,
    ) -> pd.DataFrame:
        """
        Get OHLCV data as DataFrame.
        
        Args:
            symbol: Trading symbol
            tf: Candle timeframe
            period: Period string ("1M", "2W", etc.) - alternative to start/end
            start: Start datetime
            end: End datetime
        
        Returns:
            DataFrame with timestamp, open, high, low, close, volume
        """
        # Normalize symbol to uppercase for consistency
        symbol = symbol.upper()
        
        query = f"""
            SELECT timestamp, open, high, low, close, volume
            FROM {self.table_ohlcv}
            WHERE symbol = ? AND timeframe = ?
        """
        params = [symbol, tf]
        
        if period:
            start = datetime.now() - self.parse_period(period)
        
        # DuckDB stores naive timestamps (UTC assumed)
        # Strip timezone info to avoid conversion issues
        if start:
            query += " AND timestamp >= ?"
            start_param = start.replace(tzinfo=None) if start.tzinfo else start
            params.append(start_param)
        
        if end:
            query += " AND timestamp <= ?"
            end_param = end.replace(tzinfo=None) if end.tzinfo else end
            params.append(end_param)
        
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
            rows = self.conn.execute(f"""
                SELECT * FROM {self.table_sync_metadata} WHERE symbol = ?
            """, [symbol]).fetchall()
        else:
            rows = self.conn.execute(f"""
                SELECT * FROM {self.table_sync_metadata} ORDER BY symbol, timeframe
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
        rows = self.conn.execute(f"""
            SELECT DISTINCT symbol FROM {self.table_sync_metadata} ORDER BY symbol
        """).fetchall()
        return [r[0] for r in rows]
    
    def get_database_stats(self) -> Dict:
        """Get overall database statistics with per-symbol and per-timeframe breakdowns."""
        # OHLCV stats (aggregate)
        ohlcv_stats = self.conn.execute(f"""
            SELECT 
                COUNT(DISTINCT symbol) as symbols,
                COUNT(DISTINCT symbol || '_' || timeframe) as combinations,
                COUNT(*) as total_candles
            FROM {self.table_ohlcv}
        """).fetchone()
        
        # OHLCV per-symbol breakdown
        ohlcv_by_symbol = self.conn.execute(f"""
            SELECT 
                symbol,
                timeframe,
                COUNT(*) as candles,
                MIN(timestamp) as earliest,
                MAX(timestamp) as latest
            FROM {self.table_ohlcv}
            GROUP BY symbol, timeframe
            ORDER BY symbol, timeframe
        """).fetchall()
        
        # Organize OHLCV by symbol
        ohlcv_symbols = {}
        for row in ohlcv_by_symbol:
            symbol, timeframe, candles, earliest, latest = row
            if symbol not in ohlcv_symbols:
                ohlcv_symbols[symbol] = {
                    "timeframes": [],
                    "total_candles": 0,
                    "earliest_dt": None,
                    "latest_dt": None,
                }
            ohlcv_symbols[symbol]["timeframes"].append({
                "timeframe": timeframe,
                "candles": candles,
                "earliest": earliest.isoformat() if earliest else None,
                "latest": latest.isoformat() if latest else None,
            })
            ohlcv_symbols[symbol]["total_candles"] += candles
            # Track earliest/latest as datetime objects for comparison
            if earliest:
                if ohlcv_symbols[symbol]["earliest_dt"] is None or earliest < ohlcv_symbols[symbol]["earliest_dt"]:
                    ohlcv_symbols[symbol]["earliest_dt"] = earliest
            if latest:
                if ohlcv_symbols[symbol]["latest_dt"] is None or latest > ohlcv_symbols[symbol]["latest_dt"]:
                    ohlcv_symbols[symbol]["latest_dt"] = latest
        
        # Convert datetime objects to ISO strings for final output
        for symbol_data in ohlcv_symbols.values():
            if symbol_data["earliest_dt"]:
                symbol_data["earliest"] = symbol_data["earliest_dt"].isoformat()
            else:
                symbol_data["earliest"] = None
            if symbol_data["latest_dt"]:
                symbol_data["latest"] = symbol_data["latest_dt"].isoformat()
            else:
                symbol_data["latest"] = None
            # Remove temporary datetime fields
            del symbol_data["earliest_dt"]
            del symbol_data["latest_dt"]
        
        # Funding stats (aggregate)
        funding_stats = self.conn.execute(f"""
            SELECT 
                COUNT(DISTINCT symbol) as symbols,
                COUNT(*) as total_records
            FROM {self.table_funding}
        """).fetchone()
        
        # Funding per-symbol breakdown
        funding_by_symbol = self.conn.execute(f"""
            SELECT 
                symbol,
                COUNT(*) as records,
                MIN(timestamp) as earliest,
                MAX(timestamp) as latest
            FROM {self.table_funding}
            GROUP BY symbol
            ORDER BY symbol
        """).fetchall()
        
        funding_symbols = {
            row[0]: {
                "records": row[1],
                "earliest": row[2].isoformat() if row[2] else None,
                "latest": row[3].isoformat() if row[3] else None,
            }
            for row in funding_by_symbol
        }
        
        # Open interest stats (aggregate)
        oi_stats = self.conn.execute(f"""
            SELECT 
                COUNT(DISTINCT symbol) as symbols,
                COUNT(*) as total_records
            FROM {self.table_oi}
        """).fetchone()
        
        # Open interest per-symbol breakdown
        oi_by_symbol = self.conn.execute(f"""
            SELECT 
                symbol,
                COUNT(*) as records,
                MIN(timestamp) as earliest,
                MAX(timestamp) as latest
            FROM {self.table_oi}
            GROUP BY symbol
            ORDER BY symbol
        """).fetchall()
        
        oi_symbols = {
            row[0]: {
                "records": row[1],
                "earliest": row[2].isoformat() if row[2] else None,
                "latest": row[3].isoformat() if row[3] else None,
            }
            for row in oi_by_symbol
        }
        
        file_size = self.db_path.stat().st_size if self.db_path.exists() else 0
        
        return {
            "db_path": str(self.db_path),
            "env": self.env,
            "file_size_mb": round(file_size / (1024 * 1024), 2),
            "ohlcv": {
                "symbols": ohlcv_stats[0],
                "symbol_timeframe_combinations": ohlcv_stats[1],
                "total_candles": ohlcv_stats[2],
                "by_symbol": ohlcv_symbols,
            },
            "funding_rates": {
                "symbols": funding_stats[0],
                "total_records": funding_stats[1],
                "by_symbol": funding_symbols,
            },
            "open_interest": {
                "symbols": oi_stats[0],
                "total_records": oi_stats[1],
                "by_symbol": oi_symbols,
            },
            # Legacy fields for backwards compatibility
            "symbols": ohlcv_stats[0],
            "symbol_timeframe_combinations": ohlcv_stats[1],
            "total_candles": ohlcv_stats[2],
        }
    
    # ==================== MAINTENANCE ====================
    
    def delete_symbol(self, symbol: str) -> int:
        """Delete all data for a symbol."""
        from . import historical_maintenance
        return historical_maintenance.delete_symbol(self, symbol)
    
    def delete_symbol_timeframe(self, symbol: str, timeframe: str) -> int:
        """Delete data for a specific symbol/timeframe combination."""
        from . import historical_maintenance
        return historical_maintenance.delete_symbol_timeframe(self, symbol, timeframe)
    
    def cleanup_empty_symbols(self) -> List[str]:
        """Remove symbols that have metadata but no actual data."""
        from . import historical_maintenance
        return historical_maintenance.cleanup_empty_symbols(self)
    
    def get_symbol_summary(self) -> List[Dict]:
        """
        Get summary of all symbols with their data status.
        Useful for displaying in delete menu.
        
        Returns:
            List of dicts with symbol info
        """
        rows = self.conn.execute(f"""
            SELECT 
                symbol,
                COUNT(DISTINCT timeframe) as timeframes,
                SUM(candle_count) as total_candles,
                MIN(first_timestamp) as earliest,
                MAX(last_timestamp) as latest
            FROM {self.table_sync_metadata}
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
    
    # ==================== EXTREMES METADATA ====================
    
    def update_extremes(
        self,
        symbol: str,
        data_type: str,
        timeframe: Optional[str] = None,
        earliest_ts: Optional[datetime] = None,
        latest_ts: Optional[datetime] = None,
        row_count: int = 0,
        gap_count: int = 0,
        launch_time: Optional[datetime] = None,
        source: str = "full_from_launch",
    ):
        """
        Update extremes metadata for a symbol/data_type/tf.
        
        Args:
            symbol: Trading symbol
            data_type: "ohlcv", "funding", or "open_interest"
            timeframe: Timeframe (for OHLCV) or None
            earliest_ts: Earliest timestamp in DB
            latest_ts: Latest timestamp in DB
            row_count: Number of rows
            gap_count: Gap count after healing
            launch_time: Resolved instrument launchTime
            source: Source of the data (e.g., "full_from_launch", "sync_range")
        """
        symbol = symbol.upper()
        tf_value = timeframe if timeframe else "N/A"
        
        self.conn.execute(f"""
            INSERT OR REPLACE INTO {self.table_extremes} 
            (symbol, data_type, timeframe, earliest_ts, latest_ts, row_count, 
             gap_count_after_heal, resolved_launch_time, source, last_updated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            symbol, data_type, tf_value, earliest_ts, latest_ts,
            row_count, gap_count, launch_time, source, datetime.now()
        ])
    
    def get_extremes(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        """
        Get extremes metadata for symbol(s).
        
        Args:
            symbol: Specific symbol or None for all
            
        Returns:
            Dict with extremes per symbol/data_type/tf
        """
        if symbol:
            symbol = symbol.upper()
            rows = self.conn.execute(f"""
                SELECT * FROM {self.table_extremes}
                WHERE symbol = ?
                ORDER BY data_type, timeframe
            """, [symbol]).fetchall()
        else:
            rows = self.conn.execute(f"""
                SELECT * FROM {self.table_extremes}
                ORDER BY symbol, data_type, timeframe
            """).fetchall()
        
        result = {}
        for row in rows:
            sym, dtype, tf, earliest, latest, count, gaps, launch, src, updated = row
            if sym not in result:
                result[sym] = {}
            if dtype not in result[sym]:
                result[sym][dtype] = {}
            
            result[sym][dtype][tf] = {
                "earliest_ts": earliest.isoformat() if earliest else None,
                "latest_ts": latest.isoformat() if latest else None,
                "row_count": count,
                "gap_count_after_heal": gaps,
                "resolved_launch_time": launch.isoformat() if launch else None,
                "source": src,
                "last_updated": updated.isoformat() if updated else None,
            }
        
        return result
    
    def close(self):
        """Close database connection."""
        self.conn.close()


# ==============================================================================
# Env-aware Singleton Instances
# ==============================================================================

# Cached instances per environment
_store_live: Optional[HistoricalDataStore] = None
_store_demo: Optional[HistoricalDataStore] = None


def get_historical_store(env: DataEnv = DEFAULT_DATA_ENV) -> HistoricalDataStore:
    """
    Get or create the HistoricalDataStore instance for a given environment.
    
    Args:
        env: Data environment ("live" or "demo"). Defaults to "live".
        
    Returns:
        HistoricalDataStore instance for the specified environment.
    """
    global _store_live, _store_demo
    
    env = validate_data_env(env)
    
    if env == "live":
        if _store_live is None:
            _store_live = HistoricalDataStore(env="live")
        return _store_live
    else:
        if _store_demo is None:
            _store_demo = HistoricalDataStore(env="demo")
        return _store_demo


def get_live_historical_store() -> HistoricalDataStore:
    """Get the live environment HistoricalDataStore (convenience function)."""
    return get_historical_store(env="live")


def get_demo_historical_store() -> HistoricalDataStore:
    """Get the demo environment HistoricalDataStore (convenience function)."""
    return get_historical_store(env="demo")


# ==============================================================================
# Module-level env-aware API (future-proof interface)
# ==============================================================================
# These functions provide a stable API surface that can later be swapped
# to use MongoDB or another backend without changing callers.

def get_ohlcv(
    symbol: str,
    tf: str,
    period: str = None,
    start: datetime = None,
    end: datetime = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> pd.DataFrame:
    """
    Get OHLCV data for a symbol/tf.
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT")
        tf: Candle timeframe (e.g., "15m", "1h")
        period: Period string ("1M", "2W", etc.) - alternative to start/end
        start: Start datetime
        end: End datetime
        env: Data environment ("live" or "demo")
        
    Returns:
        DataFrame with timestamp, open, high, low, close, volume
    """
    store = get_historical_store(env)
    return store.get_ohlcv(symbol, tf, period=period, start=start, end=end)


def get_latest_ohlcv(
    symbol: str,
    tf: str,
    limit: int = 100,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> pd.DataFrame:
    """
    Get the most recent OHLCV candles for a symbol/tf.
    
    Args:
        symbol: Trading symbol
        tf: Candle timeframe
        limit: Number of candles to return
        env: Data environment
        
    Returns:
        DataFrame with the most recent candles
    """
    store = get_historical_store(env)
    # Compute approximate start time based on limit and tf
    tf_minutes = TF_MINUTES.get(tf, 15)
    start = datetime.now() - timedelta(minutes=tf_minutes * limit * 2)  # Extra buffer
    df = store.get_ohlcv(symbol, tf, start=start)
    return df.tail(limit) if len(df) > limit else df


def append_ohlcv(
    symbol: str,
    tf: str,
    df: pd.DataFrame,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> None:
    """
    Append OHLCV data for a symbol/tf.
    
    Args:
        symbol: Trading symbol
        tf: Candle timeframe
        df: DataFrame with OHLCV data (columns: timestamp, open, high, low, close, volume)
        env: Data environment
    """
    store = get_historical_store(env)
    store._store_dataframe(symbol, tf, df)
    store._update_metadata(symbol, timeframe)


def get_funding(
    symbol: str,
    period: str = None,
    start: datetime = None,
    end: datetime = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> pd.DataFrame:
    """
    Get funding rate data for a symbol.
    
    Args:
        symbol: Trading symbol
        period: Period string
        start: Start datetime
        end: End datetime
        env: Data environment
        
    Returns:
        DataFrame with timestamp, funding_rate
    """
    store = get_historical_store(env)
    return store.get_funding(symbol, period=period, start=start, end=end)


def get_open_interest(
    symbol: str,
    period: str = None,
    start: datetime = None,
    end: datetime = None,
    env: DataEnv = DEFAULT_DATA_ENV,
) -> pd.DataFrame:
    """
    Get open interest data for a symbol.
    
    Args:
        symbol: Trading symbol
        period: Period string
        start: Start datetime
        end: End datetime
        env: Data environment
        
    Returns:
        DataFrame with timestamp, open_interest
    """
    store = get_historical_store(env)
    return store.get_open_interest(symbol, period=period, start=start, end=end)


def get_symbol_timeframe_ranges(
    env: DataEnv = DEFAULT_DATA_ENV,
) -> Dict[str, Dict]:
    """
    Get available data ranges for all symbol/timeframe combinations.
    
    Args:
        env: Data environment
        
    Returns:
        Dict mapping "SYMBOL_TF" to range info
    """
    store = get_historical_store(env)
    return store.status()

