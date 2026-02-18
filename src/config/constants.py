"""
Centralized constants for the trading bot.

IMPORTANT: Symbols should ALWAYS be passed as explicit parameters.
- CLI: User must input the symbol
- Agents: Must provide symbol in their API calls
- Tests: Must explicitly specify test symbols

NO function should have a default symbol value.
"""

from typing import Literal, cast
from pathlib import Path


# ==================== Trading Environment ====================

# TradingEnv: Identifies which trading API environment we're targeting.
# This maps to the combination of:
#   - BYBIT_USE_DEMO (true/false) - controls which Bybit API endpoint
#   - TRADING_MODE (paper/real) - controls order execution style
#
# ONLY two valid combinations are allowed (enforced at startup):
#   - "demo" -> BYBIT_USE_DEMO=true, TRADING_MODE=paper (fake money on api-demo.bybit.com)
#   - "live" -> BYBIT_USE_DEMO=false, TRADING_MODE=real (real money on api.bybit.com)
#
# NOTE: TradingEnv is used by agents/tools to VALIDATE intent, not to switch env.
# A running process has a fixed trading env set at startup. If an agent requests
# a different trading_env than the process is configured for, the tool returns an error.
TradingEnv = Literal["demo", "live"]

# Valid trading environments
TRADING_ENVS: list[TradingEnv] = ["demo", "live"]


def validate_trading_env(env: str) -> TradingEnv:
    """
    Validate and normalize a trading environment string.
    
    Args:
        env: The environment to validate (e.g., "live", "DEMO")
        
    Returns:
        Normalized TradingEnv ("live" or "demo")
        
    Raises:
        ValueError: If env is not a valid trading environment
    """
    normalized = env.lower().strip()
    if normalized not in TRADING_ENVS:
        raise ValueError(f"Invalid trading environment: '{env}'. Must be 'live' or 'demo'.")
    return cast(TradingEnv, normalized)


def get_trading_env_mapping() -> dict:
    """
    Return documentation of how TradingEnv maps to config settings.
    
    Returns:
        Dict with "demo" and "live" keys, each containing expected config values
    """
    return {
        "demo": {
            "description": "Demo trading with fake money",
            "api_endpoint": "api-demo.bybit.com",
            "use_demo": True,
            "trading_mode": "paper",
        },
        "live": {
            "description": "Live trading with real money",
            "api_endpoint": "api.bybit.com",
            "use_demo": False,
            "trading_mode": "real",
        },
    }


# ==================== Data Environment ====================
#
# Three separate databases for concurrent operations:
#
# | Database  | API Source         | Purpose                              |
# |-----------|--------------------|--------------------------------------|
# | backtest  | api.bybit.com      | Historical backtests (read-heavy)    |
# | demo      | api-demo.bybit.com | Paper trading (demo feed)            |
# | live      | api.bybit.com      | Live trading warm-up (real-time)     |
#
# Why separate backtest from live (both use api.bybit.com)?
# - Backtests are long-running, read-heavy operations
# - Live trading needs real-time writes for warm-up
# - DuckDB has no concurrent write access
# - Separate files allow backtest + live trading simultaneously

DataEnv = Literal["backtest", "live", "demo"]

# Valid data environments
DATA_ENVS: list[DataEnv] = ["backtest", "live", "demo"]

# Default for backtests (uses live API data, separate DB for concurrency)
DEFAULT_BACKTEST_ENV: DataEnv = "backtest"

# Default for live trading warm-up
DEFAULT_LIVE_ENV: DataEnv = "live"

# Default for demo/paper trading
DEFAULT_DEMO_ENV: DataEnv = "demo"

# Generic default for data tools
# Points to "backtest" since most data operations are for preparing backtest data
DEFAULT_DATA_ENV: DataEnv = "backtest"


