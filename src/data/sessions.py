"""
Session abstractions for Live and Demo trading environments.

This module provides isolated "bubbles" for demo and live trading sessions,
each with its own data environment, state, and risk settings.

Architecture:
- SessionConfig: Base configuration for all sessions
- DemoSession: Isolated demo trading environment (env="demo", fake money)
- LiveSession: Live trading environment (env="live", real money)

Each session:
- Has its own data environment (live or demo historical data)
- Manages warm-up by loading history into bar ring buffers
- Connects to appropriate WebSocket streams
- Logs with session_id and env for clear isolation

Usage:
    from src.data.sessions import DemoSession, LiveSession

    # Create a demo session
    session = DemoSession(
        session_id="demo_1",
        symbols=["BTCUSDT"],
        timeframes=["15m", "1h", "4h"],
        warmup_bars=200,
    )

    # Initialize and warm up
    await session.initialize()
    await session.warm_up()

    # Get bar data for strategy
    df_15m = session.get_bar_buffer("BTCUSDT", "15m")

    # Shutdown
    await session.shutdown()
"""

from dataclasses import dataclass, field
from datetime import datetime
import time
from typing import Any

from ..config.config import get_config
from ..config.constants import DataEnv, DEFAULT_DATA_ENV, validate_data_env
from ..utils.logger import get_logger
from .realtime_state import get_realtime_state, RealtimeState
from .historical_data_store import get_historical_store, get_latest_ohlcv


@dataclass
class SessionConfig:
    """
    Base configuration for a trading session.

    Attributes:
        session_id: Unique identifier for this session
        env: Data environment ("live" or "demo")
        symbols: List of symbols to trade
        timeframes: List of timeframes to warm up (e.g., ["15m", "1h", "4h"])
        warmup_candles: Number of candles to warm up per timeframe
        system_id: Optional strategy/system identifier
        risk_settings: Optional dict of risk overrides for this session
    """
    session_id: str
    env: DataEnv
    symbols: list[str]
    timeframes: list[str] = field(default_factory=lambda: ["15m", "1h", "4h"])
    warmup_candles: int = 200
    system_id: str | None = None
    risk_settings: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        """Validate configuration after initialization."""
        self.env = validate_data_env(self.env)
        self.symbols = [s.upper() for s in self.symbols]
        
        if not self.symbols:
            raise ValueError("At least one symbol is required")
        if not self.timeframes:
            raise ValueError("At least one timeframe is required")
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "session_id": self.session_id,
            "env": self.env,
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "warmup_candles": self.warmup_candles,
            "system_id": self.system_id,
            "risk_settings": self.risk_settings,
            "created_at": self.created_at.isoformat(),
        }


