"""
Price model for mark/last/mid derivation.

Derives price references from OHLC data:
- Mark price: Configurable proxy (close, hlc3, ohlc4)
- Last price: Bar close
- Mid price: (bid + ask) / 2

Mark price sources:
- "close": Use bar close (default)
- "hlc3": (high + low + close) / 3
- "ohlc4": (open + high + low + close) / 4

External price override (shadow mode):
- set_external_prices() feeds real WS mark/last/index prices
- When set, get_prices() returns external values instead of OHLC-derived
- clear_external_prices() reverts to OHLC derivation
"""

from dataclasses import dataclass

from ..types import Bar, PriceSnapshot


@dataclass
class PriceModelConfig:
    """Configuration for price model."""
    mark_source: str = "close"  # "close", "hlc3", "ohlc4"


class PriceModel:
    """Derives mark/last/mid prices from OHLC bar data.

    In backtest mode, all prices are derived from OHLC bars.
    In shadow mode, external prices from WS override mark/last/index.
    """

    def __init__(self, config: PriceModelConfig | None = None):
        """
        Initialize price model.

        Args:
            config: Optional configuration
        """
        self._config = config or PriceModelConfig()
        # External price overrides (shadow mode)
        self._external_mark: float | None = None
        self._external_last: float | None = None
        self._external_index: float | None = None

    @property
    def mark_source(self) -> str:
        """Get the configured mark price source."""
        if self._external_mark is not None:
            return "external"
        return self._config.mark_source

    @property
    def has_external_prices(self) -> bool:
        """True if external prices have been set (shadow mode)."""
        return self._external_mark is not None

    def set_external_prices(
        self,
        mark_price: float | None = None,
        last_price: float | None = None,
        index_price: float | None = None,
    ) -> None:
        """Set external price overrides from WS feed.

        When set, get_prices() uses these instead of deriving from OHLC.
        Call once per bar with the latest WS values. Any None value
        leaves the previous override in place (sticky).

        Args:
            mark_price: Exchange mark price from WS ticker
            last_price: Last traded price from WS ticker
            index_price: Spot index price from WS ticker
        """
        if mark_price is not None:
            self._external_mark = mark_price
        if last_price is not None:
            self._external_last = last_price
        if index_price is not None:
            self._external_index = index_price

    def clear_external_prices(self) -> None:
        """Clear external overrides, revert to OHLC derivation."""
        self._external_mark = None
        self._external_last = None
        self._external_index = None

    def get_mark_price(self, bar: Bar) -> float:
        """
        Get mark price.

        Returns external override if set (shadow mode),
        otherwise derives from OHLC bar.

        Args:
            bar: OHLC bar

        Returns:
            Mark price

        Raises:
            ValueError: If mark source is not supported
        """
        if self._external_mark is not None:
            return self._external_mark

        source = self._config.mark_source

        if source == "close":
            return bar.close
        elif source == "hlc3":
            return (bar.high + bar.low + bar.close) / 3.0
        elif source == "ohlc4":
            return (bar.open + bar.high + bar.low + bar.close) / 4.0
        else:
            raise ValueError(
                f"Unsupported mark_source='{source}'. "
                "Supported: close, hlc3, ohlc4"
            )

    def get_last_price(self, bar: Bar) -> float:
        """
        Get last traded price.

        Returns external override if set (shadow mode),
        otherwise uses bar close.

        Args:
            bar: OHLC bar

        Returns:
            Last price
        """
        if self._external_last is not None:
            return self._external_last
        return bar.close

    def get_index_price(self, bar: Bar) -> float:
        """
        Get spot index price.

        Returns external override if set (shadow mode),
        otherwise falls back to mark price (best available proxy).

        Args:
            bar: OHLC bar

        Returns:
            Index price
        """
        if self._external_index is not None:
            return self._external_index
        # In backtest mode, no index price available — use mark as proxy
        return self.get_mark_price(bar)

    def get_mid_price(self, bar: Bar, spread: float) -> float:
        """
        Get mid price (midpoint between bid and ask).

        Derived from last price and spread.

        Args:
            bar: OHLC bar
            spread: Bid-ask spread

        Returns:
            Mid price
        """
        return self.get_last_price(bar)

    def get_prices(
        self,
        bar: Bar,
        spread: float,
    ) -> PriceSnapshot:
        """
        Get complete price snapshot for a bar.

        When external prices are set (shadow mode), uses those.
        Otherwise derives all prices from OHLC bar.

        Args:
            bar: OHLC bar
            spread: Bid-ask spread

        Returns:
            PriceSnapshot with all price references
        """
        mark = self.get_mark_price(bar)
        last = self.get_last_price(bar)
        index = self.get_index_price(bar)
        mid = self.get_mid_price(bar, spread)

        # Derive bid/ask from mid and spread
        half_spread = spread / 2.0
        bid = mid - half_spread
        ask = mid + half_spread

        # Get timestamp (ts_close for step time)
        timestamp = bar.ts_close

        return PriceSnapshot(
            timestamp=timestamp,
            mark_price=mark,
            last_price=last,
            index_price=index,
            mid_price=mid,
            bid_price=bid,
            ask_price=ask,
            spread=spread,
        )

