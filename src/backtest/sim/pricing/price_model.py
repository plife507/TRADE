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
"""

from dataclasses import dataclass

from ..types import Bar, PriceSnapshot
from ..bar_compat import get_bar_timestamp


@dataclass
class PriceModelConfig:
    """Configuration for price model."""
    mark_source: str = "close"  # "close", "hlc3", "ohlc4"


class PriceModel:
    """Derives mark/last/mid prices from OHLC bar data."""
    
    def __init__(self, config: PriceModelConfig | None = None):
        """
        Initialize price model.
        
        Args:
            config: Optional configuration
        """
        self._config = config or PriceModelConfig()
    
    @property
    def mark_source(self) -> str:
        """Get the configured mark price source."""
        return self._config.mark_source
    
    def get_mark_price(self, bar: Bar) -> float:
        """
        Get mark price from bar.
        
        Args:
            bar: OHLC bar
            
        Returns:
            Mark price based on configured source
            
        Raises:
            ValueError: If mark source is not supported
        """
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
        Get last traded price from bar.
        
        Always uses bar close.
        
        Args:
            bar: OHLC bar
            
        Returns:
            Last price (bar close)
        """
        return bar.close
    
    def get_mid_price(self, bar: Bar, spread: float) -> float:
        """
        Get mid price (midpoint between bid and ask).
        
        Derived from close price and spread.
        
        Args:
            bar: OHLC bar
            spread: Bid-ask spread
            
        Returns:
            Mid price
        """
        # Mid price = close (close approximates mid in liquid markets)
        return bar.close
    
    def get_prices(
        self,
        bar: Bar,
        spread: float,
    ) -> PriceSnapshot:
        """
        Get complete price snapshot for a bar.
        
        Args:
            bar: OHLC bar
            spread: Bid-ask spread
            
        Returns:
            PriceSnapshot with all price references
        """
        mark = self.get_mark_price(bar)
        last = self.get_last_price(bar)
        mid = self.get_mid_price(bar, spread)
        
        # Derive bid/ask from mid and spread
        half_spread = spread / 2.0
        bid = mid - half_spread
        ask = mid + half_spread
        
        # Get timestamp (ts_close for step time)
        timestamp = get_bar_timestamp(bar)
        
        return PriceSnapshot(
            timestamp=timestamp,
            mark_price=mark,
            last_price=last,
            mid_price=mid,
            bid_price=bid,
            ask_price=ask,
            spread=spread,
        )

