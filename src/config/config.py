"""
Configuration management for the trading bot.
Loads settings from environment variables with sensible defaults.
"""

import os
from dataclasses import dataclass, field
from typing import List, Optional
from pathlib import Path
from dotenv import load_dotenv

# Note: Symbols should always be passed as explicit parameters by users/agents
# The config only stores user-configured symbols from environment variables


# Trading modes - strict mapping to API environments
# PAPER must use DEMO API, REAL must use LIVE API
class TradingMode:
    PAPER = "paper"  # Demo trading on Bybit demo account (fake money, real API orders)
    REAL = "real"    # Live trading on Bybit live account (real money, real API orders)


@dataclass
class BybitConfig:
    """
    Bybit API configuration with separate DEMO and LIVE API keys.
    
    Bybit provides two separate environments:
    
    DEMO (FAKE MONEY):
        - API endpoint: api-demo.bybit.com
        - WebSocket: stream-demo.bybit.com
        - Purpose: Strategy development, testing, agent experimentation
        - Risk: Zero - no real capital at risk
    
    LIVE (REAL MONEY):
        - API endpoint: api.bybit.com
        - WebSocket: stream.bybit.com
        - Purpose: Production trading with validated strategies
        - Risk: Real capital - use with strict risk controls!
    
    Each environment requires its own API keys.
    You can also have separate read-only data keys (120 RPS) vs
    trading keys (50 RPS) for better rate limit management.
    """
    # DEMO API keys (api-demo.bybit.com) - FAKE MONEY
    demo_api_key: str = ""
    demo_api_secret: str = ""
    demo_data_api_key: str = ""
    demo_data_api_secret: str = ""
    
    # LIVE API keys (api.bybit.com) - REAL MONEY!
    live_api_key: str = ""
    live_api_secret: str = ""
    live_data_api_key: str = ""
    live_data_api_secret: str = ""
    
    # DEPRECATED: Legacy/generic keys - NOT used in strict mode
    # These fields exist only for backward compatibility inspection.
    # All credential behavior uses only the canonical 4 keys above.
    api_key: str = ""       # DEPRECATED: Use demo_api_key or live_api_key
    api_secret: str = ""    # DEPRECATED: Use demo_api_secret or live_api_secret
    data_api_key: str = ""  # DEPRECATED: Use live_data_api_key
    data_api_secret: str = ""  # DEPRECATED: Use live_data_api_secret
    
    # Endpoints
    demo_base_url: str = "https://api-demo.bybit.com"   # DEMO (FAKE MONEY)
    live_base_url: str = "https://api.bybit.com"        # LIVE (REAL MONEY)
    
    # Environment toggle: True = DEMO (safe), False = LIVE (real money!)
    use_demo: bool = True
    
    def get_credentials(self) -> tuple:
        """
        Get trading API key and secret for current mode (STRICT - no fallbacks).
        
        CANONICAL KEY CONTRACT:
        - DEMO mode (use_demo=True): Returns ONLY demo_api_key / demo_api_secret
        - LIVE mode (use_demo=False): Returns ONLY live_api_key / live_api_secret
        
        No fallback to generic keys. If mode-specific keys are not set,
        validation will fail and block startup.
        
        Returns:
            Tuple of (api_key, api_secret) for current trading mode
        """
        if self.use_demo:
            # STRICT: DEMO mode requires BYBIT_DEMO_API_KEY (no fallback)
            return self.demo_api_key, self.demo_api_secret
        else:
            # STRICT: LIVE mode requires BYBIT_LIVE_API_KEY (no fallback)
            return self.live_api_key, self.live_api_secret
    
    def get_data_credentials(self) -> tuple:
        """
        Get data API key and secret for current mode (STRICT - no fallbacks).
        
        Data keys have higher rate limits (120 RPS vs 50 RPS).
        
        CANONICAL KEY CONTRACT:
        - DEMO mode (use_demo=True): Returns ONLY demo_data_api_key / demo_data_api_secret
        - LIVE mode (use_demo=False): Returns ONLY live_data_api_key / live_data_api_secret
        
        NOTE: For historical/market data, use get_live_data_credentials() instead,
        which ALWAYS returns LIVE data keys regardless of trading mode.
        
        Returns:
            Tuple of (api_key, api_secret) for current mode's data operations
        """
        if self.use_demo:
            # STRICT: DEMO mode data uses BYBIT_DEMO_DATA_API_KEY (no fallback)
            return self.demo_data_api_key, self.demo_data_api_secret
        else:
            # STRICT: LIVE mode data uses BYBIT_LIVE_DATA_API_KEY (no fallback)
            return self.live_data_api_key, self.live_data_api_secret
    
    def get_base_url(self) -> str:
        """Get base URL based on demo/live mode."""
        return self.demo_base_url if self.use_demo else self.live_base_url
    
    def get_mode_name(self) -> str:
        """Get human-readable mode name (short)."""
        return "DEMO" if self.use_demo else "LIVE"
    
    def get_mode_display(self) -> str:
        """Get mode display string with risk warning."""
        if self.use_demo:
            return "DEMO (FAKE MONEY)"
        else:
            return "LIVE (REAL MONEY)"
    
    def get_mode_warning(self) -> str:
        """Get warning message for current mode."""
        if self.use_demo:
            return "Safe testing environment - no real capital at risk"
        else:
            return "⚠️  CAUTION: Real money at risk!"
    
    @property
    def is_live(self) -> bool:
        """Check if running in LIVE (real money) mode."""
        return not self.use_demo
    
    @property
    def is_demo(self) -> bool:
        """Check if running in DEMO (fake money) mode."""
        return self.use_demo
    
    def has_credentials(self) -> bool:
        """Check if valid credentials are configured for current mode."""
        key, secret = self.get_credentials()
        return bool(key and secret)
    
    def get_live_data_credentials(self) -> tuple:
        """
        Get LIVE data API credentials (STRICT - no fallbacks).
        
        Historical and market data should always use LIVE API for accuracy.
        The LIVE API has real market data that matches production trading.
        
        CANONICAL KEY CONTRACT:
        - This method ALWAYS returns live_data_api_key / live_data_api_secret
        - Regardless of use_demo setting (data is always from LIVE API)
        - No fallback to trading keys or generic keys
        
        If BYBIT_LIVE_DATA_API_KEY is not set, validation will fail
        and data operations will be blocked.
        
        Returns:
            Tuple of (api_key, api_secret) for LIVE data API
        """
        # STRICT: Data operations require BYBIT_LIVE_DATA_API_KEY (no fallback)
        return self.live_data_api_key, self.live_data_api_secret
    
    def get_demo_data_credentials(self) -> tuple:
        """
        Get DEMO data API credentials (STRICT - no fallbacks).
        
        DEMO data operations should use dedicated DEMO data keys.
        There is NO fallback to trading keys.
        
        Returns:
            Tuple of (api_key, api_secret) for DEMO data API
        """
        return self.demo_data_api_key, self.demo_data_api_secret
    
    def has_demo_data_credentials(self) -> bool:
        """
        Check if DEMO data API credentials are configured (STRICT).
        
        Returns True only if BYBIT_DEMO_DATA_API_KEY and SECRET are set.
        """
        key, secret = self.get_demo_data_credentials()
        return bool(key and secret)
    
    def has_live_data_credentials(self) -> bool:
        """
        Check if LIVE data API credentials are configured (STRICT).
        
        Returns True only if BYBIT_LIVE_DATA_API_KEY and SECRET are set.
        Data operations require these keys; no fallback is allowed.
        """
        # STRICT: Only check live_data_api_key (no fallback chain)
        return bool(self.live_data_api_key and self.live_data_api_secret)
    
    def get_api_environment_summary(self) -> dict:
        """
        Get a comprehensive summary of ALL 4 API environment legs.
        
        The system has 4 independent API legs:
        - Trading LIVE: Real money trading (api.bybit.com)
        - Trading DEMO: Fake money trading (api-demo.bybit.com)
        - Data LIVE: Canonical historical data for backtesting (api.bybit.com)
        - Data DEMO: Demo-only history for demo validation (api-demo.bybit.com)
        
        Returns:
            Dict with all 4 legs, current active trading mode, and safety info
        """
        # Current trading mode
        trading_mode = "DEMO" if self.use_demo else "LIVE"
        trading_url = self.demo_base_url if self.use_demo else self.live_base_url
        
        # Trading LIVE leg
        trade_live_key = bool(self.live_api_key and self.live_api_secret)
        trade_live_source = "BYBIT_LIVE_API_KEY" if self.live_api_key else "MISSING"
        
        # Trading DEMO leg
        trade_demo_key = bool(self.demo_api_key and self.demo_api_secret)
        trade_demo_source = "BYBIT_DEMO_API_KEY" if self.demo_api_key else "MISSING"
        
        # Data LIVE leg (canonical backtest data)
        data_live_key = bool(self.live_data_api_key and self.live_data_api_secret)
        data_live_source = "BYBIT_LIVE_DATA_API_KEY" if self.live_data_api_key else "MISSING"
        
        # Data DEMO leg (demo-only data)
        data_demo_key = bool(self.demo_data_api_key and self.demo_data_api_secret)
        data_demo_source = "BYBIT_DEMO_DATA_API_KEY" if self.demo_data_api_key else "MISSING"
        
        # WebSocket environment (matches trading mode)
        ws_mode = "DEMO" if self.use_demo else "LIVE"
        ws_public_url = "wss://stream-demo.bybit.com" if self.use_demo else "wss://stream.bybit.com"
        ws_private_url = ws_public_url
        
        # Safety validation
        messages = []
        if self.use_demo and not trade_demo_key:
            messages.append("DEMO trading mode selected but BYBIT_DEMO_API_KEY not set")
        if not self.use_demo and not trade_live_key:
            messages.append("LIVE trading mode selected but BYBIT_LIVE_API_KEY not set")
        
        return {
            # Current active trading mode
            "trading": {
                "mode": trading_mode,
                "base_url": trading_url,
                "key_configured": trade_demo_key if self.use_demo else trade_live_key,
                "key_source": trade_demo_source if self.use_demo else trade_live_source,
                "is_demo": self.use_demo,
                "is_live": not self.use_demo,
            },
            # Legacy "data" key for backwards compatibility (shows LIVE data only)
            "data": {
                "mode": "LIVE",
                "base_url": self.live_base_url,
                "key_configured": data_live_key,
                "key_source": data_live_source,
                "note": "Use data_live/data_demo for explicit env selection",
            },
            # All 4 legs explicitly
            "trade_live": {
                "mode": "LIVE",
                "base_url": self.live_base_url,
                "key_configured": trade_live_key,
                "key_source": trade_live_source,
            },
            "trade_demo": {
                "mode": "DEMO",
                "base_url": self.demo_base_url,
                "key_configured": trade_demo_key,
                "key_source": trade_demo_source,
            },
            "data_live": {
                "mode": "LIVE",
                "base_url": self.live_base_url,
                "key_configured": data_live_key,
                "key_source": data_live_source,
                "purpose": "Canonical backtest/research history",
            },
            "data_demo": {
                "mode": "DEMO",
                "base_url": self.demo_base_url,
                "key_configured": data_demo_key,
                "key_source": data_demo_source,
                "purpose": "Demo-only history for demo validation",
            },
            # WebSocket
            "websocket": {
                "mode": ws_mode,
                "public_url": ws_public_url,
                "private_url": ws_private_url,
            },
            # Safety validation
            "safety": {
                "mode_consistent": len(messages) == 0,
                "messages": messages,
            },
        }
    
    def get_api_environment_display(self) -> str:
        """
        Get a short human-readable API environment string for display.
        
        Returns:
            String like "Trading: DEMO | Keys: Trade[L:✓ D:✓] Data[L:✓ D:✗]"
        """
        env = self.get_api_environment_summary()
        trading = env["trading"]
        
        # Status indicators for all 4 legs
        tl = "✓" if env["trade_live"]["key_configured"] else "✗"
        td = "✓" if env["trade_demo"]["key_configured"] else "✗"
        dl = "✓" if env["data_live"]["key_configured"] else "✗"
        dd = "✓" if env["data_demo"]["key_configured"] else "✗"
        
        trading_str = f"Trading: {trading['mode']}"
        keys_str = f"Keys: Trade[L:{tl} D:{td}] Data[L:{dl} D:{dd}]"
        
        return f"{trading_str} | {keys_str}"


