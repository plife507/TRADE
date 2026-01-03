"""
Zone Interaction Computer (Stage 6).

Computes interaction metrics for zones using exec-bar OHLC.

Metrics:
- touched: bool — candle range overlaps zone (range intersection)
- inside: bool — close is within zone bounds (close-based occupancy)
- time_in_zone: int — consecutive bars where inside AND state ACTIVE AND same instance

Metric Formulas:
- touched = (bar_low <= upper) AND (bar_high >= lower)
- inside = (bar_close >= lower) AND (bar_close <= upper)
- time_in_zone = consecutive bars where state==ACTIVE AND inside==1 AND instance_id unchanged

Reset Rules:
- Reset all metrics to 0 when:
  - state != ACTIVE (zone broken or none)
  - instance_id changes (slot got new occupant)
- Break bar override: if state[i] == BROKEN → force all metrics to 0

No lookahead: Uses closed-candle OHLC only.
"""

import numpy as np

from src.backtest.market_structure.types import ZoneState


class ZoneInteractionComputer:
    """
    Computes zone interaction metrics at exec close.

    Called after ZoneDetector.build_batch() produces zone arrays.
    Uses exec-bar OHLC for interaction detection.
    """

    def build_batch(
        self,
        zone_outputs: dict[str, np.ndarray],
        bar_high: np.ndarray,
        bar_low: np.ndarray,
        bar_close: np.ndarray,
    ) -> dict[str, np.ndarray]:
        """
        Compute interaction metrics for a zone.

        Args:
            zone_outputs: Dict from ZoneDetector.build_batch():
                - lower: Zone lower bound (NaN if NONE)
                - upper: Zone upper bound (NaN if NONE)
                - state: Zone state (0=NONE, 1=ACTIVE, 2=BROKEN)
                - instance_id: Deterministic hash (0 if NONE)
            bar_high: Exec-bar high prices
            bar_low: Exec-bar low prices
            bar_close: Exec-bar close prices

        Returns:
            Dict with:
                - touched: uint8 array (0/1)
                - inside: uint8 array (0/1)
                - time_in_zone: int32 array
        """
        n = len(bar_high)

        # Extract zone arrays
        lower = zone_outputs["lower"]
        upper = zone_outputs["upper"]
        state = zone_outputs["state"]
        instance_id = zone_outputs["instance_id"]

        # Output arrays
        touched = np.zeros(n, dtype=np.uint8)
        inside = np.zeros(n, dtype=np.uint8)
        time_in_zone = np.zeros(n, dtype=np.int32)

        # Track previous instance_id for reset detection
        prev_instance_id = 0

        for i in range(n):
            zone_state = state[i]
            zone_lower = lower[i]
            zone_upper = upper[i]
            zone_instance = instance_id[i]

            # Check for instance_id change (slot got new occupant)
            instance_changed = zone_instance != prev_instance_id
            prev_instance_id = zone_instance

            # Only compute metrics when state == ACTIVE
            if zone_state == ZoneState.ACTIVE.value:
                # touched = range intersection (candle overlaps zone)
                # touched = (bar_low <= upper) AND (bar_high >= lower)
                bar_h = bar_high[i]
                bar_l = bar_low[i]
                bar_c = bar_close[i]

                if not (np.isnan(zone_lower) or np.isnan(zone_upper)):
                    # Range intersection check
                    is_touched = (bar_l <= zone_upper) and (bar_h >= zone_lower)
                    touched[i] = 1 if is_touched else 0

                    # inside = close-based occupancy
                    # inside = (bar_close >= lower) AND (bar_close <= upper)
                    is_inside = (bar_c >= zone_lower) and (bar_c <= zone_upper)
                    inside[i] = 1 if is_inside else 0

                    # time_in_zone = consecutive bars where:
                    #   state == ACTIVE AND inside == True AND instance_id unchanged
                    if is_inside and not instance_changed:
                        # Increment from previous bar
                        time_in_zone[i] = (time_in_zone[i - 1] if i > 0 else 0) + 1
                    else:
                        # Reset to 0 (not inside or instance changed)
                        time_in_zone[i] = 0
                else:
                    # Bounds are NaN - shouldn't happen for ACTIVE, but be safe
                    touched[i] = 0
                    inside[i] = 0
                    time_in_zone[i] = 0

            elif zone_state == ZoneState.BROKEN.value:
                # Break bar override: force all metrics to 0
                touched[i] = 0
                inside[i] = 0
                time_in_zone[i] = 0

            else:
                # state == NONE: force all metrics to 0
                touched[i] = 0
                inside[i] = 0
                time_in_zone[i] = 0

        return {
            "touched": touched,
            "inside": inside,
            "time_in_zone": time_in_zone,
        }


# Interaction output fields added to zones (Stage 6)
ZONE_INTERACTION_OUTPUTS = frozenset({
    "touched",
    "inside",
    "time_in_zone",
})
