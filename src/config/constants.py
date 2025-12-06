"""
Centralized constants for the trading bot.

IMPORTANT: Symbols should ALWAYS be passed as explicit parameters.
- CLI: User must input the symbol
- Agents: Must provide symbol in their API calls
- Tests: Must explicitly specify test symbols

NO function should have a default symbol value.
"""

from typing import List


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


def validate_symbols(symbols: List[str]) -> List[str]:
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