@dataclass
class RiskConfig:
    """Risk management configuration."""
    # Leverage limits
    max_leverage: int = 3
    default_leverage: int = 2
    
    # Position size limits (USD)
    max_position_size_usd: float = 50.0
    max_total_exposure_usd: float = 200.0
    
    # Loss limits
    max_daily_loss_usd: float = 20.0
    max_daily_loss_percent: float = 10.0  # % of account
    
    # Account protection
    min_balance_usd: float = 10.0
    
    # Per-trade risk
    max_risk_per_trade_percent: float = 2.0  # % of account per trade
    
    # Hard caps (cannot be overridden by config)
    HARD_MAX_LEVERAGE: int = 10
    HARD_MAX_POSITION_USD: float = 1000.0
    HARD_MIN_BALANCE: float = 5.0
    
    def __post_init__(self):
        """Enforce hard caps."""
        self.max_leverage = min(self.max_leverage, self.HARD_MAX_LEVERAGE)
        self.max_position_size_usd = min(self.max_position_size_usd, self.HARD_MAX_POSITION_USD)
        self.min_balance_usd = max(self.min_balance_usd, self.HARD_MIN_BALANCE)


@dataclass
class DataConfig:
    """Data configuration for market data and historical storage."""
    # DuckDB storage path
    db_path: str = "data/market_data.duckdb"
    
    # Cache settings (for live MarketData module)
    price_cache_seconds: int = 2
    ohlcv_cache_seconds: int = 60
    funding_cache_seconds: int = 300


