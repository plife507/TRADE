"""
Canonical type definitions for the unified engine.

Provides normalized types that work across backtest, shadow, and live modes.
"""

from enum import Enum


class PositionSide(str, Enum):
    """
    Canonical position side enum.

    Normalizes various representations:
    - "LONG", "long", "Long" -> LONG
    - "SHORT", "short", "Short" -> SHORT
    - "BUY", "buy" -> LONG (exchange convention)
    - "SELL", "sell" -> SHORT (exchange convention)
    """

    LONG = "LONG"
    SHORT = "SHORT"

    @classmethod
    def from_any(cls, value: str | "PositionSide") -> "PositionSide":
        """
        Convert any position side representation to canonical enum.

        Args:
            value: String or enum representing position side

        Returns:
            Normalized PositionSide enum

        Raises:
            ValueError: If value cannot be interpreted as a position side
        """
        if isinstance(value, PositionSide):
            return value

        if isinstance(value, str):
            upper_val = value.upper()

            # Direct matches
            if upper_val in ("LONG", "BUY"):
                return cls.LONG
            if upper_val in ("SHORT", "SELL"):
                return cls.SHORT

        raise ValueError(
            f"Cannot convert '{value}' to PositionSide. "
            f"Expected: LONG, SHORT, BUY, SELL (case-insensitive)"
        )

    @property
    def is_long(self) -> bool:
        """Check if this is a long position."""
        return self == PositionSide.LONG

    @property
    def is_short(self) -> bool:
        """Check if this is a short position."""
        return self == PositionSide.SHORT

    @property
    def opposite(self) -> "PositionSide":
        """Get the opposite side."""
        return PositionSide.SHORT if self == PositionSide.LONG else PositionSide.LONG

    def to_order_side(self) -> str:
        """Convert to order side (BUY/SELL) for exchange APIs."""
        return "BUY" if self == PositionSide.LONG else "SELL"

    def __str__(self) -> str:
        return self.value