class BaseSession:
    """
    Base class for trading sessions.

    Provides common functionality for both demo and live sessions:
    - Configuration management
    - State access
    - Bar buffer initialization
    - Warm-up from historical data
    - Logging with session context
    """

    def __init__(self, config: SessionConfig):
        """
        Initialize session.

        Args:
            config: Session configuration
        """
        self.config = config
        self.app_config = get_config()
        self.logger = get_logger()

        # State (shared across sessions, but bar buffers are env-scoped)
        self.state: RealtimeState = get_realtime_state()
        
        # Session state
        self._initialized = False
        self._warmed_up = False
        self._running = False
        self._started_at: float | None = None
        self._stopped_at: float | None = None
        
        self._log_info(f"Session created: {self.config.to_dict()}")
    
    @property
    def env(self) -> DataEnv:
        """Get data environment."""
        return self.config.env
    
    @property
    def session_id(self) -> str:
        """Get session ID."""
        return self.config.session_id
    
    @property
    def symbols(self) -> list[str]:
        """Get configured symbols."""
        return self.config.symbols

    @property
    def timeframes(self) -> list[str]:
        """Get configured timeframes."""
        return self.config.timeframes
    
    @property
    def is_initialized(self) -> bool:
        """Check if session is initialized."""
        return self._initialized
    
    @property
    def is_warmed_up(self) -> bool:
        """Check if session is warmed up."""
        return self._warmed_up
    
    @property
    def is_running(self) -> bool:
        """Check if session is running."""
        return self._running
    
    # ==========================================================================
    # Logging with Session Context
    # ==========================================================================
    
    def _log_info(self, message: str):
        """Log info with session context."""
        self.logger.info(f"[{self.env.upper()}][{self.session_id}] {message}")
    
    def _log_warning(self, message: str):
        """Log warning with session context."""
        self.logger.warning(f"[{self.env.upper()}][{self.session_id}] {message}")
    
    def _log_error(self, message: str):
        """Log error with session context."""
        self.logger.error(f"[{self.env.upper()}][{self.session_id}] {message}")
    
    def _log_debug(self, message: str):
        """Log debug with session context."""
        self.logger.debug(f"[{self.env.upper()}][{self.session_id}] {message}")
    
    # ==========================================================================
    # Initialization and Warm-up
    # ==========================================================================
    
    def initialize(self) -> bool:
        """
        Initialize the session.
        
        This prepares the session for operation but does not start trading.
        Override in subclasses for additional initialization.
        
        Returns:
            True if initialization succeeded
        """
        if self._initialized:
            self._log_warning("Session already initialized")
            return True
        
        try:
            self._log_info("Initializing session...")
            
            # Validate that we can access the historical store
            store = get_historical_store(env=self.env)
            self._log_debug(f"Historical store: {store.db_path}")
            
            self._initialized = True
            self._log_info("Session initialized successfully")
            return True
            
        except Exception as e:
            self._log_error(f"Failed to initialize session: {e}")
            return False
    
    def warm_up(self) -> dict[str, int]:
        """
        Warm up bar buffers with historical data.

        Loads historical bars into ring buffers for each symbol/timeframe
        combination. This provides lookback data for strategy calculations.

        Returns:
            Dict mapping "SYMBOL_TF" to number of bars loaded
        """
        if not self._initialized:
            raise RuntimeError("Session must be initialized before warm-up")

        if self._warmed_up:
            self._log_warning("Session already warmed up")
            return {}

        self._log_info(
            f"Warming up bar buffers: {len(self.symbols)} symbols x "
            f"{len(self.timeframes)} timeframes x {self.config.warmup_candles} bars"
        )
        
        results = {}
        
        for symbol in self.symbols:
            for tf in self.timeframes:
                key = f"{symbol}_{tf}"
                try:
                    # Get historical data
                    df = get_latest_ohlcv(
                        symbol=symbol,
                        timeframe=tf,
                        limit=self.config.warmup_candles,
                        env=self.env,
                    )
                    
                    if df.empty:
                        self._log_warning(f"No historical data for {key}")
                        results[key] = 0
                        continue
                    
                    # Initialize bar buffer
                    count = self.state.init_bar_buffer(
                        env=self.env,
                        symbol=symbol,
                        timeframe=tf,
                        bars_df=df,
                    )

                    results[key] = count
                    self._log_debug(f"Warmed up {key}: {count} bars")
                    
                except Exception as e:
                    self._log_error(f"Failed to warm up {key}: {e}")
                    results[key] = 0
        
        total = sum(results.values())
        self._warmed_up = True
        self._log_info(f"Warm-up complete: {total} total bars loaded")

        return results

    # ==========================================================================
    # Bar Buffer Access
    # ==========================================================================

    def get_bar_buffer(self, symbol: str, timeframe: str, limit: int | None = None):
        """
        Get bar buffer as a list of bars.

        Args:
            symbol: Trading symbol
            timeframe: Bar timeframe
            limit: Maximum bars to return (None = all)

        Returns:
            List of BarRecord objects
        """
        return self.state.get_bar_buffer(
            env=self.env,
            symbol=symbol.upper(),
            timeframe=timeframe,
            limit=limit,
        )

    def get_bar_buffer_df(self, symbol: str, timeframe: str, limit: int | None = None):
        """
        Get bar buffer as a pandas DataFrame.

        Args:
            symbol: Trading symbol
            timeframe: Bar timeframe
            limit: Maximum rows to return

        Returns:
            DataFrame with OHLCV columns
        """
        return self.state.get_bar_buffer_as_df(
            env=self.env,
            symbol=symbol.upper(),
            timeframe=timeframe,
            limit=limit,
        )
    
    # ==========================================================================
    # Lifecycle
    # ==========================================================================
    
    def start(self) -> bool:
        """
        Start the session.
        
        Override in subclasses to add WebSocket connections, etc.
        
        Returns:
            True if started successfully
        """
        if not self._initialized:
            if not self.initialize():
                return False
        
        if not self._warmed_up:
            self.warm_up()
        
        self._running = True
        self._started_at = time.time()
        self._log_info("Session started")
        return True
    
    def stop(self):
        """
        Stop the session.
        
        Override in subclasses to clean up WebSocket connections, etc.
        """
        self._running = False
        self._stopped_at = time.time()
        
        runtime = (self._stopped_at - self._started_at) if self._started_at else 0
        self._log_info(f"Session stopped (runtime: {runtime:.1f}s)")
    
    def get_status(self) -> dict[str, Any]:
        """Get session status."""
        return {
            "session_id": self.session_id,
            "env": self.env,
            "initialized": self._initialized,
            "warmed_up": self._warmed_up,
            "running": self._running,
            "started_at": self._started_at,
            "stopped_at": self._stopped_at,
            "symbols": self.symbols,
            "timeframes": self.timeframes,
            "bar_buffer_stats": self.state.get_bar_buffer_stats(env=self.env),
        }


