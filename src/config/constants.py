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

# DataEnv: Identifies which market data environment we're working with.
# This is SEPARATE from:
#   - TRADING_MODE (paper/real) - controls order execution
#   - BYBIT_USE_DEMO (true/false) - controls which Bybit API endpoint for trading
#
# DataEnv controls which historical data store (DuckDB file) is used:
#   - "live": Canonical live market history for research/backtests/live trading warm-up
#   - "demo": Demo-only market history for demo session warm-up and testing
DataEnv = Literal["live", "demo"]

# Valid data environments
DATA_ENVS: list[DataEnv] = ["live", "demo"]

# Default data environment (always use live for research/backtest)
DEFAULT_DATA_ENV: DataEnv = "live"


def validate_data_env(env: str) -> DataEnv:
    """
    Validate and normalize a data environment string.
    
    Args:
        env: The environment to validate (e.g., "live", "DEMO")
        
    Returns:
        Normalized DataEnv ("live" or "demo")
        
    Raises:
        ValueError: If env is not a valid data environment
    """
    normalized = env.lower().strip()
    if normalized not in DATA_ENVS:
        raise ValueError(f"Invalid data environment: '{env}'. Must be 'live' or 'demo'.")
    return cast(DataEnv, normalized)


# ==================== DuckDB Path and Table Mapping ====================

# Base directory for data files (relative to project root)
DATA_DIR = Path("data")

# DuckDB file names per environment
DB_FILENAMES = {
    "live": "market_data_live.duckdb",
    "demo": "market_data_demo.duckdb",
}

# Table name suffixes per environment
TABLE_SUFFIXES = {
    "live": "_live",
    "demo": "_demo",
}


def resolve_db_path(env: DataEnv) -> Path:
    """
    Get the DuckDB file path for a given data environment.
    
    Args:
        env: Data environment ("live" or "demo")
        
    Returns:
        Path to the DuckDB file (e.g., data/market_data_live.duckdb)
    """
    env = validate_data_env(env)
    return DATA_DIR / DB_FILENAMES[env]


def resolve_table_name(base_table: str, env: DataEnv) -> str:
    """
    Get the table name for a given base table and environment.
    
    Args:
        base_table: Base table name (e.g., "ohlcv", "funding_rates", "open_interest")
        env: Data environment ("live" or "demo")
        
    Returns:
        Full table name with env suffix (e.g., "ohlcv_live", "funding_rates_demo")
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

# Common timeframe strings for reference
TIMEFRAMES = {
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
    "1d": "D",
    "1w": "W",
    "1M": "M",
}

DEFAULT_TIMEFRAME = "15m"

# ==================== Timeframe Groups (for Play validation) ====================
# These define which timeframes are valid for each role

TF_GROUP_LTF = ["1m", "3m", "5m"]         # LTF (high-resolution)
TF_GROUP_MTF = ["15m", "30m"]             # MTF (medium resolution)
TF_GROUP_HTF = ["1h", "4h", "1d"]         # HTF (low resolution)

# All valid timeframes for backtesting
ALL_BACKTEST_TIMEFRAMES = TF_GROUP_LTF + TF_GROUP_MTF + TF_GROUP_HTF

# Mapping from role to allowed timeframe groups
TF_ROLE_GROUPS = {
    "ltf": TF_GROUP_LTF,    # Low timeframe: 1m, 3m, 5m
    "mtf": TF_GROUP_MTF,    # Medium timeframe: 15m, 30m
    "htf": TF_GROUP_HTF,    # High timeframe: 1h, 4h, 1d
    "exec": ALL_BACKTEST_TIMEFRAMES,  # Execution can be any valid TF
}
