"""
Vectorized reference implementation for premium/discount zone detection.

Replicates IncrementalPremiumDiscount logic in a single-pass loop:
- Reads swing pair high/low levels per bar
- Computes equilibrium, premium, discount levels
- Classifies zone based on close position
- Tracks zone changes for version counter

Used by audit_structure_parity.py for parity comparison.
"""

from __future__ import annotations

import math

import numpy as np


def vectorized_premium_discount(
    ohlcv: dict[str, np.ndarray],
    swing_outputs: dict[str, np.ndarray],
) -> dict[str, np.ndarray]:
    """
    Compute premium/discount zone outputs from OHLCV and swing pair data.

    Args:
        ohlcv: Dict with open, high, low, close, volume arrays.
        swing_outputs: Dict with pair_high_level, pair_low_level arrays from
            the swing detector (vectorized).

    Returns:
        Dict mapping output key -> numpy array (float64 for numeric,
        object for zone strings).
    """
    close = ohlcv["close"]
    n = len(close)

    pair_high = swing_outputs["pair_high_level"]
    pair_low = swing_outputs["pair_low_level"]

    # Output arrays
    out_equilibrium = np.full(n, np.nan)
    out_premium_level = np.full(n, np.nan)
    out_discount_level = np.full(n, np.nan)
    out_zone = np.empty(n, dtype=object)
    out_zone[:] = "none"
    out_depth_pct = np.full(n, np.nan)
    out_version = np.zeros(n)

    prev_zone = "none"
    version = 0

    for i in range(n):
        ph = pair_high[i]
        pl = pair_low[i]

        if isinstance(ph, float) and math.isnan(ph) or isinstance(pl, float) and math.isnan(pl):
            # No valid swing pair
            out_equilibrium[i] = np.nan
            out_premium_level[i] = np.nan
            out_discount_level[i] = np.nan
            out_depth_pct[i] = np.nan
            new_zone = "none"
        else:
            high = float(ph)
            low = float(pl)
            span = high - low

            if span <= 0:
                out_equilibrium[i] = high
                out_premium_level[i] = high
                out_discount_level[i] = low
                out_depth_pct[i] = 0.5
                new_zone = "equilibrium"
            else:
                eq = low + 0.5 * span
                prem = low + 0.75 * span
                disc = low + 0.25 * span
                out_equilibrium[i] = eq
                out_premium_level[i] = prem
                out_discount_level[i] = disc

                c = close[i]
                if c >= prem:
                    new_zone = "premium"
                elif c <= disc:
                    new_zone = "discount"
                else:
                    new_zone = "equilibrium"

                raw_depth = (c - low) / span
                out_depth_pct[i] = max(0.0, min(1.0, raw_depth))

        if new_zone != prev_zone:
            version += 1
            prev_zone = new_zone
        out_zone[i] = new_zone
        out_version[i] = float(version)

    return {
        "equilibrium": out_equilibrium,
        "premium_level": out_premium_level,
        "discount_level": out_discount_level,
        "zone": out_zone,
        "depth_pct": out_depth_pct,
        "version": out_version,
    }
