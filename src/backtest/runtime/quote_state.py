"""
Quote state for 1m-driven price feed.

Provides a closed-candle "ticker-like" quote stream derived from 1m bars.
Used as the primary price source for simulator/backtest.

Price Semantics (IMPORTANT for Live Integration):
=================================================

Two distinct price fields with different purposes:

| Field | Backtest Source         | Live Source (Future)      | Use Case              |
|-------|-------------------------|---------------------------|-----------------------|
| last  | 1m bar close            | ticker.lastPrice          | Signal evaluation     |
| mark  | 1m close OR mark kline  | ticker.markPrice          | PnL, liquidation, risk|

WHY TWO PRICES:
- last (px.last): Actual last trade price. For signal evaluation and entry/exit
  decisions. Reflects real orderbook activity on the exchange.

- mark (px.mark): Index-derived mark price. For position valuation, unrealized PnL,
  and liquidation triggers. Bybit calculates this from prices across multiple
  exchanges to prevent manipulation-triggered liquidations.

In backtest, both default to the same 1m close source for simplicity.
In live trading, they come from different WebSocket fields and CAN DIVERGE
significantly during volatile periods.

Key Design:
- QuoteState: Immutable dataclass representing the current quote at a 1m close
- px.last: Last trade proxy (1m close price) - for signal evaluation
- px.mark: Mark price for risk/liquidation - for position valuation

Invariants:
- All values from CLOSED candles only (no partial bar data)
- ts_ms is the 1m bar close timestamp
- mark_source documents provenance explicitly

Phase 2: Simulator Quote Stream (PRICE_FEED_1M_PREFLIGHT_PHASES.md)
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class QuoteState:
    """
    Point-in-time quote state derived from the most recent closed 1m bar.

    This is the "ticker proxy" for simulator/backtest. All prices come from
    closed 1m candles (no intrabar/partial data).

    Attributes:
        ts_ms: Epoch milliseconds of the 1m bar close
        last: Last-trade proxy (px.last) - 1m close price
        open_1m: 1m bar open (for rollup open price tracking)
        high_1m: 1m bar high (for zone touch detection)
        low_1m: 1m bar low (for zone touch detection)
        mark: Mark price (px.mark) for risk/liquidation
        mark_source: Provenance of mark price:
            - "mark_1m": From dedicated mark-price klines
            - "approx_from_ohlcv_1m": Approximated from 1m OHLCV close
        volume_1m: 1m bar volume (optional, for volume-based rollups)

    Usage:
        # At each exec TF close, get the most recent 1m quote
        quote = quote_builder.get_quote_at(exec_ts_close)

        # Access prices
        entry_price = quote.last      # px.last.value
        mark_price = quote.mark       # px.mark.value
        high = quote.high_1m          # px.last.high_1m
        low = quote.low_1m            # px.last.low_1m
    """

    ts_ms: int  # Epoch ms of 1m bar close
    last: float  # px.last (1m close price)
    open_1m: float  # 1m bar open (for rollup)
    high_1m: float  # 1m high
    low_1m: float  # 1m low
    mark: float  # px.mark (mark price or approximation)
    mark_source: str  # "mark_1m" | "approx_from_ohlcv_1m"
    volume_1m: float = 0.0  # Optional volume

    def __post_init__(self):
        """Validate quote state."""
        if self.ts_ms <= 0:
            raise ValueError(f"ts_ms must be positive, got {self.ts_ms}")
        if self.last <= 0:
            raise ValueError(f"last price must be positive, got {self.last}")
        if self.high_1m < self.low_1m:
            raise ValueError(
                f"high_1m ({self.high_1m}) must be >= low_1m ({self.low_1m})"
            )
        if self.mark <= 0:
            raise ValueError(f"mark price must be positive, got {self.mark}")
        if self.mark_source not in ("mark_1m", "approx_from_ohlcv_1m"):
            raise ValueError(
                f"Invalid mark_source: '{self.mark_source}'. "
                "Must be 'mark_1m' or 'approx_from_ohlcv_1m'"
            )

    @property
    def is_mark_approximated(self) -> bool:
        """Check if mark price is approximated from OHLCV."""
        return self.mark_source == "approx_from_ohlcv_1m"


# =============================================================================
# Quote Feed Constants
# =============================================================================

# Packet key namespace for quote data
# These keys are injected into the snapshot at exec TF close
QUOTE_KEYS = {
    # px.last namespace (ticker/last-trade proxy)
    "px.last.ts_ms": "Epoch ms of quote timestamp",
    "px.last.value": "Last trade price (1m close)",
    "px.last.high_1m": "1m bar high",
    "px.last.low_1m": "1m bar low",
    # px.mark namespace (mark price for risk/liquidation)
    "px.mark.ts_ms": "Epoch ms of mark price timestamp",
    "px.mark.value": "Mark price value",
    "px.mark.source": "Mark price source (mark_1m | approx_from_ohlcv_1m)",
}


def quote_to_packet_dict(quote: QuoteState) -> dict:
    """
    Convert QuoteState to packet dict for snapshot injection.

    Returns dict with px.last.* and px.mark.* keys.

    Args:
        quote: QuoteState to convert

    Returns:
        Dict with standardized packet keys
    """
    return {
        "px.last.ts_ms": quote.ts_ms,
        "px.last.value": quote.last,
        "px.last.high_1m": quote.high_1m,
        "px.last.low_1m": quote.low_1m,
        "px.mark.ts_ms": quote.ts_ms,
        "px.mark.value": quote.mark,
        "px.mark.source": quote.mark_source,
    }
