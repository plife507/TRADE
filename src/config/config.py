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


# Trading modes
class TradingMode:
    PAPER = "paper"  # Demo mode - simulated trades (safe for testing)
    REAL = "real"    # Live trading (REAL MONEY!)


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
    
    # Legacy/fallback keys (used if mode-specific keys not set)
    api_key: str = ""
    api_secret: str = ""
    data_api_key: str = ""
    data_api_secret: str = ""
    
    # Endpoints
    demo_base_url: str = "https://api-demo.bybit.com"   # DEMO (FAKE MONEY)
    live_base_url: str = "https://api.bybit.com"        # LIVE (REAL MONEY)
    
    # Environment toggle: True = DEMO (safe), False = LIVE (real money!)
    use_demo: bool = True
    
    def get_credentials(self) -> tuple:
        """
        Get trading API key and secret for current mode.
        
        Returns appropriate credentials based on demo/live mode.
        Falls back to generic keys if mode-specific keys not set.
        """
        if self.use_demo:
            # Try demo-specific keys first, then fallback
            key = self.demo_api_key or self.api_key
            secret = self.demo_api_secret or self.api_secret
        else:
            # Try live-specific keys first, then fallback
            key = self.live_api_key or self.api_key
            secret = self.live_api_secret or self.api_secret
        return key, secret
    
    def get_data_credentials(self) -> tuple:
        """
        Get data API key and secret for current mode (read-only, for market data).
        
        Data keys have higher rate limits (120 RPS vs 50 RPS).
        Falls back to trading keys if data keys not set.
        """
        if self.use_demo:
            # Try demo data keys, then demo trading keys, then generic
            key = self.demo_data_api_key or self.demo_api_key or self.data_api_key or self.api_key
            secret = self.demo_data_api_secret or self.demo_api_secret or self.data_api_secret or self.api_secret
        else:
            # Try live data keys, then live trading keys, then generic
            key = self.live_data_api_key or self.live_api_key or self.data_api_key or self.api_key
            secret = self.live_data_api_secret or self.live_api_secret or self.data_api_secret or self.api_secret
        return key, secret
    
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
        Get LIVE data API credentials (always LIVE, regardless of use_demo setting).
        
        Historical and market data should always use LIVE API for accuracy.
        The LIVE API has real market data that matches production trading.
        
        This method ALWAYS returns LIVE credentials, never DEMO.
        
        Returns:
            Tuple of (api_key, api_secret) for LIVE data API
        """
        # Always return LIVE data keys, regardless of use_demo setting
        key = self.live_data_api_key or self.live_api_key or self.data_api_key or self.api_key
        secret = self.live_data_api_secret or self.live_api_secret or self.data_api_secret or self.api_secret
        return key, secret
    
    def has_live_data_credentials(self) -> bool:
        """
        Check if LIVE data API credentials are configured.
        
        Used to warn users if LIVE data keys are missing (data operations
        will fail or fallback to unauthenticated access).
        """
        key, secret = self.get_live_data_credentials()
        return bool(key and secret)


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
    """Data collection configuration."""
    enable_capture: bool = False
    capture_symbols: List[str] = field(default_factory=list)  # Must be set via env var or explicitly
    capture_timeframes: List[str] = field(default_factory=lambda: ["1m", "5m", "15m", "1h", "4h", "1d"])
    capture_interval_seconds: int = 60
    
    # Storage paths
    data_dir: str = "data/historical"
    ohlcv_dir: str = "data/historical/ohlcv"
    funding_dir: str = "data/historical/funding"
    oi_dir: str = "data/historical/open_interest"
    
    # Cache settings (for live data)
    price_cache_seconds: int = 2
    ohlcv_cache_seconds: int = 60
    funding_cache_seconds: int = 300


@dataclass
class WebSocketConfig:
    """
    WebSocket and real-time data configuration.
    
    WebSocket Endpoint Modes:
    - Mainnet: stream.bybit.com (live trading, real money)
    - Testnet: stream-testnet.bybit.com (testnet, fake money)
    - Demo: stream-demo.bybit.com (demo trading API, fake money)
    
    For PUBLIC streams (market data), you can optionally use mainnet streams
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
    
    # Advanced: Use mainnet WebSocket for public market data in demo mode
    # Market data (tickers, orderbook, klines) is the same on mainnet and demo
    # This can be useful if demo WebSocket streams have connectivity issues
    use_mainnet_for_public_streams: bool = False
    
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
    """Main trading configuration."""
    # Mode (paper = demo, real = live trading)
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
        """Paper mode = simulated trades (demo)."""
        return self.mode == TradingMode.PAPER
    
    @property
    def is_real(self) -> bool:
        """Real mode = live trading."""
        return self.mode == TradingMode.REAL
    
    @property
    def uses_real_money(self) -> bool:
        """Only real mode with demo=false uses actual money."""
        return self.mode == TradingMode.REAL


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
        
        self._initialized = True
    
    def _load_bybit_config(self) -> BybitConfig:
        """
        Load Bybit configuration from environment.
        
        Supports separate API keys for Demo and Live modes:
        - BYBIT_DEMO_API_KEY / BYBIT_DEMO_API_SECRET for demo
        - BYBIT_LIVE_API_KEY / BYBIT_LIVE_API_SECRET for live
        
        Falls back to generic BYBIT_API_KEY / BYBIT_API_SECRET if
        mode-specific keys are not set.
        """
        return BybitConfig(
            # Demo API keys (api-demo.bybit.com)
            demo_api_key=os.getenv("BYBIT_DEMO_API_KEY", ""),
            demo_api_secret=os.getenv("BYBIT_DEMO_API_SECRET", ""),
            demo_data_api_key=os.getenv("BYBIT_DEMO_DATA_API_KEY", ""),
            demo_data_api_secret=os.getenv("BYBIT_DEMO_DATA_API_SECRET", ""),
            
            # Live API keys (api.bybit.com - REAL MONEY!)
            live_api_key=os.getenv("BYBIT_LIVE_API_KEY", ""),
            live_api_secret=os.getenv("BYBIT_LIVE_API_SECRET", ""),
            live_data_api_key=os.getenv("BYBIT_LIVE_DATA_API_KEY", ""),
            live_data_api_secret=os.getenv("BYBIT_LIVE_DATA_API_SECRET", ""),
            
            # Fallback/legacy keys (used if mode-specific keys not set)
            api_key=os.getenv("BYBIT_API_KEY", os.getenv("BYBIT_MAINNET_API_KEY", "")),
            api_secret=os.getenv("BYBIT_API_SECRET", os.getenv("BYBIT_MAINNET_API_SECRET", "")),
            data_api_key=os.getenv("BYBIT_DATA_API_KEY", os.getenv("BYBIT_MAINNET_DATA_API_KEY", "")),
            data_api_secret=os.getenv("BYBIT_DATA_API_SECRET", os.getenv("BYBIT_MAINNET_DATA_API_SECRET", "")),
            
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
        symbols_str = os.getenv("DATA_CAPTURE_SYMBOLS", "")
        # Only create list if symbols are actually configured
        capture_symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()] if symbols_str else []
        return DataConfig(
            enable_capture=os.getenv("ENABLE_DATA_CAPTURE", "false").lower() == "true",
            capture_symbols=capture_symbols,
            capture_interval_seconds=int(os.getenv("DATA_CAPTURE_INTERVAL_SECONDS", "60")),
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
            use_mainnet_for_public_streams=os.getenv("WS_USE_MAINNET_FOR_PUBLIC", "false").lower() == "true",
            min_evaluation_interval=float(os.getenv("WS_MIN_EVAL_INTERVAL", "1.0")),
            max_evaluations_per_minute=int(os.getenv("WS_MAX_EVALS_PER_MINUTE", "30")),
            # Global risk view settings
            enable_global_risk_view=os.getenv("ENABLE_GLOBAL_RISK_VIEW", "true").lower() == "true",
            enable_public_liquidation_stream=os.getenv("WS_ENABLE_PUBLIC_LIQUIDATION", "false").lower() == "true",
            max_global_snapshot_frequency=float(os.getenv("WS_MAX_GLOBAL_SNAPSHOT_FREQ", "1.0")),
            enable_risk_caching=os.getenv("WS_ENABLE_RISK_CACHING", "true").lower() == "true",
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
        
        # === API Credentials Validation ===
        api_key, api_secret = self.bybit.get_credentials()
        mode_name = self.bybit.get_mode_name()
        
        if not api_key or not api_secret:
            errors.append(f"Bybit {mode_name} API credentials not configured")
            if self.bybit.is_demo:
                errors.append("  Set BYBIT_DEMO_API_KEY and BYBIT_DEMO_API_SECRET in .env")
            else:
                errors.append("  Set BYBIT_LIVE_API_KEY and BYBIT_LIVE_API_SECRET in .env")
        
        # Verify correct key type for mode
        if self.bybit.is_demo:
            if not self.bybit.demo_api_key and self.bybit.api_key:
                warnings.append("Using fallback API key for DEMO mode - consider using BYBIT_DEMO_API_KEY")
        else:
            if not self.bybit.live_api_key and self.bybit.api_key:
                warnings.append("⚠️ Using fallback API key for LIVE mode - consider using BYBIT_LIVE_API_KEY")
        
        # === Environment & Trading Mode Consistency ===
        # If trading mode is REAL but using DEMO API, that's a mismatch
        if self.trading.mode == TradingMode.REAL and self.bybit.is_demo:
            warnings.append(
                "⚠️ TRADING_MODE=real but BYBIT_USE_DEMO=true: "
                "Trades will execute on DEMO account (no real money)"
            )
        
        # If trading mode is PAPER but using LIVE API
        if self.trading.mode == TradingMode.PAPER and self.bybit.is_live:
            warnings.append(
                "TRADING_MODE=paper but BYBIT_USE_DEMO=false: "
                "API calls use LIVE account but trades are simulated"
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
        # Must have valid credentials
        api_key, api_secret = self.bybit.get_credentials()
        if not api_key or not api_secret:
            return False, f"No API credentials for {self.bybit.get_mode_name()} mode"
        
        # === SAFETY GUARD RAIL: Validate trading mode consistency ===
        is_consistent, messages = self.validate_trading_mode_consistency()
        if not is_consistent:
            # Return the first error message
            return False, messages[0] if messages else "Trading mode consistency check failed"
        
        # In LIVE mode with REAL trading, extra confirmation
        if self.bybit.is_live and self.trading.mode == TradingMode.REAL:
            # All checks passed for live real trading
            return True, "LIVE REAL TRADING ENABLED"
        
        # Demo mode or paper trading is always allowed with credentials
        return True, f"{self.bybit.get_mode_name()} mode ready"
    
    def validate_trading_mode_consistency(self) -> tuple[bool, List[str]]:
        """
        SAFETY GUARD RAIL: Validate that trading mode matches API environment.
        
        This prevents dangerous mismatches like:
        - TRADING_MODE=real but BYBIT_USE_DEMO=true (would trade on demo instead of live)
        - Ensures user intention matches actual API behavior
        
        Returns:
            Tuple of (is_valid, list of errors/warnings)
            - is_valid: True if configuration is safe for trading
            - messages: List of error/warning strings explaining any issues
        """
        errors = []
        warnings = []
        
        # === CRITICAL SAFETY CHECK ===
        # Block trading if user says "real" but API is demo
        # This prevents user thinking they're live trading when they're not
        if self.trading.mode == TradingMode.REAL and self.bybit.use_demo:
            errors.append(
                "SAFETY CHECK FAILED: TRADING_MODE=real but BYBIT_USE_DEMO=true. "
                "You indicated REAL trading mode but are connected to DEMO API. "
                "Set BYBIT_USE_DEMO=false to enable live trading, or use TRADING_MODE=paper for demo."
            )
        
        # === WARNING: Paper trading on LIVE API ===
        # This is allowed but user should be aware
        if self.trading.mode == TradingMode.PAPER and not self.bybit.use_demo:
            warnings.append(
                "TRADING_MODE=paper but BYBIT_USE_DEMO=false: "
                "Using LIVE API for paper trading. Trades will be simulated but "
                "API calls interact with your real account (read operations)."
            )
        
        # All errors are blocking, warnings are informational
        all_messages = [f"[ERROR] {e}" for e in errors] + [f"[WARN] {w}" for w in warnings]
        
        return len(errors) == 0, all_messages
    
    def validate_data_credentials(self) -> tuple[bool, List[str]]:
        """
        Validate that LIVE data credentials are configured.
        
        Data operations (historical data, market data) always use LIVE API
        for accuracy. This method checks if those credentials are available.
        
        Returns:
            Tuple of (has_credentials, list of warnings)
        """
        warnings = []
        
        key, secret = self.bybit.get_live_data_credentials()
        
        if not key or not secret:
            warnings.append(
                "LIVE data API credentials not configured. "
                "Historical data and market data require LIVE API access. "
                "Set BYBIT_LIVE_DATA_API_KEY/SECRET or BYBIT_LIVE_API_KEY/SECRET."
            )
        
        return bool(key and secret), warnings
    
    def summary(self) -> str:
        """Generate a human-readable configuration summary for Unified Trading Account."""
        # Trading mode
        if self.trading.is_paper:
            trade_mode = "PAPER (simulated trades)"
        else:
            trade_mode = "REAL (executing trades)"
        
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


