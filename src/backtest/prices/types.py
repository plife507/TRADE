"""
Price Engine Types.

Enums and dataclasses for the price engine layer.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class PriceRef(str, Enum):
    """
    Supported price references.

    MARK is always available (implicit, never declared in IdeaCard).
    LAST is reserved for future use.
    """

    MARK = "mark"  # Mark price (always available)
    LAST = "last"  # Last traded price (reserved, not implemented)


@dataclass(frozen=True)
class HealthCheckResult:
    """Result of a price engine health check."""

    ok: bool
    provider_name: str
    message: str
    details: Optional[dict] = None

    def __bool__(self) -> bool:
        return self.ok


@dataclass(frozen=True)
class MarkPriceResult:
    """Result of a mark price query."""

    value: float
    source: str  # e.g., "backtest_exec_close"
    ts_close_ms: int  # Timestamp of the exec bar close