@dataclass
class WebSocketConfig:
    """
    WebSocket and real-time data configuration.
    
    WebSocket Endpoint Modes:
    - LIVE: stream.bybit.com (live trading, real money)
    - DEMO: stream-demo.bybit.com (fake money)
    - Demo: stream-demo.bybit.com (demo trading API, fake money)
    
    For PUBLIC streams (market data), you can optionally use LIVE streams
    even when trading on demo API since market data is the same.
    
    For PRIVATE streams (positions, orders), the stream must match your
    REST API mode since authentication is account-specific.
    """
    # Master toggle
    enable_websocket: bool = True
    
    # Auto-start WebSocket on application initialization
    auto_start: bool = True
    
    # Timeout settings (seconds)
    startup_timeout: float = 10.0   # Max wait for WebSocket connection
    shutdown_timeout: float = 5.0   # Max wait for graceful shutdown
    
    # Runner mode: "polling" (traditional) or "realtime" (event-driven)
    runner_mode: str = "polling"  # Default to polling for backwards compatibility
    
    # Public stream options
    enable_ticker_stream: bool = True
    enable_orderbook_stream: bool = False  # High frequency, disabled by default
    enable_trades_stream: bool = False     # High frequency, disabled by default
    enable_klines_stream: bool = True
    kline_intervals: List[str] = field(default_factory=lambda: ["15"])
    
    # Private stream options
    enable_position_stream: bool = True
    enable_order_stream: bool = True
    enable_execution_stream: bool = True
    enable_wallet_stream: bool = True
    
    # Hybrid mode options
    prefer_websocket_data: bool = True     # Prefer WS data over REST
    fallback_to_polling: bool = True       # Fall back to polling if WS fails
    
    # Advanced: Use LIVE WebSocket for public market data in DEMO mode
    # Market data (tickers, orderbook, klines) is the same on LIVE and DEMO
    # This can be useful if DEMO WebSocket streams have connectivity issues
    use_live_for_public_streams: bool = False
    
    # Rate limiting
    min_evaluation_interval: float = 1.0   # Min seconds between strategy evaluations
    max_evaluations_per_minute: int = 30   # Max evaluations per minute
    
    # Staleness thresholds (seconds)
    ticker_staleness: float = 5.0
    position_staleness: float = 10.0
    wallet_staleness: float = 30.0
    
    # ===== Global Risk View Settings =====
    # These control the GlobalRiskView feature for account-wide risk monitoring
    
    # Enable/disable GlobalRiskView integration
    enable_global_risk_view: bool = True
    
    # Enable public liquidation stream (for monitoring market-wide liquidations)
    # This is a high-frequency stream, disable if not needed
    enable_public_liquidation_stream: bool = False
    
    # Maximum frequency for rebuilding portfolio risk snapshots (seconds)
    # Prevents excessive computation on rapid updates
    max_global_snapshot_frequency: float = 1.0
    
    # Enable caching for GlobalRiskView computations
    enable_risk_caching: bool = True
    
    @property
    def is_realtime_mode(self) -> bool:
        """Check if running in real-time event-driven mode."""
        return self.enable_websocket and self.runner_mode == "realtime"