def validate_data_env(env: str) -> DataEnv:
    """
    Validate and normalize a data environment string.

    Args:
        env: The environment to validate (e.g., "live", "DEMO", "backtest")

    Returns:
        Normalized DataEnv ("backtest", "live", or "demo")

    Raises:
        ValueError: If env is not a valid data environment
    """
    normalized = env.lower().strip()
    if normalized not in DATA_ENVS:
        raise ValueError(f"Invalid data environment: '{env}'. Must be 'backtest', 'live', or 'demo'.")
    return cast(DataEnv, normalized)


# ==================== DuckDB Path and Table Mapping ====================
#
# Three separate databases to enable concurrent operations:
#
# | Database                      | Data Source        | Purpose                    |
# |-------------------------------|--------------------|----------------------------|
# | market_data_backtest.duckdb   | api.bybit.com      | Backtests (most accurate)  |
# | market_data_demo.duckdb       | api-demo.bybit.com | Paper trading (demo feed)  |
# | market_data_live.duckdb       | api.bybit.com      | Live trading warm-up       |
#
# Why 3 DBs?
# - Backtest uses LIVE data (more accurate) but is read-heavy with long runs
# - Demo trading needs its own feed from api-demo.bybit.com (similar but not exact)
# - Live trading needs real-time writes for warm-up
# - DuckDB has no concurrent write access - separate files solve this
#
# This allows: backtest + demo trading + live trading to run simultaneously

# Base directory for data files (relative to project root)
DATA_DIR = Path("data")

# DuckDB file names per environment
DB_FILENAMES: dict[DataEnv, str] = {
    "backtest": "market_data_backtest.duckdb",  # Live data for backtests
    "demo": "market_data_demo.duckdb",          # Demo data for paper trading
    "live": "market_data_live.duckdb",          # Live data for live trading warm-up
}

# Data source per database (which API endpoint feeds it)
DB_DATA_SOURCES: dict[DataEnv, str] = {
    "backtest": "api.bybit.com",      # Live API (most accurate)
    "demo": "api-demo.bybit.com",     # Demo API (paper trading feed)
    "live": "api.bybit.com",          # Live API (real-time warm-up)
}

# Table name suffixes per environment
# NOTE: "backtest" uses "_live" suffix because it contains live API data
TABLE_SUFFIXES: dict[DataEnv, str] = {
    "backtest": "_live",  # Backtest DB contains live data, uses _live tables
    "live": "_live",
    "demo": "_demo",
}


def resolve_db_path(env: DataEnv) -> Path:
    """
    Get the DuckDB file path for a given environment.

    Args:
        env: Data environment ("backtest", "live", or "demo")

    Returns:
        Path to the DuckDB file (e.g., data/market_data_backtest.duckdb)
    """
    env = validate_data_env(env)
    return DATA_DIR / DB_FILENAMES[env]


def resolve_table_name(base_table: str, env: DataEnv) -> str:
    """
    Get the table name for a given base table and environment.

    Args:
        base_table: Base table name (e.g., "ohlcv", "funding_rates", "open_interest")
        env: Data environment ("backtest", "live", or "demo")

    Returns:
        Full table name with env suffix (e.g., "ohlcv_live", "funding_rates_demo")
        Note: "backtest" env uses "_live" suffix since it contains live API data
    """
    env = validate_data_env(env)
    return f"{base_table}{TABLE_SUFFIXES[env]}"


# ==================== Symbol Reference (Display Only) ====================

# COMMON_SYMBOLS: Used ONLY for display/suggestions in prompts
# These are NOT defaults - just helpful suggestions for users
COMMON_SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]


def validate_symbol(symbol: str) -> str:
    """
    Validate and normalize a symbol string.
    
    Args:
        symbol: The symbol to validate (e.g., "btcusdt", "BTC/USDT")
        
    Returns:
        Normalized symbol (uppercase, no slashes)
        
    Raises:
        ValueError: If symbol is empty or invalid
    """
    if not symbol:
        raise ValueError("Symbol is required - it must be explicitly provided")
    
    # Normalize: uppercase, remove slashes and whitespace
    normalized = symbol.strip().upper().replace("/", "")
    
    if not normalized:
        raise ValueError(f"Invalid symbol: '{symbol}'")
    
    return normalized


