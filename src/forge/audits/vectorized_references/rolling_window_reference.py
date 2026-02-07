"""
Vectorized reference implementation for rolling window min/max.

Uses pd.Series.rolling() as the ground truth - trivial to verify
but proves the comparison framework works end-to-end.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def vectorized_rolling_window(
    ohlcv: dict[str, np.ndarray],
    size: int,
    source: str,
    mode: str,
) -> dict[str, np.ndarray]:
    """
    Compute rolling min/max using pandas rolling window.

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        size: Window size in bars.
        source: Which OHLCV field to track ("open", "high", "low", "close", "volume").
        mode: "min" or "max".

    Returns:
        Dict with "value" -> numpy array of rolling min/max values.
    """
    series = pd.Series(ohlcv[source])

    if mode == "min":
        result = series.rolling(window=size, min_periods=1).min()
    else:
        result = series.rolling(window=size, min_periods=1).max()

    return {"value": result.values}
