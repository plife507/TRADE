"""
Zone Detector (Stage 5.1).

Computes demand/supply zones from swing high/low points.

Zone Semantics:
- DEMAND zone: Below swing low. Upper=swing_low_level, lower=swing_low - width
- SUPPLY zone: Above swing high. Lower=swing_high_level, upper=swing_high + width

Width Models:
- atr_mult: width = ATR(atr_len) * mult
- percent: width = anchor_level * pct
- fixed: width = fixed value

State Machine:
- NONE → ACTIVE (on swing confirmation)
- ACTIVE → BROKEN (price closes through zone, closed-candle only)

Slot Selection Policy (Stage 5.1):
- Zone slots (demand_1, supply_1, etc.) are "top N zones by deterministic ranking"
- Ranking: newest confirmed swing zone that is ACTIVE at current bar
- BROKEN zones are excluded from slot ranking (historical only)
- When newest ACTIVE zone breaks, slot shifts to next newest ACTIVE
- If no ACTIVE candidates exist, slot is NONE

Instance Identity (Stage 5.1):
- instance_id = deterministic hash of (zone_key, zone_spec_id, parent_anchor_id)
- Stable for caching/artifacts when same swing occupies slot
- Changes when slot occupant changes (different parent_anchor_id)
- 0 when slot is NONE (no occupant)

Output Arrays (per-bar, forward-filled):
- lower: Zone lower bound (NaN if no zone)
- upper: Zone upper bound (NaN if no zone)
- state: Zone state (0=NONE, 1=ACTIVE, 2=BROKEN)
- recency: Bars since zone created (-1 if never)
- parent_anchor_id: Parent swing index that created this zone (-1 if none)
- instance_id: Deterministic identity hash (0 if NONE)
"""

import hashlib
import numpy as np
from typing import Any, Dict, Tuple

from src.backtest.market_structure.types import (
    ZoneType,
    ZoneState,
    ZONE_OUTPUTS,
)
from src.backtest.market_structure.spec import ZoneSpec


def compute_zone_spec_id(zone_spec: "ZoneSpec") -> str:
    """
    Compute stable hash of zone specification.

    The spec_id identifies the zone configuration (type, width_model, params).
    Same configuration -> same spec_id across runs.

    Args:
        zone_spec: Zone specification

    Returns:
        8-character hex string hash
    """
    # Canonical representation of spec parameters
    canonical = f"{zone_spec.type.value}:{zone_spec.width_model}:{sorted(zone_spec.width_params.items())}"
    hash_bytes = hashlib.sha256(canonical.encode()).digest()[:4]
    return hash_bytes.hex()


def compute_zone_instance_id(
    zone_key: str,
    zone_spec_id: str,
    parent_anchor_id: int,
) -> int:
    """
    Compute deterministic instance_id for a zone slot occupant.

    The instance_id uniquely identifies a specific zone instance:
    - Same (zone_key, zone_spec_id, parent_anchor_id) → same instance_id
    - Different parent_anchor_id → different instance_id

    Args:
        zone_key: Stable slot key (e.g., "demand_1")
        zone_spec_id: Hash of zone specification (type, width_model, params)
        parent_anchor_id: Index of parent swing that created this zone

    Returns:
        64-bit signed integer hash (0 if parent_anchor_id is -1/NONE)
    """
    if parent_anchor_id < 0:
        return 0  # Sentinel for NONE state

    # Canonical string for hashing
    canonical = f"{zone_key}:{zone_spec_id}:{parent_anchor_id}"
    # Use SHA256 and take first 8 bytes as int64
    hash_bytes = hashlib.sha256(canonical.encode()).digest()[:8]
    # Convert to signed int64 (to match numpy int64)
    instance_id = int.from_bytes(hash_bytes, byteorder="big", signed=True)
    # Ensure non-zero (0 is reserved for NONE)
    if instance_id == 0:
        instance_id = 1
    return instance_id


