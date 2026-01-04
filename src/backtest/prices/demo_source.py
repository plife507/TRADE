"""
Demo Price Source (Stub).

Implements PriceSource protocol for demo mode (api-demo.bybit.com).
Currently a stub - raises NotImplementedError for unimplemented methods.

Future Implementation (W5):
- WebSocket connection to demo API
- Real-time price updates
- Same interface as BacktestPriceSource
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from src.backtest.prices.source import PriceSource, DataNotAvailableError
from src.backtest.prices.types import HealthCheckResult

if TYPE_CHECKING:
    import pandas as pd


class DemoPriceSource:
    """
    Price source for demo mode (STUB).

    This is a placeholder implementation that will be completed in W5.
    Uses api-demo.bybit.com for demo trading with fake funds.

    When implemented:
    - WebSocket connection for real-time prices
    - Historical data from demo API
    - Same interface as BacktestPriceSource
    """

    SOURCE_NAME = "demo_ws"

    def __init__(self) -> None:
        """Initialize demo source (stub)."""
        pass

    @property
    def source_name(self) -> str:
        """Unique name identifying this source."""
        return self.SOURCE_NAME

    def get_mark_price(self, symbol: str, ts: datetime) -> float | None:
        """Get mark price at a specific timestamp (NOT IMPLEMENTED)."""
        raise NotImplementedError(
            "DemoPriceSource.get_mark_price not implemented. "
            "Use BacktestPriceSource for backtest mode."
        )

    def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
    ) -> "pd.DataFrame":
        """Get OHLCV data (NOT IMPLEMENTED)."""
        raise NotImplementedError(
            "DemoPriceSource.get_ohlcv not implemented. "
            "Use BacktestPriceSource for backtest mode."
        )

    def get_1m_marks(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
    ) -> np.ndarray:
        """Get 1-minute mark prices (NOT IMPLEMENTED)."""
        raise NotImplementedError(
            "DemoPriceSource.get_1m_marks not implemented. "
            "Use BacktestPriceSource for backtest mode."
        )

    def healthcheck(self) -> HealthCheckResult:
        """Check if source is ready (stub returns not ready)."""
        return HealthCheckResult(
            ok=False,
            provider_name=self.SOURCE_NAME,
            message="Demo source not implemented (W5)",
        )