def validate_symbols(symbols: list[str]) -> list[str]:
    """
    Validate and normalize a list of symbols.
    
    Args:
        symbols: List of symbols to validate
        
    Returns:
        List of normalized symbols
        
    Raises:
        ValueError: If symbols list is empty or contains invalid symbols
    """
    if not symbols:
        raise ValueError("At least one symbol is required - symbols must be explicitly provided")
    
    return [validate_symbol(s) for s in symbols]


def format_symbol_prompt() -> str:
    """
    Format a user prompt for symbol input (no default).
    
    Returns:
        Formatted prompt string
    """
    suggestions = ", ".join(COMMON_SYMBOLS[:4])
    return f"Enter symbol ({suggestions}): "


def format_symbols_prompt() -> str:
    """
    Format a user prompt for multiple symbols input.
    
    Returns:
        Formatted prompt string
    """
    suggestions = ", ".join(COMMON_SYMBOLS[:3])
    return f"Enter symbols, comma-separated ({suggestions}): "


# ==================== Timeframe Constants ====================
#
# Bybit API intervals: 1,3,5,15,30,60,120,240,360,720,D,W,M
# Internal format:     1m,3m,5m,15m,30m,1h,2h,4h,6h,12h,D,W,M
#
# NOTE: 8h is NOT a valid Bybit interval - do not use it.

# Internal -> Bybit API mapping
TIMEFRAME_TO_BYBIT = {
    "1m": "1",
    "3m": "3",
    "5m": "5",
    "15m": "15",
    "30m": "30",
    "1h": "60",
    "2h": "120",
    "4h": "240",
    "6h": "360",
    "12h": "720",
    "D": "D",
    "W": "W",
    "M": "M",
}

# Bybit API -> Internal mapping
BYBIT_TO_TIMEFRAME = {v: k for k, v in TIMEFRAME_TO_BYBIT.items()}

# All valid timeframes (internal format)
ALL_TIMEFRAMES = list(TIMEFRAME_TO_BYBIT.keys())

# Minutes per timeframe
TIMEFRAME_MINUTES = {
    "1m": 1,
    "3m": 3,
    "5m": 5,
    "15m": 15,
    "30m": 30,
    "1h": 60,
    "2h": 120,
    "4h": 240,
    "6h": 360,
    "12h": 720,
    "D": 1440,
    "W": 10080,
    "M": 43200,  # ~30 days
}

DEFAULT_TIMEFRAME = "15m"

# ==================== Timeframe Categories ====================
#
# Three-tier categorization for multi-timeframe trading:
#
# | Category | Timeframes        | Use Case                    |
# |----------|-------------------|-----------------------------|
# | low_tf   | 1m, 3m, 5m, 15m   | Execution, entries/exits    |
# | med_tf   | 30m, 1h, 2h, 4h   | Structure, bias, swing      |
# | high_tf  | 6h, 12h, D, W, M  | Context, trend, major S/R   |

TF_CATEGORY_LOW = ["1m", "3m", "5m", "15m"]      # low_tf (execution-level)
TF_CATEGORY_MED = ["30m", "1h", "2h", "4h"]      # med_tf (structure)
TF_CATEGORY_HIGH = ["6h", "12h", "D", "W", "M"]  # high_tf (context)

# ==================== Timeframe Roles (Play Configuration) ====================
#
# Plays define timeframe roles for multi-TF strategies:
#
# | Role    | Meaning                              | Typical Values    |
# |---------|--------------------------------------|-------------------|
# | low_tf  | Fast timeframe for entries/exits     | 1m, 5m, 15m       |
# | med_tf  | Mid timeframe for structure/bias     | 30m, 1h, 2h, 4h   |
# | high_tf | High timeframe for trend/context     | 6h, 12h, D        |
# | exec    | POINTER to which TF to step on       | "low_tf", etc.    |

