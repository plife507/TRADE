"""
Configuration management for the trading bot.
Loads settings from environment variables with sensible defaults.
"""

import os
import threading
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Note: Symbols should always be passed as explicit parameters by users/agents
# The config only stores user-configured symbols from environment variables


@dataclass
class BybitConfig:
    """
    Bybit API configuration (LIVE only).

    API endpoint: api.bybit.com
    WebSocket: stream.bybit.com

    Separate read-only data keys (120 RPS) vs trading keys (50 RPS)
    for better rate limit management.
    """
    # LIVE API keys (api.bybit.com) - REAL MONEY!
    live_api_key: str = ""
    live_api_secret: str = ""
    live_data_api_key: str = ""
    live_data_api_secret: str = ""

    # Endpoint
    live_base_url: str = "https://api.bybit.com"

    def get_credentials(self) -> tuple:
        """
        Get trading API key and secret (STRICT - no fallbacks).

        Returns:
            Tuple of (api_key, api_secret) for live trading
        """
        return self.live_api_key, self.live_api_secret

    def get_data_credentials(self) -> tuple:
        """
        Get data API key and secret (STRICT - no fallbacks).

        Data keys have higher rate limits (120 RPS vs 50 RPS).

        Returns:
            Tuple of (api_key, api_secret) for data operations
        """
        return self.live_data_api_key, self.live_data_api_secret

    def get_base_url(self) -> str:
        """Get base URL for Bybit API."""
        return self.live_base_url

    def get_mode_name(self) -> str:
        """Get human-readable mode name (short)."""
        return "LIVE"

    def get_mode_display(self) -> str:
        """Get mode display string with risk warning."""
        return "LIVE (REAL MONEY)"

    def get_mode_warning(self) -> str:
        """Get warning message for current mode."""
        return "⚠️  CAUTION: Real money at risk!"

    @property
    def is_live(self) -> bool:
        """Check if running in LIVE (real money) mode. Always True."""
        return True

    def has_credentials(self) -> bool:
        """Check if valid credentials are configured."""
        key, secret = self.get_credentials()
        return bool(key and secret)

    def get_live_data_credentials(self) -> tuple:
        """
        Get LIVE data API credentials (STRICT - no fallbacks).

        Historical and market data always use LIVE API for accuracy.

        Returns:
            Tuple of (api_key, api_secret) for LIVE data API
        """
        return self.live_data_api_key, self.live_data_api_secret

    def has_live_data_credentials(self) -> bool:
        """
        Check if LIVE data API credentials are configured (STRICT).

        Returns True only if BYBIT_LIVE_DATA_API_KEY and SECRET are set.
        """
        return bool(self.live_data_api_key and self.live_data_api_secret)

    def get_api_environment_summary(self) -> dict:
        """
        Get a summary of API environment (2 legs: trade + data).

        Returns:
            Dict with trade_live, data_live, websocket, and safety info
        """
        # Trading LIVE leg
        trade_live_key = bool(self.live_api_key and self.live_api_secret)
        trade_live_source = "BYBIT_LIVE_API_KEY" if self.live_api_key else "MISSING"

        # Data LIVE leg
        data_live_key = bool(self.live_data_api_key and self.live_data_api_secret)
        data_live_source = "BYBIT_LIVE_DATA_API_KEY" if self.live_data_api_key else "MISSING"

        # Safety validation
        messages = []
        if not trade_live_key:
            messages.append("BYBIT_LIVE_API_KEY not set")

        return {
            "trading": {
                "mode": "LIVE",
                "base_url": self.live_base_url,
                "key_configured": trade_live_key,
                "key_source": trade_live_source,
            },
            "data": {
                "mode": "LIVE",
                "base_url": self.live_base_url,
                "key_configured": data_live_key,
                "key_source": data_live_source,
            },
            "trade_live": {
                "mode": "LIVE",
                "base_url": self.live_base_url,
                "key_configured": trade_live_key,
                "key_source": trade_live_source,
            },
            "data_live": {
                "mode": "LIVE",
                "base_url": self.live_base_url,
                "key_configured": data_live_key,
                "key_source": data_live_source,
                "purpose": "Canonical backtest/research history",
            },
            "websocket": {
                "mode": "LIVE",
                "public_url": "wss://stream.bybit.com",
                "private_url": "wss://stream.bybit.com",
            },
            "safety": {
                "mode_consistent": len(messages) == 0,
                "messages": messages,
            },
        }

    def get_api_environment_display(self) -> str:
        """
        Get a short human-readable API environment string for display.

        Returns:
            String like "Trading: LIVE | Keys: Trade[✓] Data[✓]"
        """
        env = self.get_api_environment_summary()

        tl = "✓" if env["trade_live"]["key_configured"] else "✗"
        dl = "✓" if env["data_live"]["key_configured"] else "✗"

        return f"Trading: LIVE | Keys: Trade[{tl}] Data[{dl}]"


