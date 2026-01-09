"""
Window presets for backtesting.

Provides symbol-agnostic window definitions that can be referenced in system YAML files.
This allows defining hygiene/test and regime windows in one place without hard-coding
dates in each system config.

Usage in YAML:
    windows:
      hygiene:
        preset: hygiene_mid_tf  # Resolved via get_window_preset(symbol, tf, "hygiene_mid_tf")
      test:
        preset: test_mid_tf

Or with explicit dates (backward compatible):
    windows:
      hygiene:
        start: "2024-09-01"
        end: "2024-10-31"
"""

from datetime import datetime


# Timeframe group mappings
# Maps group names to specific tfs that belong to that group
TF_GROUPS: dict[str, list[str]] = {
    "low_tf": ["1m", "5m"],
    "mid_tf": ["15m", "1h"],
    "high_tf": ["4h", "D"],
}


def get_tf_group(tf: str) -> str:
    """
    Get the tf group for a given tf.
    
    Args:
        tf: Timeframe string (e.g., "1h", "5m")
        
    Returns:
        Group name ("low_tf", "mid_tf", "high_tf") or "mid_tf" as default
    """
    tf_lower = tf.lower()
    for group, tfs in TF_GROUPS.items():
        if tf_lower in [t.lower() for t in tfs]:
            return group
    return "mid_tf"  # Default to mid_tf


# Window presets organized by symbol -> tf_group -> preset_name -> (start, end)
# Dates are ISO format strings for clarity
# NOTE: These are fallback defaults. System YAML configs should define their own windows.
# Windows should align with available data in the database.
PRESETS: dict[str, dict[str, dict[str, tuple[str, str]]]] = {
    # Bitcoin - the reference asset
    "BTCUSDT": {
        "low_tf": {
            "hygiene": ("2025-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2025-09-30"),
        },
        "mid_tf": {
            "hygiene": ("2025-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2025-09-30"),
        },
        "high_tf": {
            "hygiene": ("2025-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2025-09-30"),
        },
    },
    
    # Ethereum
    "ETHUSDT": {
        "low_tf": {
            "hygiene": ("2025-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2025-09-30"),
        },
        "mid_tf": {
            "hygiene": ("2025-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2025-09-30"),
        },
        "high_tf": {
            "hygiene": ("2025-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2025-09-30"),
        },
    },
    
    # Solana
    "SOLUSDT": {
        "low_tf": {
            "hygiene": ("2025-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2025-09-30"),
        },
        "mid_tf": {
            "hygiene": ("2025-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2025-09-30"),
        },
        "high_tf": {
            "hygiene": ("2025-01-01", "2025-06-30"),
            "test": ("2025-07-01", "2025-09-30"),
        },
    },
}

# Default presets for symbols not explicitly defined
DEFAULT_PRESETS: dict[str, dict[str, tuple[str, str]]] = {
    "low_tf": {
        "hygiene": ("2025-01-01", "2025-06-30"),
        "test": ("2025-07-01", "2025-09-30"),
    },
    "mid_tf": {
        "hygiene": ("2025-01-01", "2025-06-30"),
        "test": ("2025-07-01", "2025-09-30"),
    },
    "high_tf": {
        "hygiene": ("2025-01-01", "2025-06-30"),
        "test": ("2025-07-01", "2025-09-30"),
    },
}


def get_window_preset(
    symbol: str,
    tf: str,
    preset_name: str,
) -> tuple[datetime, datetime]:
    """
    Get a window preset for a given symbol and tf.
    
    Resolution order:
    1. PRESETS[symbol][tf_group][preset_name]
    2. DEFAULT_PRESETS[tf_group][preset_name]
    3. Raises ValueError if not found
    
    Args:
        symbol: Trading symbol (e.g., "BTCUSDT", "SOLUSDT")
        tf: Timeframe string (e.g., "1h", "5m")
        preset_name: Preset name (e.g., "hygiene", "test")
        
    Returns:
        Tuple of (start_datetime, end_datetime)
        
    Raises:
        ValueError: If preset not found
    """
    symbol = symbol.upper()
    tf_group = get_tf_group(tf)
    
    # Try symbol-specific presets first
    if symbol in PRESETS:
        symbol_presets = PRESETS[symbol]
        if tf_group in symbol_presets:
            group_presets = symbol_presets[tf_group]
            if preset_name in group_presets:
                start_str, end_str = group_presets[preset_name]
                return datetime.fromisoformat(start_str), datetime.fromisoformat(end_str)
    
    # Fall back to defaults
    if tf_group in DEFAULT_PRESETS:
        group_presets = DEFAULT_PRESETS[tf_group]
        if preset_name in group_presets:
            start_str, end_str = group_presets[preset_name]
            return datetime.fromisoformat(start_str), datetime.fromisoformat(end_str)
    
    # Not found
    raise ValueError(
        f"Window preset '{preset_name}' not found for {symbol} {tf} (tf_group={tf_group}). "
        f"Available presets: {list_available_presets(symbol, tf)}"
    )


def list_available_presets(symbol: str, tf: str) -> list[str]:
    """
    List available preset names for a symbol and tf.
    
    Args:
        symbol: Trading symbol
        tf: Timeframe string
        
    Returns:
        List of preset names
    """
    symbol = symbol.upper()
    tf_group = get_tf_group(tf)
    presets = set()
    
    # Symbol-specific
    if symbol in PRESETS and tf_group in PRESETS[symbol]:
        presets.update(PRESETS[symbol][tf_group].keys())
    
    # Defaults
    if tf_group in DEFAULT_PRESETS:
        presets.update(DEFAULT_PRESETS[tf_group].keys())
    
    return sorted(presets)


def has_preset(symbol: str, tf: str, preset_name: str) -> bool:
    """
    Check if a preset exists for the given symbol/tf/name.
    
    Args:
        symbol: Trading symbol
        tf: Timeframe string
        preset_name: Preset name
        
    Returns:
        True if preset exists
    """
    try:
        get_window_preset(symbol, tf, preset_name)
        return True
    except ValueError:
        return False