TF_ROLE_LOW = ["1m", "3m", "5m", "15m"]          # Valid for low_tf role
TF_ROLE_MED = ["30m", "1h", "2h", "4h"]          # Valid for med_tf role
TF_ROLE_HIGH = ["6h", "12h", "D"]                # Valid for high_tf role (W, M excluded)

# Mapping from role to allowed timeframes
# Note: "exec" is a role pointer (points to low_tf/med_tf/high_tf), not a TF value
TF_ROLE_GROUPS = {
    "low_tf": TF_ROLE_LOW,
    "med_tf": TF_ROLE_MED,
    "high_tf": TF_ROLE_HIGH,
}

# ==================== Common Presets ====================

# Standard backtest timeframes (most commonly used)
BACKTEST_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "D"]

# Smoke test timeframes (quick validation)
SMOKE_TEST_TIMEFRAMES = ["1h", "4h", "D"]

# Data sync timeframes (full history)
DATA_SYNC_TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "D"]


# ==================== System Defaults (from config/defaults.yml) ====================
#
# Single source of truth for all default values.
# Loaded once at module import time.
# All code should reference these instead of hardcoding values.

import yaml
from dataclasses import dataclass
from functools import lru_cache


@dataclass(frozen=True)
class FeeDefaults:
    """Fee defaults from config/defaults.yml."""
    taker_bps: float
    maker_bps: float
    liquidation_bps: float

    @property
    def taker_rate(self) -> float:
        """Taker fee as decimal (e.g., 0.00055 for 5.5 bps)."""
        return self.taker_bps / 10000.0

    @property
    def maker_rate(self) -> float:
        """Maker fee as decimal."""
        return self.maker_bps / 10000.0

    @property
    def liquidation_rate(self) -> float:
        """Liquidation fee as decimal."""
        return self.liquidation_bps / 10000.0


@dataclass(frozen=True)
class MarginDefaults:
    """Margin defaults from config/defaults.yml."""
    mode: str
    position_mode: str
    maintenance_margin_rate: float
    mm_deduction: float
    mark_price_source: str


@dataclass(frozen=True)
class ExecutionDefaults:
    """Execution defaults from config/defaults.yml."""
    slippage_bps: float
    min_trade_notional_usdt: float


@dataclass(frozen=True)
class RiskDefaults:
    """Risk defaults from config/defaults.yml."""
    max_leverage: float
    risk_per_trade_pct: float
    max_drawdown_pct: float
    stop_equity_usdt: float
    max_position_equity_pct: float
    reserve_fee_buffer: bool
    max_daily_loss_usdt: float
    max_funding_cost_pct: float


@dataclass(frozen=True)
class AccountDefaults:
    """Account defaults from config/defaults.yml."""
    starting_equity_usdt: float


@dataclass(frozen=True)
class EngineDefaults:
    """Engine defaults from config/defaults.yml."""
    warmup_bars: int
    state_save_interval: int
    max_warmup_bars: int


@dataclass(frozen=True)
class WindowingDefaults:
    """Windowing defaults from config/defaults.yml."""
    high_tf_safety_closes: int
    med_tf_safety_closes: int
    max_window_bars: int


@dataclass(frozen=True)
class ImpactDefaults:
    """Impact model defaults from config/defaults.yml."""
    max_impact_bps: float


@dataclass(frozen=True)
class PositionPolicyDefaults:
    """Position policy defaults from config/defaults.yml."""
    mode: str
    exit_mode: str
    max_positions_per_symbol: int


@dataclass(frozen=True)
class SystemDefaults:
    """All system defaults loaded from config/defaults.yml."""
    fees: FeeDefaults
    margin: MarginDefaults
    execution: ExecutionDefaults
    risk: RiskDefaults
    account: AccountDefaults
    engine: EngineDefaults
    windowing: WindowingDefaults
    impact: ImpactDefaults
    position_policy: PositionPolicyDefaults
    exchange_name: str
    instrument_type: str
    quote_ccy: str


