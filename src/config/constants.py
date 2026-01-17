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

# Generic default for data tools (backward compatibility)
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
# | exec_tf  | 1m, 3m, 5m, 15m   | Execution, entries/exits    |
# | med_tf   | 30m, 1h, 2h, 4h   | Structure, bias, swing      |
# | high_tf  | 6h, 12h, D, W, M  | Context, trend, major S/R   |

TF_CATEGORY_EXEC = ["1m", "3m", "5m", "15m"]     # exec_tf (execution)
TF_CATEGORY_MED = ["30m", "1h", "2h", "4h"]      # med_tf (structure)
TF_CATEGORY_HIGH = ["6h", "12h", "D", "W", "M"]  # high_tf (context)

# ==================== Timeframe Roles (Play Configuration) ====================
#
# Plays define timeframe roles for multi-TF strategies:
#
# | Role    | Meaning                              | Typical Values    |
# |---------|--------------------------------------|-------------------|
# | exec_tf | Bar-by-bar evaluation timeframe      | 1m, 5m, 15m       |
# | med_tf  | Mid timeframe for structure/bias     | 30m, 1h, 2h, 4h   |
# | high_tf | High timeframe for trend/context     | 6h, 12h, D        |

TF_ROLE_EXEC = ["1m", "3m", "5m", "15m"]         # Valid for exec_tf role
TF_ROLE_MED = ["30m", "1h", "2h", "4h"]          # Valid for med_tf role
TF_ROLE_HIGH = ["6h", "12h", "D"]                # Valid for high_tf role (W, M excluded)

# Mapping from role to allowed timeframes
# Note: "exec" is a role pointer (points to low_tf/med_tf/high_tf), not a TF category
TF_ROLE_GROUPS = {
    "low_tf": TF_ROLE_EXEC,   # low_tf uses exec TF category
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
