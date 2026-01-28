"""
Data adapters for the simulated exchange.

Converts external data formats (DuckDB rows, pandas) to exchange types.
"""

from .ohlcv_adapter import (
    adapt_ohlcv_row_canonical,
    adapt_ohlcv_dataframe_canonical,
    adapt_ohlcv_row,
    adapt_ohlcv_dataframe,
    build_bar_close_ts_map,
)
from .funding_adapter import adapt_funding_dataframe

__all__ = [
    # Canonical adapters (preferred)
    "adapt_ohlcv_row_canonical",
    "adapt_ohlcv_dataframe_canonical",
    "build_bar_close_ts_map",
    # Aliases for backward compatibility
    "adapt_ohlcv_row",
    "adapt_ohlcv_dataframe",
    # Funding adapters
    "adapt_funding_dataframe",
]