@lru_cache(maxsize=1)
def load_system_defaults() -> SystemDefaults:
    """
    Load system defaults from config/defaults.yml.

    Cached - only reads file once.

    Returns:
        SystemDefaults with all default values

    Raises:
        FileNotFoundError: If defaults.yml not found
        ValueError: If defaults.yml is invalid
    """
    # Find config/defaults.yml relative to this file
    config_dir = Path(__file__).parent.parent.parent / "config"
    defaults_path = config_dir / "defaults.yml"

    if not defaults_path.exists():
        raise FileNotFoundError(
            f"System defaults not found: {defaults_path}\n"
            "This file is required - it contains all default values for the system."
        )

    with open(defaults_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    if not data:
        raise ValueError(f"Empty or invalid defaults file: {defaults_path}")

    # Validate all required sections exist
    required_sections = [
        "fees", "margin", "execution", "risk", "account",
        "engine", "windowing", "impact", "position_policy", "exchange",
    ]
    missing = [s for s in required_sections if s not in data]
    if missing:
        raise ValueError(
            f"defaults.yml missing required sections: {missing}. "
            "All sections must be present — no silent fallbacks."
        )

    return SystemDefaults(
        fees=FeeDefaults(
            taker_bps=float(data["fees"]["taker_bps"]),
            maker_bps=float(data["fees"]["maker_bps"]),
            liquidation_bps=float(data["fees"]["liquidation_bps"]),
        ),
        margin=MarginDefaults(
            mode=str(data["margin"]["mode"]),
            position_mode=str(data["margin"]["position_mode"]),
            maintenance_margin_rate=float(data["margin"]["maintenance_margin_rate"]),
            mm_deduction=float(data["margin"]["mm_deduction"]),
            mark_price_source=str(data["margin"]["mark_price_source"]),
        ),
        execution=ExecutionDefaults(
            slippage_bps=float(data["execution"]["slippage_bps"]),
            min_trade_notional_usdt=float(data["execution"]["min_trade_notional_usdt"]),
        ),
        risk=RiskDefaults(
            max_leverage=float(data["risk"]["max_leverage"]),
            risk_per_trade_pct=float(data["risk"]["risk_per_trade_pct"]),
            max_drawdown_pct=float(data["risk"]["max_drawdown_pct"]),
            stop_equity_usdt=float(data["risk"]["stop_equity_usdt"]),
            max_position_equity_pct=float(data["risk"]["max_position_equity_pct"]),
            reserve_fee_buffer=bool(data["risk"]["reserve_fee_buffer"]),
            max_daily_loss_usdt=float(data["risk"]["max_daily_loss_usdt"]),
            max_funding_cost_pct=float(data["risk"]["max_funding_cost_pct"]),
        ),
        account=AccountDefaults(
            starting_equity_usdt=float(data["account"]["starting_equity_usdt"]),
        ),
        engine=EngineDefaults(
            warmup_bars=int(data["engine"]["warmup_bars"]),
            state_save_interval=int(data["engine"]["state_save_interval"]),
            max_warmup_bars=int(data["engine"]["max_warmup_bars"]),
        ),
        windowing=WindowingDefaults(
            high_tf_safety_closes=int(data["windowing"]["high_tf_safety_closes"]),
            med_tf_safety_closes=int(data["windowing"]["med_tf_safety_closes"]),
            max_window_bars=int(data["windowing"]["max_window_bars"]),
        ),
        impact=ImpactDefaults(
            max_impact_bps=float(data["impact"]["max_impact_bps"]),
        ),
        position_policy=PositionPolicyDefaults(
            mode=str(data["position_policy"]["mode"]),
            exit_mode=str(data["position_policy"]["exit_mode"]),
            max_positions_per_symbol=int(data["position_policy"]["max_positions_per_symbol"]),
        ),
        exchange_name=str(data["exchange"]["name"]),
        instrument_type=str(data["exchange"]["instrument_type"]),
        quote_ccy=str(data["exchange"]["quote_ccy"]),
    )


# Load defaults at module import time
# This ensures the file is valid and provides fast access
DEFAULTS = load_system_defaults()