@dataclass
class LogConfig:
    """Logging configuration."""
    level: str = "INFO"
    log_dir: str = "logs"
    log_trades: bool = True
    log_errors_separately: bool = True


@dataclass 
class TradingConfig:
    """
    Main trading configuration.
    
    Trading modes have a strict 1:1 mapping to API environments:
    - PAPER mode → must use DEMO API (BYBIT_USE_DEMO=true)
    - REAL mode → must use LIVE API (BYBIT_USE_DEMO=false)
    
    We never simulate trades in this codebase; both modes execute
    real orders on the Bybit API. The difference is which account
    (demo vs live) receives those orders.
    """
    # Mode (paper = demo account, real = live account)
    mode: str = TradingMode.PAPER
    
    # Symbols - must be set via env var (DEFAULT_SYMBOLS) or passed explicitly
    default_symbols: List[str] = field(default_factory=list)
    
    # Runner settings
    loop_interval_seconds: float = 15.0
    
    # Strategy settings
    strategies_dir: str = "src/strategies/configs"
    active_strategies: List[str] = field(default_factory=list)
    
    @property
    def is_paper(self) -> bool:
        """Paper mode = demo trading on Bybit demo account (fake money)."""
        return self.mode == TradingMode.PAPER
    
    @property
    def is_real(self) -> bool:
        """Real mode = live trading on Bybit live account (real money)."""
        return self.mode == TradingMode.REAL
    
    @property
    def uses_real_money(self) -> bool:
        """
        Check if this configuration uses real money.
        
        Real money is at risk only when:
        - TRADING_MODE=real AND BYBIT_USE_DEMO=false
        
        This requires checking both trading mode and API environment,
        but TradingConfig only knows its own mode. The full check
        happens in Config.validate_trading_mode_consistency().
        """
        return self.mode == TradingMode.REAL