class DemoSession(BaseSession):
    """
    Demo trading session.

    Uses env="demo" for:
    - Historical data from demo DuckDB file
    - Bar buffers scoped to demo environment
    - All logs tagged with [DEMO]

    Demo sessions use fake money and are isolated from live data.
    """

    def __init__(
        self,
        session_id: str,
        symbols: list[str],
        timeframes: list[str] | None = None,
        warmup_candles: int = 200,
        system_id: str | None = None,
        risk_settings: dict[str, Any] | None = None,
    ):
        """
        Create a demo session.
        
        Args:
            session_id: Unique session identifier
            symbols: Symbols to trade
            timeframes: Timeframes to warm up
            warmup_candles: Number of candles per timeframe
            system_id: Optional strategy identifier
            risk_settings: Optional risk overrides
        """
        config = SessionConfig(
            session_id=session_id,
            env="demo",
            symbols=symbols,
            timeframes=timeframes or ["15m", "1h", "4h"],
            warmup_candles=warmup_candles,
            system_id=system_id,
            risk_settings=risk_settings or {},
        )
        super().__init__(config)
    
    def initialize(self) -> bool:
        """Initialize demo session with demo-specific setup."""
        if not super().initialize():
            return False
        
        # Demo-specific initialization
        # (e.g., connect to demo WebSocket, verify demo API keys)
        self._log_info("Demo session ready (fake money, isolated data)")
        return True


class LiveSession(BaseSession):
    """
    Live trading session.

    Uses env="live" for:
    - Historical data from canonical live DuckDB file
    - Bar buffers scoped to live environment
    - All logs tagged with [LIVE]

    Live sessions use real money and should have stricter risk controls.
    """

    def __init__(
        self,
        session_id: str,
        symbols: list[str],
        timeframes: list[str] | None = None,
        warmup_candles: int = 200,
        system_id: str | None = None,
        risk_settings: dict[str, Any] | None = None,
    ):
        """
        Create a live session.
        
        Args:
            session_id: Unique session identifier
            symbols: Symbols to trade
            timeframes: Timeframes to warm up
            warmup_candles: Number of candles per timeframe
            system_id: Optional strategy identifier
            risk_settings: Optional risk overrides (should be stricter than demo)
        """
        config = SessionConfig(
            session_id=session_id,
            env="live",
            symbols=symbols,
            timeframes=timeframes or ["15m", "1h", "4h"],
            warmup_candles=warmup_candles,
            system_id=system_id,
            risk_settings=risk_settings or {},
        )
        super().__init__(config)
    
    def initialize(self) -> bool:
        """Initialize live session with live-specific setup."""
        if not super().initialize():
            return False
        
        # Live-specific initialization
        # (e.g., verify live API keys, check risk settings)
        self._log_info("Live session ready (REAL MONEY, use caution)")
        return True


# ==============================================================================
# Factory Functions
# ==============================================================================

def create_demo_session(
    symbols: list[str],
    timeframes: list[str] | None = None,
    warmup_candles: int = 200,
    system_id: str | None = None,
) -> DemoSession:
    """
    Factory function to create a demo session with auto-generated ID.
    
    Args:
        symbols: Symbols to trade
        timeframes: Timeframes to warm up
        warmup_candles: Candles per timeframe
        system_id: Optional strategy ID
        
    Returns:
        DemoSession instance
    """
    session_id = f"demo_{int(time.time() * 1000)}"
    return DemoSession(
        session_id=session_id,
        symbols=symbols,
        timeframes=timeframes,
        warmup_candles=warmup_candles,
        system_id=system_id,
    )


def create_live_session(
    symbols: list[str],
    timeframes: list[str] | None = None,
    warmup_candles: int = 200,
    system_id: str | None = None,
    risk_settings: dict[str, Any] | None = None,
) -> LiveSession:
    """
    Factory function to create a live session with auto-generated ID.
    
    Args:
        symbols: Symbols to trade
        timeframes: Timeframes to warm up
        warmup_candles: Candles per timeframe
        system_id: Optional strategy ID
        risk_settings: Risk overrides (should be stricter)
        
    Returns:
        LiveSession instance
    """
    session_id = f"live_{int(time.time() * 1000)}"
    return LiveSession(
        session_id=session_id,
        symbols=symbols,
        timeframes=timeframes,
        warmup_candles=warmup_candles,
        system_id=system_id,
        risk_settings=risk_settings,
    )