@dataclass
class RiskConfig:
    """Risk management configuration."""
    # Leverage limits
    max_leverage: int = 3
    default_leverage: int = 2
    
    # Position size limits (USDT)
    max_position_size_usdt: float = 50.0
    max_total_exposure_usd: float = 200.0
    
    # Loss limits
    max_daily_loss_usd: float = 20.0
    max_daily_loss_percent: float = 10.0  # % of account
    
    # Account protection
    min_balance_usd: float = 10.0
    
    # Per-trade risk
    max_risk_per_trade_percent: float = 2.0  # % of account per trade

    # Minimum viable trade size (trades below this are rejected)
    min_viable_size_usdt: float = 5.0

    # Max drawdown circuit breaker (0 = disabled, >0 = block new entries at this drawdown %)
    max_drawdown_pct: float = 0.0

    def __post_init__(self):
        """Validate risk config values are sane."""
        if self.max_leverage < 1:
            raise ValueError(f"max_leverage must be >= 1. Got: {self.max_leverage}")
        if self.max_position_size_usdt <= 0:
            raise ValueError(f"max_position_size_usdt must be > 0. Got: {self.max_position_size_usdt}")
        if self.min_balance_usd < 0:
            raise ValueError(f"min_balance_usd must be >= 0. Got: {self.min_balance_usd}")


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

    All streams use stream.bybit.com (live endpoint).
    """
    # Master toggle
    enable_websocket: bool = True

    # Auto-start WebSocket on application initialization
    auto_start: bool = False

    # Timeout settings (seconds)
    startup_timeout: float = 10.0   # Max wait for WebSocket connection
    shutdown_timeout: float = 5.0   # Max wait for graceful shutdown

    # Runner mode: "polling" (traditional) or "realtime" (event-driven)
    runner_mode: str = "polling"  # Default to polling (explicit WebSocket opt-in)

    # Public stream options
    enable_ticker_stream: bool = True
    enable_orderbook_stream: bool = False  # High frequency, disabled by default
    enable_trades_stream: bool = False     # High frequency, disabled by default
    enable_klines_stream: bool = True
    # Empty default — LiveRunner subscribes to exactly the play's timeframes
    kline_intervals: list[str] = field(default_factory=list)
    
    # Private stream options
    enable_position_stream: bool = True
    enable_order_stream: bool = True
    enable_execution_stream: bool = True
    enable_wallet_stream: bool = True
    
    # Hybrid mode options
    prefer_websocket_data: bool = True     # Prefer WS data over REST
    fallback_to_polling: bool = True       # Fall back to polling if WS fails
    
    # Reserved for future use
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
class TradingConfig:
    """
    Main trading configuration.

    All trading uses the live Bybit API. Mode (shadow vs live) is
    selected per-play at runtime via --mode flag.
    """
    # Symbols - must be set via env var (DEFAULT_SYMBOLS) or passed explicitly
    default_symbols: list[str] = field(default_factory=list)

    # Runner settings
    loop_interval_seconds: float = 15.0

    # Strategy settings
    strategies_dir: str = "src/strategies/configs"
    active_strategies: list[str] = field(default_factory=list)


@dataclass
class SmokeTestConfig:
    """
    Configuration for non-interactive smoke test suite.

    Loaded from environment variables:
    - TRADE_SMOKE_SYMBOLS: Comma-separated symbols (e.g., "BTCUSDT,ETHUSDT,SOLUSDT")
    - TRADE_SMOKE_PERIOD: Time period for data pulls (e.g., "1Y", "6M", "3M")
    - TRADE_SMOKE_USD_SIZE: Small USD amount for demo trades (e.g., "5")
    - TRADE_SMOKE_ENABLE_GAP_TESTING: Enable intentional gap testing (e.g., "true")

    Safety: Smoke tests use small order sizes for validation.
    """
    # Symbols to test (must have at least 3 for full smoke test)
    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])

    # Period for historical data pulls (1Y = 1 year, 6M = 6 months, etc.)
    period: str = "1Y"

    # Small USD amount for demo trading tests (must meet minimum order size)
    # Default $20 to handle most symbols' minimum order requirements
    usd_size: float = 20.0

    # Enable intentional gap testing (creates gaps then tests repair)
    enable_gap_testing: bool = True

    # Timeframes to test (subset for faster smoke tests)
    timeframes: list[str] = field(default_factory=lambda: ["1h", "4h", "D"])
    
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

    _instance: 'Config | None' = None
    _singleton_lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            with cls._singleton_lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self, env_file: str = ".env"):
        if self._initialized:
            return
        
        # Load environment variables from multiple files
        # Priority: .env > api_keys.env (later files override earlier)
        loaded_env_files: list[str] = []
        for env_name in ["api_keys.env", ".env", env_file]:
            env_path = Path(env_name)
            if env_path.exists():
                load_dotenv(env_path, override=True)
                loaded_env_files.append(env_name)
        if "api_keys.env" in loaded_env_files and ".env" in loaded_env_files:
            from src.utils.logger import get_module_logger
            get_module_logger(__name__).warning(
                "Both .env and api_keys.env found. "
                ".env values override api_keys.env (load order: api_keys.env → .env)."
            )
        
        # Initialize sub-configs
        self.bybit = self._load_bybit_config()
        self.risk = self._load_risk_config()
        self.data = self._load_data_config()
        self.trading = self._load_trading_config()
        self.websocket = self._load_websocket_config()
        self.smoke = self._load_smoke_config()

        self._initialized = True
    
    def _load_bybit_config(self) -> BybitConfig:
        """
        Load Bybit configuration from environment (STRICT - no fallbacks).

        CANONICAL KEY CONTRACT (2 key pairs):
        - BYBIT_LIVE_API_KEY / SECRET → LIVE trading (real money)
        - BYBIT_LIVE_DATA_API_KEY / SECRET → Data operations (always LIVE)
        """
        return BybitConfig(
            # Live trading keys (api.bybit.com - REAL MONEY!)
            live_api_key=os.getenv("BYBIT_LIVE_API_KEY", ""),
            live_api_secret=os.getenv("BYBIT_LIVE_API_SECRET", ""),
            live_data_api_key=os.getenv("BYBIT_LIVE_DATA_API_KEY", ""),
            live_data_api_secret=os.getenv("BYBIT_LIVE_DATA_API_SECRET", ""),
        )
    
    def _load_risk_config(self) -> RiskConfig:
        """Load risk configuration from environment."""
        return RiskConfig(
            max_leverage=int(os.getenv("MAX_LEVERAGE", "3")),
            max_position_size_usdt=float(os.getenv("MAX_POSITION_SIZE_USDT", "50")),
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
    
    def _load_trading_config(self) -> TradingConfig:
        """Load trading configuration from environment."""
        # Symbols must be explicitly set via DEFAULT_SYMBOLS env var - no hardcoded fallback
        symbols_str = os.getenv("DEFAULT_SYMBOLS", "")
        configured_symbols = [s.strip().upper() for s in symbols_str.split(",") if s.strip()] if symbols_str else []
        return TradingConfig(
            default_symbols=configured_symbols,
        )
    
    def _load_websocket_config(self) -> WebSocketConfig:
        """Load WebSocket configuration from environment."""
        # Parse kline intervals
        kline_intervals_str = os.getenv("WS_KLINE_INTERVALS", "")
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
        
        # Parse timeframes (D for daily, matching Bybit format)
        timeframes_str = os.getenv("TRADE_SMOKE_TIMEFRAMES", "1h,4h,D")
        timeframes = [t.strip() for t in timeframes_str.split(",") if t.strip()]
        
        return SmokeTestConfig(
            symbols=symbols,
            period=os.getenv("TRADE_SMOKE_PERIOD", "1Y"),
            usd_size=float(os.getenv("TRADE_SMOKE_USD_SIZE", "20")),
            enable_gap_testing=os.getenv("TRADE_SMOKE_ENABLE_GAP_TESTING", "true").lower() == "true",
            timeframes=timeframes,
            oi_interval=os.getenv("TRADE_SMOKE_OI_INTERVAL", "1h"),
        )
    
    def reload(self, env_file: str = ".env") -> None:
        """Reload configuration from environment in-place.

        Re-reads env files and updates all sub-configs on the existing
        instance so that existing references remain valid.
        """
        self._initialized = False

        # Re-read environment files (same priority as __init__)
        for env_name in ["api_keys.env", ".env", env_file]:
            env_path = Path(env_name)
            if env_path.exists():
                load_dotenv(env_path, override=True)

        # Update sub-configs in-place on the existing singleton
        self.bybit = self._load_bybit_config()
        self.risk = self._load_risk_config()
        self.data = self._load_data_config()
        self.trading = self._load_trading_config()
        self.websocket = self._load_websocket_config()
        self.smoke = self._load_smoke_config()

        self._initialized = True

    def validate(self) -> tuple[bool, list[str]]:
        """
        Validate configuration for Unified Trading Account.

        Performs comprehensive validation including:
        - API credentials check
        - Risk settings validation

        Returns:
            Tuple of (is_valid, list of error/warning messages)
        """
        errors = []
        warnings = []

        # === API Credentials Validation (STRICT - no fallbacks) ===
        api_key, api_secret = self.bybit.get_credentials()

        # Trading keys are REQUIRED
        if not api_key or not api_secret:
            errors.append(
                "MISSING REQUIRED KEY: BYBIT_LIVE_API_KEY and BYBIT_LIVE_API_SECRET are required. "
                "No fallback keys are used. Set these environment variables in .env or api_keys.env."
            )

        # Data keys are ALWAYS required
        if not self.bybit.has_live_data_credentials():
            errors.append(
                "MISSING REQUIRED KEY: BYBIT_LIVE_DATA_API_KEY and BYBIT_LIVE_DATA_API_SECRET are required for data operations. "
                "Historical and market data always use the LIVE API for accuracy. No fallback keys are used."
            )

        # === LIVE Mode Validation ===
        if not api_key or not api_secret:
            errors.append("LIVE MODE (REAL MONEY) requires valid API credentials!")
        else:
            warnings.append(
                "CAUTION: Running in LIVE mode - all operations affect REAL MONEY"
            )

        # === Risk Settings Validation ===
        if self.risk.default_leverage > self.risk.max_leverage:
            errors.append(
                f"Default leverage ({self.risk.default_leverage}) exceeds max leverage ({self.risk.max_leverage})"
            )

        # === WebSocket Configuration Warnings ===
        if self.websocket.enable_websocket:
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
            return False, "MISSING REQUIRED KEY: BYBIT_LIVE_API_KEY required for LIVE mode (no fallback)"

        return True, "LIVE trading on real-money account ENABLED"

    def validate_data_credentials(self) -> tuple[bool, list[str]]:
        """
        Validate that LIVE data credentials are configured (STRICT).

        Data operations (historical data, market data) always use LIVE API
        for accuracy. This method checks if BYBIT_LIVE_DATA_API_KEY is set.

        Returns:
            Tuple of (has_credentials, list of error messages)
        """
        errors = []

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
        Get a summary of API environment configuration.

        Returns:
            Dict with trading, data, websocket environment info
        """
        env_summary = self.bybit.get_api_environment_summary()

        # Trading is always live (shadow vs live selected per-play at runtime)
        env_summary["trading"]["trading_mode"] = "live"

        # Add websocket config details
        env_summary["websocket"]["enabled"] = self.websocket.enable_websocket
        env_summary["websocket"]["auto_start"] = self.websocket.auto_start

        return env_summary

    def get_api_environment_display(self) -> str:
        """
        Get a short human-readable API environment string for display.

        Returns:
            String like "Trading: LIVE | Keys: Trade[✓] Data[✓]"
        """
        return self.bybit.get_api_environment_display()

    def summary(self) -> str:
        """Generate a human-readable configuration summary for Unified Trading Account."""
        trade_mode = "LIVE (shadow + live modes use api.bybit.com)"
        env_display = self.bybit.get_mode_display()
        env_warning = self.bybit.get_mode_warning()

        ws_mode = "REALTIME (event-driven)" if self.websocket.is_realtime_mode else "POLLING (traditional)"

        # Check for credentials
        trading_key, _ = self.bybit.get_credentials()
        data_key, _ = self.bybit.get_data_credentials()
        live_data_key, _ = self.bybit.get_live_data_credentials()

        money_status = "⚠️  REAL MONEY AT RISK ⚠️"

        lines = [
            "=" * 55,
            "BYBIT UNIFIED TRADING ACCOUNT - CONFIGURATION",
            "=" * 55,
            "",
            "Account Type: UNIFIED (v5 API)",
            f"Environment:  {env_display}",
            f"Trading:      {trade_mode}",
            f"Status:       {money_status}",
            f"  {env_warning}",
            "",
            f"Runner: {ws_mode}",
            f"Symbols: {', '.join(self.trading.default_symbols) or '(none configured)'}",
            "",
            "Risk Settings:",
            f"  Max Leverage:    {self.risk.max_leverage}x",
            f"  Max Position:    ${self.risk.max_position_size_usdt:,.0f}",
            f"  Max Daily Loss:  ${self.risk.max_daily_loss_usd:,.0f}",
            f"  Min Balance:     ${self.risk.min_balance_usd:,.0f}",
            "",
            "API Keys (LIVE):",
            f"  Trading (R/W): {'✓ Configured' if trading_key else '✗ Missing'}",
            f"  Data (R/O):    {'✓ Configured' if data_key else '✗ Missing'}",
            f"  LIVE Data:     {'✓ Configured' if live_data_key else '✗ Missing (required for historical/market data)'}",
            "",
            "WebSocket Streams:",
            f"  Enabled: {self.websocket.enable_websocket}",
            f"  Positions: {self.websocket.enable_position_stream}",
            f"  Orders:    {self.websocket.enable_order_stream}",
            f"  Wallet:    {self.websocket.enable_wallet_stream}",
            "=" * 55,
        ]
        return "\n".join(lines)
    
    def summary_short(self) -> str:
        """Generate a short one-line configuration summary."""
        mode = self.bybit.get_mode_name()
        key_status = "✓" if self.bybit.has_credentials() else "✗"
        return f"Bybit UTA | {mode} | LIVE | API: {key_status}"


def get_config(env_file: str = ".env") -> Config:
    """Get or create the global config instance."""
    return Config(env_file)


