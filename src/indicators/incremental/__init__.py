"""
Incremental indicator computation for live trading.

O(1) per-bar updates for common indicators. These MUST produce identical
results to pandas_ta vectorized computation (within floating point tolerance).

Usage:
    from src.indicators.incremental import IncrementalEMA, IncrementalRSI

    # Initialize with warmup data
    ema = IncrementalEMA(length=20)
    for price in historical_closes:
        ema.update(price)

    # Then update incrementally in live loop
    ema.update(new_close)
    current_value = ema.value
"""

from __future__ import annotations

# Base class
from .base import IncrementalIndicator

# Core indicators
from .core import (
    IncrementalEMA,
    IncrementalSMA,
    IncrementalRSI,
    IncrementalATR,
    IncrementalMACD,
    IncrementalBBands,
    IncrementalWilliamsR,
    IncrementalCCI,
    IncrementalStochastic,
    IncrementalStochRSI,
    IncrementalADX,
    IncrementalSuperTrend,
)

# Trivial indicators
from .trivial import (
    IncrementalOHLC4,
    IncrementalMidprice,
    IncrementalROC,
    IncrementalMOM,
    IncrementalOBV,
    IncrementalNATR,
)

# EMA-composable indicators
from .ema_composable import (
    IncrementalDEMA,
    IncrementalTEMA,
    IncrementalPPO,
    IncrementalTRIX,
    IncrementalTSI,
)

# SMA/Buffer-based indicators
from .buffer_based import (
    IncrementalWMA,
    IncrementalTRIMA,
    IncrementalLINREG,
    IncrementalCMF,
    IncrementalCMO,
    IncrementalMFI,
)

# Lookback-based indicators
from .lookback import (
    IncrementalAROON,
    IncrementalDonchian,
    IncrementalKC,
    IncrementalDM,
    IncrementalVortex,
)

# Complex adaptive indicators
from .adaptive import (
    IncrementalKAMA,
    IncrementalALMA,
    IncrementalZLMA,
    IncrementalUO,
)

# Stateful multi-output indicators
from .stateful import (
    IncrementalPSAR,
    IncrementalSqueeze,
    IncrementalFisher,
)

# Volume complex indicators
from .volume import (
    IncrementalKVO,
    IncrementalVWAP,
    IncrementalAnchoredVWAP,
)

# Factory and utilities
from .factory import (
    create_incremental_indicator,
    supports_incremental,
    list_incremental_indicators,
    INCREMENTAL_INDICATORS,
)

__all__ = [
    # Base
    "IncrementalIndicator",
    # Core
    "IncrementalEMA",
    "IncrementalSMA",
    "IncrementalRSI",
    "IncrementalATR",
    "IncrementalMACD",
    "IncrementalBBands",
    "IncrementalWilliamsR",
    "IncrementalCCI",
    "IncrementalStochastic",
    "IncrementalStochRSI",
    "IncrementalADX",
    "IncrementalSuperTrend",
    # Trivial
    "IncrementalOHLC4",
    "IncrementalMidprice",
    "IncrementalROC",
    "IncrementalMOM",
    "IncrementalOBV",
    "IncrementalNATR",
    # EMA-composable
    "IncrementalDEMA",
    "IncrementalTEMA",
    "IncrementalPPO",
    "IncrementalTRIX",
    "IncrementalTSI",
    # SMA/Buffer-based
    "IncrementalWMA",
    "IncrementalTRIMA",
    "IncrementalLINREG",
    "IncrementalCMF",
    "IncrementalCMO",
    "IncrementalMFI",
    # Lookback-based
    "IncrementalAROON",
    "IncrementalDonchian",
    "IncrementalKC",
    "IncrementalDM",
    "IncrementalVortex",
    # Complex adaptive
    "IncrementalKAMA",
    "IncrementalALMA",
    "IncrementalZLMA",
    "IncrementalUO",
    # Stateful multi-output
    "IncrementalPSAR",
    "IncrementalSqueeze",
    "IncrementalFisher",
    # Volume complex
    "IncrementalKVO",
    "IncrementalVWAP",
    "IncrementalAnchoredVWAP",
    # Factory and utilities
    "create_incremental_indicator",
    "supports_incremental",
    "list_incremental_indicators",
    "INCREMENTAL_INDICATORS",
]