class ZoneDetector:
    """
    Computes zones from parent swing detector outputs.

    Not registered in STRUCTURE_REGISTRY - zones are computed as part of
    structure block processing, not standalone.
    """

    def build_batch(
        self,
        swing_outputs: Dict[str, np.ndarray],
        close_prices: np.ndarray,
        zone_spec: ZoneSpec,
        atr: np.ndarray | None = None,
    ) -> Dict[str, np.ndarray]:
        """
        Compute zone arrays from swing outputs.

        Args:
            swing_outputs: Dict from SwingDetector.build_batch()
                - high_level, high_idx for SUPPLY zones
                - low_level, low_idx for DEMAND zones
            close_prices: Close prices for break detection
            zone_spec: Zone specification with width model
            atr: ATR array if width_model='atr_mult'

        Returns:
            Dict mapping ZONE_OUTPUTS keys to numpy arrays
        """
        n = len(close_prices)

        # Output arrays
        lower = np.full(n, np.nan, dtype=np.float64)
        upper = np.full(n, np.nan, dtype=np.float64)
        state = np.zeros(n, dtype=np.int8)  # ZoneState.NONE
        recency = np.full(n, -1, dtype=np.int16)
        parent_anchor_id = np.full(n, -1, dtype=np.int32)
        instance_id = np.zeros(n, dtype=np.int64)  # 0 = NONE

        # Compute zone_spec_id once (stable across bars)
        zone_spec_id = compute_zone_spec_id(zone_spec)

        # Get anchor data based on zone type
        if zone_spec.type == ZoneType.DEMAND:
            anchor_level = swing_outputs["low_level"]
            anchor_idx = swing_outputs["low_idx"]
            # Demand zone: lower = anchor - width, upper = anchor
            is_demand = True
        elif zone_spec.type == ZoneType.SUPPLY:
            anchor_level = swing_outputs["high_level"]
            anchor_idx = swing_outputs["high_idx"]
            # Supply zone: lower = anchor, upper = anchor + width
            is_demand = False
        else:
            raise ValueError(f"Unknown zone type: {zone_spec.type}")

        # Track current zone state
        current_lower = np.nan
        current_upper = np.nan
        current_state = ZoneState.NONE.value
        current_anchor_id = -1
        current_instance_id = 0
        zone_created_bar = -1

        # Process bar by bar
        for i in range(n):
            bar_anchor_level = anchor_level[i]
            bar_anchor_idx = int(anchor_idx[i]) if anchor_idx[i] >= 0 else -1

            # Check if parent swing updated (new zone source)
            if bar_anchor_idx >= 0 and bar_anchor_idx != current_anchor_id:
                if not np.isnan(bar_anchor_level):
                    # New zone from new swing point
                    width = self._compute_width(
                        zone_spec, bar_anchor_level, atr, i
                    )

                    if is_demand:
                        current_lower = bar_anchor_level - width
                        current_upper = bar_anchor_level
                    else:
                        current_lower = bar_anchor_level
                        current_upper = bar_anchor_level + width

                    current_state = ZoneState.ACTIVE.value
                    current_anchor_id = bar_anchor_idx
                    current_instance_id = compute_zone_instance_id(
                        zone_spec.key, zone_spec_id, bar_anchor_idx
                    )
                    zone_created_bar = i

            # Check for zone break (only if ACTIVE)
            if current_state == ZoneState.ACTIVE.value:
                bar_close = close_prices[i]
                if not np.isnan(bar_close):
                    if is_demand:
                        # Demand zone breaks when close < lower
                        if bar_close < current_lower:
                            current_state = ZoneState.BROKEN.value
                    else:
                        # Supply zone breaks when close > upper
                        if bar_close > current_upper:
                            current_state = ZoneState.BROKEN.value

            # Fill output arrays
            lower[i] = current_lower
            upper[i] = current_upper
            state[i] = current_state
            parent_anchor_id[i] = current_anchor_id
            instance_id[i] = current_instance_id

            # Recency: bars since zone created
            if zone_created_bar >= 0:
                recency[i] = i - zone_created_bar

        return {
            "lower": lower,
            "upper": upper,
            "state": state,
            "recency": recency,
            "parent_anchor_id": parent_anchor_id,
            "instance_id": instance_id,
        }

    def _compute_width(
        self,
        zone_spec: ZoneSpec,
        anchor_level: float,
        atr: np.ndarray | None,
        bar_idx: int,
    ) -> float:
        """Compute zone width based on width model."""
        model = zone_spec.width_model
        params = zone_spec.width_params

        if model == "atr_mult":
            if atr is None:
                raise ValueError(
                    f"Zone '{zone_spec.key}' uses atr_mult but no ATR provided. "
                    "Ensure ATR indicator is computed with matching atr_len."
                )
            atr_val = atr[bar_idx] if bar_idx < len(atr) else np.nan
            if np.isnan(atr_val):
                # Fallback to 1% if ATR not available yet
                return anchor_level * 0.01
            mult = params.get("mult", 1.0)
            return atr_val * mult

        elif model == "percent":
            pct = params.get("pct", 0.01)  # Default 1%
            return anchor_level * pct

        elif model == "fixed":
            width = params.get("width", 100.0)  # Default $100
            return width

        else:
            raise ValueError(
                f"Unknown width_model '{model}' for zone '{zone_spec.key}'. "
                "Valid: atr_mult, percent, fixed"
            )


# Public zone output field mapping (internal -> public)
# Zones use the same names internally and publicly
ZONE_OUTPUT_MAPPING: Dict[str, str] = {
    "lower": "lower",
    "upper": "upper",
    "state": "state",
    "recency": "recency",
    "parent_anchor_id": "parent_anchor_id",
    "instance_id": "instance_id",
}

# Public fields for allowlist validation
ZONE_PUBLIC_FIELDS: Tuple[str, ...] = (
    "lower",
    "upper",
    "state",
    "recency",
    "parent_anchor_id",
    "instance_id",
)