@dataclass
class SmokeTestConfig:
    """
    Configuration for non-interactive smoke test suite.
    
    Loaded from environment variables:
    - TRADE_SMOKE_SYMBOLS: Comma-separated symbols (e.g., "BTCUSDT,ETHUSDT,SOLUSDT")
    - TRADE_SMOKE_PERIOD: Time period for data pulls (e.g., "1Y", "6M", "3M")
    - TRADE_SMOKE_USD_SIZE: Small USD amount for demo trades (e.g., "5")
    - TRADE_SMOKE_ENABLE_GAP_TESTING: Enable intentional gap testing (e.g., "true")
    
    Safety: Smoke tests always run in DEMO/PAPER mode.
    """
    # Symbols to test (must have at least 3 for full smoke test)
    symbols: List[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    
    # Period for historical data pulls (1Y = 1 year, 6M = 6 months, etc.)
    period: str = "1Y"
    
    # Small USD amount for demo trading tests (must meet minimum order size)
    # Default $20 to handle most symbols' minimum order requirements
    usd_size: float = 20.0
    
    # Enable intentional gap testing (creates gaps then tests repair)
    enable_gap_testing: bool = True
    
    # Timeframes to test (subset for faster smoke tests)
    timeframes: List[str] = field(default_factory=lambda: ["1h", "4h", "1d"])
    
    # Open interest interval for smoke test
    oi_interval: str = "1h"
    
    def __post_init__(self):
        """Validate and normalize configuration."""
        # Ensure symbols are uppercase
        self.symbols = [s.upper().strip() for s in self.symbols if s.strip()]
        
        # Validate minimum symbols
        if len(self.symbols) < 3:
            raise ValueError(
                f"TRADE_SMOKE_SYMBOLS must have at least 3 symbols, got {len(self.symbols)}: {self.symbols}"
            )
        
        # Validate period format
        valid_periods = ["1D", "1W", "1M", "3M", "6M", "1Y"]
        if self.period.upper() not in valid_periods:
            raise ValueError(
                f"TRADE_SMOKE_PERIOD must be one of {valid_periods}, got '{self.period}'"
            )
        self.period = self.period.upper()
        
        # Validate USD size (must be positive but small)
        if self.usd_size <= 0:
            raise ValueError(f"TRADE_SMOKE_USD_SIZE must be positive, got {self.usd_size}")
        if self.usd_size > 100:
            # Safety cap for smoke tests
            self.usd_size = 100.0


class Config:
    """
    Central configuration manager.
    
    Loads configuration from environment variables and provides
    typed access to all settings.
    """
    
    _instance: Optional['Config'] = None
    
    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, env_file: str = ".env"):
        if self._initialized:
            return
        
        # Load environment variables from multiple files
        # Priority: .env > api_keys.env (later files override earlier)
        for env_name in ["api_keys.env", ".env", env_file]:
            env_path = Path(env_name)
            if env_path.exists():
                load_dotenv(env_path, override=True)
        
        # Initialize sub-configs
        self.bybit = self._load_bybit_config()
        self.risk = self._load_risk_config()
        self.data = self._load_data_config()
        self.log = self._load_log_config()
        self.trading = self._load_trading_config()
        self.websocket = self._load_websocket_config()
        self.smoke = self._load_smoke_config()
        
        self._initialized = True
    
    def _load_bybit_config(self) -> BybitConfig:
        """
        Load Bybit configuration from environment (STRICT - no fallbacks).
        
        CANONICAL KEY CONTRACT (only these 4 key pairs are used):
        - BYBIT_DEMO_API_KEY / SECRET → DEMO trading (fake money)
        - BYBIT_LIVE_API_KEY / SECRET → LIVE trading (real money)
        - BYBIT_LIVE_DATA_API_KEY / SECRET → Data operations (always LIVE)
        - BYBIT_DEMO_DATA_API_KEY / SECRET → Demo data (optional)
        
        Legacy/generic keys (BYBIT_API_KEY, BYBIT_DATA_API_KEY) are loaded
        for backward compatibility inspection but are NOT used for behavior.
        """
        return BybitConfig(
            # CANONICAL: Demo trading keys (api-demo.bybit.com)
            demo_api_key=os.getenv("BYBIT_DEMO_API_KEY", ""),
            demo_api_secret=os.getenv("BYBIT_DEMO_API_SECRET", ""),
            demo_data_api_key=os.getenv("BYBIT_DEMO_DATA_API_KEY", ""),
            demo_data_api_secret=os.getenv("BYBIT_DEMO_DATA_API_SECRET", ""),
            
            # CANONICAL: Live trading keys (api.bybit.com - REAL MONEY!)
            live_api_key=os.getenv("BYBIT_LIVE_API_KEY", ""),
            live_api_secret=os.getenv("BYBIT_LIVE_API_SECRET", ""),
            live_data_api_key=os.getenv("BYBIT_LIVE_DATA_API_KEY", ""),
            live_data_api_secret=os.getenv("BYBIT_LIVE_DATA_API_SECRET", ""),
            
            # DEPRECATED: Legacy keys - loaded for inspection only, NOT used for behavior
            api_key=os.getenv("BYBIT_API_KEY", ""),
            api_secret=os.getenv("BYBIT_API_SECRET", ""),
            data_api_key=os.getenv("BYBIT_DATA_API_KEY", ""),
            data_api_secret=os.getenv("BYBIT_DATA_API_SECRET", ""),
            
            # Demo mode (true = api-demo.bybit.com, false = api.bybit.com)
            use_demo=os.getenv("BYBIT_USE_DEMO", "true").lower() == "true",
        )
    
    def _load_risk_config(self) -> RiskConfig:
        """Load risk configuration from environment."""
        return RiskConfig(
            max_leverage=int(os.getenv("MAX_LEVERAGE", "3")),
            max_position_size_usd=float(os.getenv("MAX_POSITION_SIZE_USD", "50")),
            max_daily_loss_usd=float(os.getenv("MAX_DAILY_LOSS_USD", "20")),
            min_balance_usd=float(os.getenv("MIN_BALANCE_USD", "10")),
        )
    
    def _load_data_config(self) -> DataConfig:
        """Load data configuration from environment."""
        return DataConfig(
            db_path=os.getenv("DATA_DB_PATH", "data/market_data.duckdb"),
            price_cache_seconds=int(os.getenv("PRICE_CACHE_SECONDS", "2")),
            ohlcv_cache_seconds=int(os.getenv("OHLCV_CACHE_SECONDS", "60")),
            funding_cache_seconds=int(os.getenv("FUNDING_CACHE_SECONDS", "300")),
        )
    
    def _load_log_config(self) -> LogConfig:
        """Load logging configuration from environment."""
        return LogConfig(
            level=os.getenv("LOG_LEVEL", "INFO"),
            log_dir=os.getenv("LOG_DIR", "logs"),
        )
    
    def _load_trading_config(self) -> TradingConfig:
        """Load trading configuration from environment."""
        # Symbols must be explicitly set via DEFAULT_SYMBOLS env var - no hardcoded fallback
        symbols_str = os.getenv("DEFAULT_SYMBOLS", "")
        configured_symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()] if symbols_str else []
        return TradingConfig(
            mode=os.getenv("TRADING_MODE", TradingMode.PAPER),
            default_symbols=configured_symbols,
        )
    
    def _load_websocket_config(self) -> WebSocketConfig:
        """Load WebSocket configuration from environment."""
        # Parse kline intervals
        kline_intervals_str = os.getenv("WS_KLINE_INTERVALS", "15")
        kline_intervals = [s.strip() for s in kline_intervals_str.split(",") if s.strip()]
        
        return WebSocketConfig(
            # REST-first approach: WebSocket available but not auto-started
            # Per Bybit docs: "Do not frequently connect and disconnect"
            enable_websocket=os.getenv("ENABLE_WEBSOCKET", "true").lower() == "true",
            auto_start=os.getenv("WS_AUTO_START", "false").lower() == "true",  # REST-first
            startup_timeout=float(os.getenv("WS_STARTUP_TIMEOUT", "10.0")),
            shutdown_timeout=float(os.getenv("WS_SHUTDOWN_TIMEOUT", "5.0")),
            runner_mode=os.getenv("RUNNER_MODE", "polling"),
            enable_ticker_stream=os.getenv("WS_ENABLE_TICKER", "true").lower() == "true",
            enable_orderbook_stream=os.getenv("WS_ENABLE_ORDERBOOK", "false").lower() == "true",
            enable_trades_stream=os.getenv("WS_ENABLE_TRADES", "false").lower() == "true",
            enable_klines_stream=os.getenv("WS_ENABLE_KLINES", "true").lower() == "true",
            kline_intervals=kline_intervals,
            enable_position_stream=os.getenv("WS_ENABLE_POSITIONS", "true").lower() == "true",
            enable_order_stream=os.getenv("WS_ENABLE_ORDERS", "true").lower() == "true",
            enable_execution_stream=os.getenv("WS_ENABLE_EXECUTIONS", "true").lower() == "true",
            enable_wallet_stream=os.getenv("WS_ENABLE_WALLET", "true").lower() == "true",
            prefer_websocket_data=os.getenv("PREFER_WEBSOCKET_DATA", "true").lower() == "true",
            fallback_to_polling=os.getenv("WS_FALLBACK_TO_POLLING", "true").lower() == "true",
            use_live_for_public_streams=os.getenv("WS_USE_LIVE_FOR_PUBLIC", "false").lower() == "true",
            min_evaluation_interval=float(os.getenv("WS_MIN_EVAL_INTERVAL", "1.0")),
            max_evaluations_per_minute=int(os.getenv("WS_MAX_EVALS_PER_MINUTE", "30")),
            # Global risk view settings
            enable_global_risk_view=os.getenv("ENABLE_GLOBAL_RISK_VIEW", "true").lower() == "true",
            enable_public_liquidation_stream=os.getenv("WS_ENABLE_PUBLIC_LIQUIDATION", "false").lower() == "true",
            max_global_snapshot_frequency=float(os.getenv("WS_MAX_GLOBAL_SNAPSHOT_FREQ", "1.0")),
            enable_risk_caching=os.getenv("WS_ENABLE_RISK_CACHING", "true").lower() == "true",
        )
    
    def _load_smoke_config(self) -> SmokeTestConfig:
        """
        Load smoke test configuration from environment.
        
        Environment variables:
        - TRADE_SMOKE_SYMBOLS: Comma-separated symbols (default: BTCUSDT,ETHUSDT,SOLUSDT)
        - TRADE_SMOKE_PERIOD: Data pull period (default: 1Y)
        - TRADE_SMOKE_USD_SIZE: Demo trade size in USD (default: 20)
        - TRADE_SMOKE_ENABLE_GAP_TESTING: Enable gap testing (default: true)
        """
        # Parse symbols from comma-separated string
        symbols_str = os.getenv("TRADE_SMOKE_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT")
        symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()]
        
        # Parse timeframes
        timeframes_str = os.getenv("TRADE_SMOKE_TIMEFRAMES", "1h,4h,1d")
        timeframes = [t.strip() for t in timeframes_str.split(",") if t.strip()]
        
        return SmokeTestConfig(
            symbols=symbols,
            period=os.getenv("TRADE_SMOKE_PERIOD", "1Y"),
            usd_size=float(os.getenv("TRADE_SMOKE_USD_SIZE", "20")),
            enable_gap_testing=os.getenv("TRADE_SMOKE_ENABLE_GAP_TESTING", "true").lower() == "true",
            timeframes=timeframes,
            oi_interval=os.getenv("TRADE_SMOKE_OI_INTERVAL", "1h"),
        )
    
    def reload(self, env_file: str = ".env"):
        """Reload configuration from environment."""
        self._initialized = False
        Config._instance = None
        return Config(env_file)
    
    def validate(self) -> tuple[bool, List[str]]:
        """
        Validate configuration for Unified Trading Account.
        
        Performs comprehensive validation including:
        - API credentials check for selected mode
        - Environment/trading mode consistency check
        - Risk settings validation
        - Demo vs Live mode warnings
        
        Returns:
            Tuple of (is_valid, list of error/warning messages)
        """
        errors = []
        warnings = []
        
        # === API Credentials Validation (STRICT - no fallbacks) ===
        api_key, api_secret = self.bybit.get_credentials()
        mode_name = self.bybit.get_mode_name()
        
        # Trading keys are REQUIRED for the current mode
        if not api_key or not api_secret:
            if self.bybit.is_demo:
                errors.append(
                    f"MISSING REQUIRED KEY: BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET are required for {mode_name} mode. "
                    "No fallback keys are used. Set these environment variables in .env or api_keys.env."
                )
            else:
                errors.append(
                    f"MISSING REQUIRED KEY: BYBIT_LIVE_API_KEY and BYBIT_LIVE_API_SECRET are required for {mode_name} mode. "
                    "No fallback keys are used. Set these environment variables in .env or api_keys.env."
                )
        
        # Data keys are ALWAYS required (data always uses LIVE API)
        if not self.bybit.has_live_data_credentials():
            errors.append(
                "MISSING REQUIRED KEY: BYBIT_LIVE_DATA_API_KEY and BYBIT_LIVE_DATA_API_SECRET are required for data operations. "
                "Historical and market data always use the LIVE API for accuracy. No fallback keys are used."
            )
        
        # === Environment & Trading Mode Consistency (STRICT) ===
        # Only two valid combinations: PAPER+DEMO or REAL+LIVE
        if self.trading.mode == TradingMode.REAL and self.bybit.is_demo:
            errors.append(
                "INVALID: TRADING_MODE=real but BYBIT_USE_DEMO=true. "
                "REAL mode requires LIVE API (BYBIT_USE_DEMO=false)."
            )
        
        if self.trading.mode == TradingMode.PAPER and self.bybit.is_live:
            errors.append(
                "INVALID: TRADING_MODE=paper but BYBIT_USE_DEMO=false. "
                "PAPER mode requires DEMO API (BYBIT_USE_DEMO=true)."
            )
        
        # === LIVE Mode Extra Validation ===
        if self.bybit.is_live:
            if not api_key or not api_secret:
                errors.append("⚠️ LIVE MODE (REAL MONEY) requires valid API credentials!")
            else:
                warnings.append(
                    "⚠️ CAUTION: Running in LIVE mode - all operations affect REAL MONEY"
                )
        
        # === Risk Settings Validation ===
        if self.risk.max_leverage > self.risk.HARD_MAX_LEVERAGE:
            errors.append(
                f"Max leverage ({self.risk.max_leverage}) exceeds hard cap of {self.risk.HARD_MAX_LEVERAGE}"
            )
        
        if self.risk.max_position_size_usd > self.risk.HARD_MAX_POSITION_USD:
            errors.append(
                f"Max position size (${self.risk.max_position_size_usd}) exceeds hard cap of ${self.risk.HARD_MAX_POSITION_USD}"
            )
        
        if self.risk.default_leverage > self.risk.max_leverage:
            errors.append(
                f"Default leverage ({self.risk.default_leverage}) exceeds max leverage ({self.risk.max_leverage})"
            )
        
        # === WebSocket Configuration Warnings ===
        if self.websocket.enable_websocket and self.bybit.is_live:
            if not self.websocket.enable_position_stream:
                warnings.append("Position stream disabled - live position updates won't be received")
            if not self.websocket.enable_wallet_stream:
                warnings.append("Wallet stream disabled - balance updates won't be received in real-time")
        
        # Combine errors and warnings for output
        all_messages = errors + [f"[WARN] {w}" for w in warnings]
        
        return len(errors) == 0, all_messages
    
    def validate_for_trading(self) -> tuple[bool, str]:
        """
        Strict validation before executing any trade.
        
        Returns:
            Tuple of (can_trade, reason if not)
        """
        # Must have valid credentials (STRICT - canonical keys only)
        api_key, api_secret = self.bybit.get_credentials()
        if not api_key or not api_secret:
            mode = self.bybit.get_mode_name()
            key_name = "BYBIT_DEMO_API_KEY" if self.bybit.is_demo else "BYBIT_LIVE_API_KEY"
            return False, f"MISSING REQUIRED KEY: {key_name} required for {mode} mode (no fallback)"
        
        # === SAFETY GUARD RAIL: Validate trading mode consistency ===
        is_consistent, messages = self.validate_trading_mode_consistency()
        if not is_consistent:
            # Return the first error message
            return False, messages[0] if messages else "Trading mode consistency check failed"
        
        # In LIVE mode with REAL trading
        if self.bybit.is_live and self.trading.mode == TradingMode.REAL:
            return True, "LIVE trading on real-money account ENABLED"
        
        # DEMO mode with PAPER trading
        if self.bybit.is_demo and self.trading.mode == TradingMode.PAPER:
            return True, "DEMO trading on fake-money account ready"
        
        # Should not reach here if validation passed
        return True, f"{self.bybit.get_mode_name()} mode ready"
    
    def validate_trading_mode_consistency(self) -> tuple[bool, List[str]]:
        """
        SAFETY GUARD RAIL: Validate strict mapping between trading mode and API environment.
        
        Enforces the canonical contract:
        - PAPER mode MUST use DEMO API (BYBIT_USE_DEMO=true)
        - REAL mode MUST use LIVE API (BYBIT_USE_DEMO=false)
        
        Any other combination is a hard error that blocks startup/trading.
        We never simulate trades; both modes execute real orders on Bybit.
        The difference is which account (demo vs live) receives those orders.
        
        Returns:
            Tuple of (is_valid, list of errors)
            - is_valid: True only if configuration matches one of the two valid combos
            - messages: List of error strings explaining any violations
        """
        errors = []
        
        # === INVALID: REAL mode on DEMO API ===
        # User says "real" but API is demo - dangerous mismatch
        if self.trading.mode == TradingMode.REAL and self.bybit.use_demo:
            errors.append(
                "INVALID CONFIGURATION: TRADING_MODE=real but BYBIT_USE_DEMO=true. "
                "REAL mode requires LIVE API. Set BYBIT_USE_DEMO=false to enable live trading, "
                "or use TRADING_MODE=paper for demo account trading."
            )
        
        # === INVALID: PAPER mode on LIVE API ===
        # User says "paper" but API is live - also a mismatch
        if self.trading.mode == TradingMode.PAPER and not self.bybit.use_demo:
            errors.append(
                "INVALID CONFIGURATION: TRADING_MODE=paper but BYBIT_USE_DEMO=false. "
                "PAPER mode requires DEMO API. Set BYBIT_USE_DEMO=true for paper/demo trading, "
                "or use TRADING_MODE=real for live account trading."
            )
        
        # Format all errors
        all_messages = [f"[ERROR] {e}" for e in errors]
        
        return len(errors) == 0, all_messages
    
    def validate_data_credentials(self) -> tuple[bool, List[str]]:
        """
        Validate that LIVE data credentials are configured (STRICT).
        
        Data operations (historical data, market data) always use LIVE API
        for accuracy. This method checks if BYBIT_LIVE_DATA_API_KEY is set.
        
        CANONICAL KEY CONTRACT:
        - Data operations require BYBIT_LIVE_DATA_API_KEY (no fallback)
        - Missing keys cause this to return (False, [error_message])
        
        Returns:
            Tuple of (has_credentials, list of error messages)
        """
        errors = []
        
        # STRICT: Only check live_data_api_key (no fallback to trading keys)
        has_keys = self.bybit.has_live_data_credentials()
        
        if not has_keys:
            errors.append(
                "MISSING REQUIRED KEY: BYBIT_LIVE_DATA_API_KEY and BYBIT_LIVE_DATA_API_SECRET are required. "
                "Historical and market data always use the LIVE API for accuracy. "
                "No fallback to trading keys or generic keys is allowed."
            )
        
        return has_keys, errors
    
    def get_api_environment_summary(self) -> dict:
        """
        Get a comprehensive summary of API environment configuration.
        
        Delegates to BybitConfig.get_api_environment_summary() and adds
        additional config-level information like trading mode.
        
        Returns:
            Dict with trading, data, websocket environment info plus config details
        """
        env_summary = self.bybit.get_api_environment_summary()
        
        # Add trading mode info
        env_summary["trading"]["trading_mode"] = self.trading.mode
        env_summary["trading"]["is_paper"] = self.trading.is_paper
        env_summary["trading"]["is_real"] = self.trading.is_real
        
        # Add websocket config details
        env_summary["websocket"]["enabled"] = self.websocket.enable_websocket
        env_summary["websocket"]["auto_start"] = self.websocket.auto_start
        
        # Add consistency check status
        is_consistent, msgs = self.validate_trading_mode_consistency()
        env_summary["safety"] = {
            "mode_consistent": is_consistent,
            "messages": msgs,
        }
        
        return env_summary
    
    def get_api_environment_display(self) -> str:
        """
        Get a short human-readable API environment string for display.
        
        Returns:
            String like "Trading: DEMO | Data: LIVE"
        """
        return self.bybit.get_api_environment_display()
    
    def summary(self) -> str:
        """Generate a human-readable configuration summary for Unified Trading Account."""
        # Trading mode
        if self.trading.is_paper:
            trade_mode = "PAPER (demo trading on fake-money account)"
        else:
            trade_mode = "REAL (live trading on real-money account)"
        
        # Environment (DEMO vs LIVE)
        env_display = self.bybit.get_mode_display()
        env_warning = self.bybit.get_mode_warning()
        
        ws_mode = "REALTIME (event-driven)" if self.websocket.is_realtime_mode else "POLLING (traditional)"
        
        # Check for credentials
        trading_key, _ = self.bybit.get_credentials()
        data_key, _ = self.bybit.get_data_credentials()
        live_data_key, _ = self.bybit.get_live_data_credentials()
        
        # Money status
        if self.bybit.is_live and self.trading.is_real:
            money_status = "⚠️  REAL MONEY AT RISK ⚠️"
        elif self.bybit.is_live:
            money_status = "⚠️  Using LIVE API (paper trading)"
        else:
            money_status = "✓ FAKE MONEY (Demo account)"
        
        # Safety check status
        is_consistent, consistency_msgs = self.validate_trading_mode_consistency()
        safety_status = "✓ PASSED" if is_consistent else "✗ FAILED"
        
        lines = [
            "=" * 55,
            "BYBIT UNIFIED TRADING ACCOUNT - CONFIGURATION",
            "=" * 55,
            "",
            f"Account Type: UNIFIED (v5 API)",
            f"Environment:  {env_display}",
            f"Trading:      {trade_mode}",
            f"Status:       {money_status}",
            f"  {env_warning}",
            "",
            f"Safety Check: {safety_status}",
        ]
        
        # Add any safety messages
        if consistency_msgs:
            for msg in consistency_msgs:
                lines.append(f"  {msg}")
        
        lines.extend([
            "",
            f"Runner: {ws_mode}",
            f"Symbols: {', '.join(self.trading.default_symbols) or '(none configured)'}",
            "",
            "Risk Settings:",
            f"  Max Leverage:    {self.risk.max_leverage}x (cap: {self.risk.HARD_MAX_LEVERAGE}x)",
            f"  Max Position:    ${self.risk.max_position_size_usd:,.0f} (cap: ${self.risk.HARD_MAX_POSITION_USD:,.0f})",
            f"  Max Daily Loss:  ${self.risk.max_daily_loss_usd:,.0f}",
            f"  Min Balance:     ${self.risk.min_balance_usd:,.0f}",
            "",
            f"API Keys - Trading ({self.bybit.get_mode_name()}):",
            f"  Trading (R/W): {'✓ Configured' if trading_key else '✗ Missing'}",
            f"  Data (R/O):    {'✓ Configured' if data_key else '✗ Missing'}",
            "",
            "API Keys - Data (ALWAYS LIVE for accuracy):",
            f"  LIVE Data:     {'✓ Configured' if live_data_key else '✗ Missing (required for historical/market data)'}",
            "",
            "WebSocket Streams:",
            f"  Enabled: {self.websocket.enable_websocket}",
            f"  Positions: {self.websocket.enable_position_stream}",
            f"  Orders:    {self.websocket.enable_order_stream}",
            f"  Wallet:    {self.websocket.enable_wallet_stream}",
            "",
            "Data Capture:",
            f"  Enabled: {self.data.enable_capture}",
            f"  Symbols: {', '.join(self.data.capture_symbols) or '(none)'}",
            "=" * 55,
        ])
        return "\n".join(lines)
    
    def summary_short(self) -> str:
        """Generate a short one-line configuration summary."""
        mode = self.bybit.get_mode_name()
        trade = self.trading.mode.upper()
        key_status = "✓" if self.bybit.has_credentials() else "✗"
        return f"Bybit UTA | {mode} | Trading: {trade} | API: {key_status}"


def get_config(env_file: str = ".env") -> Config:
    """Get or create the global config instance."""
    return Config(env_file)


