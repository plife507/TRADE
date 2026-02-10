"""
Common utility functions used across the trading bot.

These helpers handle edge cases from exchange API responses.
"""

from typing import Any


def safe_float(value: Any, default: float = 0.0) -> float:
    """
    Safely convert value to float, handling edge cases from API responses.
    
    Bybit API sometimes returns:
    - Empty strings "" instead of 0 or null
    - String numbers "123.45" instead of 123.45
    - None for optional fields
    
    Args:
        value: Value to convert (str, int, float, None, etc.)
        default: Default value if conversion fails
    
    Returns:
        Float value or default
    
    Examples:
        >>> safe_float("123.45")
        123.45
        >>> safe_float("")
        0.0
        >>> safe_float(None)
        0.0
        >>> safe_float("invalid", default=-1.0)
        -1.0
    """
    if value is None or value == "" or value == " ":
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """
    Safely convert value to int, handling edge cases from API responses.
    
    Args:
        value: Value to convert
        default: Default value if conversion fails
    
    Returns:
        Int value or default
    """
    if value is None or value == "" or value == " ":
        return default
    try:
        return int(float(value))  # Handle "123.0" -> 123
    except (ValueError, TypeError):
        return default


def safe_str(value: Any, default: str = "") -> str:
    """
    Safely convert value to string.
    
    Args:
        value: Value to convert
        default: Default value if None
    
    Returns:
        String value or default
    """
    if value is None:
        return default
    return str(value)

