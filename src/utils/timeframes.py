"""
Canonical timeframe constants and validation.

Single source of truth for timeframe definitions used across CLI, tools, and engine.
"""


# Canonical timeframes accepted by CLI (stored in DuckDB as-is)
# Full Bybit-supported set: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 4h, 6h, 12h, D
# NOTE: 8h is NOT a valid Bybit interval - use 6h or 12h instead
CANONICAL_TIMEFRAMES = {"1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "D"}

# Bybit API intervals (numeric format for sub-daily)
BYBIT_API_INTERVALS = {"1", "3", "5", "15", "30", "60", "120", "240", "360", "720", "D"}

# Mapping from Bybit API numeric interval to canonical
BYBIT_TO_CANONICAL = {
    "1": "1m",
    "3": "3m",
    "5": "5m",
    "15": "15m",
    "30": "30m",
    "60": "1h",
    "120": "2h",
    "240": "4h",
    "360": "6h",
    "720": "12h",
    "D": "D",
}


def validate_canonical_tf(tf: str) -> str:
    """
    Validate timeframe is canonical format.

    Args:
        tf: Timeframe string (e.g., "1h", "15m")

    Returns:
        Validated canonical tf string

    Raises:
        ValueError: If tf is not canonical (with fix-it message)
    """
    tf_clean = tf.strip()

    # H-C3: Check original case first — "D" is canonical but "d".lower() isn't in the set
    if tf_clean in CANONICAL_TIMEFRAMES:
        return tf_clean

    # Try lowercase for case-insensitive matching (e.g. "1H" → "1h")
    tf_lower = tf_clean.lower()
    if tf_lower in CANONICAL_TIMEFRAMES:
        return tf_lower

    # "d" is commonly typed but canonical is "D"
    if tf_lower == "d":
        return "D"

    # Check if it's a Bybit API interval
    if tf in BYBIT_API_INTERVALS:
        canonical = BYBIT_TO_CANONICAL.get(tf, tf)
        raise ValueError(
            f"Timeframe '{tf}' is a Bybit API interval, not canonical. "
            f"Use '{canonical}' instead. "
            f"Canonical timeframes: {sorted(CANONICAL_TIMEFRAMES)}"
        )

    raise ValueError(
        f"Invalid timeframe: '{tf}'. "
        f"Must be one of: {sorted(CANONICAL_TIMEFRAMES)}"
    )
