"""
Common utility functions used across the trading bot.

These helpers handle edge cases from exchange API responses.
"""

import os
import tempfile
from pathlib import Path
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


def atomic_write_text(path: Path | str, content: str) -> None:
    """Write text to a file atomically using temp-file + os.replace.

    Guarantees readers see either the old complete file or the new complete
    file, never a partial/corrupt one. Safe against crashes mid-write.

    Args:
        path: Destination file path.
        content: Text content to write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        # Clean up temp file on any failure
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def atomic_write_bytes(path: Path | str, data: bytes) -> None:
    """Write bytes to a file atomically using temp-file + os.replace.

    Same guarantees as atomic_write_text but for binary content (e.g. Parquet).

    Args:
        path: Destination file path.
        data: Binary content to write.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp", prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

