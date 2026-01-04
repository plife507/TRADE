"""
Live Price Source (Stub).

Implements PriceSource protocol for live mode (api.bybit.com).
Currently a stub - raises NotImplementedError for unimplemented methods.

Future Implementation (W5):
- WebSocket connection to live API
- Real-time price updates
- Mark price from funding rate data
- Integration with BybitClient for authenticated access
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import numpy as np

from src.backtest.prices.source import PriceSource, DataNotAvailableError
from src.backtest.prices.types import HealthCheckResult

if TYPE_CHECKING:
    import pandas as pd
    from src.exchanges.bybit_client import BybitClient


class LivePriceSource:
    """
    Price source for live mode (STUB).

    This is a placeholder implementation that will be completed in W5.
    Uses api.bybit.com for live trading with real funds.

    When implemented:
    - WebSocket connection for real-time prices
    - Mark price from exchange funding data
    - Uses BybitClient for authenticated access
    - Integration with GlobalRiskView for position monitoring

    SAFETY: Live mode uses real funds. Always verify with demo first.
    """

    SOURCE_NAME = "live_ws"

    def __init__(self, client: "BybitClient | None" = None) -> None:
        """
        Initialize live source (stub).

        Args:
            client: BybitClient for authenticated access (optional for now)
        """
        self._client = client

    @property
    def source_name(self) -> str:
        """Unique name identifying this source."""
        return self.SOURCE_NAME

    def get_mark_price(self, symbol: str, ts: datetime) -> float | None:
        """Get mark price at a specific timestamp (NOT IMPLEMENTED)."""
        raise NotImplementedError(
            "LivePriceSource.get_mark_price not implemented. "
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
            "LivePriceSource.get_ohlcv not implemented. "
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
            "LivePriceSource.get_1m_marks not implemented. "
            "Use BacktestPriceSource for backtest mode."
        )

    def healthcheck(self) -> HealthCheckResult:
        """Check if source is ready (stub returns not ready)."""
        return HealthCheckResult(
            ok=False,
            provider_name=self.SOURCE_NAME,
            message="Live source not implemented (W5)",
        )

    def connect(self) -> None:
        """Connect to WebSocket (NOT IMPLEMENTED)."""
        raise NotImplementedError(
            "LivePriceSource.connect not implemented."
        )

    def disconnect(self) -> None:
        """Disconnect from WebSocket (NOT IMPLEMENTED)."""
        raise NotImplementedError(
            "LivePriceSource.disconnect not implemented."
        )
