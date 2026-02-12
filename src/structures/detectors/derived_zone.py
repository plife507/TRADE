"""
Derived zone detector with K slots + scalar aggregates pattern.

Derives zones from a source swing detector using configurable levels
(e.g., fibonacci ratios). Zones are stored internally as a list and
exposed via:
- Slot fields: zone0_*, zone1_*, ..., zone{K-1}_*
- Aggregate fields: active_count, any_touched, first_active_lower, etc.

Implementation follows 14 locked decisions from DERIVATION_RULE_INVESTIGATION.md:
- Slot ordering: Most recent first (zone0 = newest)
- Empty encoding: None for floats, "none" for state, -1 for ints, false for bools
- Zone hash: blake2b for stability across platforms
- Version-triggered regen: only on source version change
- Separate regen vs interaction paths
- Touched semantics: event (reset each bar)
- Closest: distance to nearest boundary

Example Play usage:
    structures:
      exec:
        - type: swing
          key: pivots
          params:
            left: 5
            right: 5

        - type: derived_zone
          key: fib_zones
          uses: pivots
          params:
            levels: [0.382, 0.5, 0.618]
            mode: retracement
            max_active: 5
            width_pct: 0.002

Access in rules:
    # Slot access
    condition: structure.fib_zones.zone0_state == "active"
    condition: close > structure.fib_zones.zone0_lower

    # Aggregate access
    condition: structure.fib_zones.any_touched == true
    condition: close near_pct structure.fib_zones.first_active_lower

See: docs/architecture/DERIVATION_RULE_INVESTIGATION.md
See: docs/architecture/INCREMENTAL_STATE_ARCHITECTURE.md
"""

from __future__ import annotations

import hashlib
import struct
from typing import TYPE_CHECKING, Any

from ..base import BaseIncrementalDetector
from ..registry import register_structure

if TYPE_CHECKING:
    from ..base import BarData


# Zone states - all lowercase for DSL consistency
ZONE_STATE_NONE = "none"
ZONE_STATE_ACTIVE = "active"
ZONE_STATE_BROKEN = "broken"


@register_structure("derived_zone")
class IncrementalDerivedZone(BaseIncrementalDetector):
    """
    Derived zone detector with K slots + scalar aggregates.

    Creates zones from source swing detector using configurable levels
    (e.g., fibonacci ratios). Supports both retracement and extension modes.

    Parameters:
        levels: List of ratios for zone placement (e.g., [0.382, 0.5, 0.618])
        mode: "retracement" (between swings) or "extension" (beyond swings)
        max_active: Maximum number of active zones to track (K slots)
        width_pct: Zone width as percentage of level price (e.g., 0.002 = 0.2%)
        use_paired_source: If true, only regenerate zones when a complete swing
                          pair forms (L->H bullish or H->L bearish), using
                          pair_high_level/pair_low_level which are guaranteed
                          to come from the same swing sequence. Default: true.

    Dependencies:
        source: A swing detector providing high_level, low_level, version,
               and (if use_paired_source) pair_high_level, pair_low_level, pair_version

    Slot Outputs (per zone 0 to max_active-1):
        zone{N}_lower: Lower boundary price (None if empty)
        zone{N}_upper: Upper boundary price (None if empty)
        zone{N}_state: Zone state ("none", "active", "broken")
        zone{N}_anchor_idx: Bar index where zone was created (-1 if empty)
        zone{N}_age_bars: Bars since creation (-1 if empty)
        zone{N}_touched_this_bar: Event flag - touched THIS bar (false if empty)
        zone{N}_touch_count: Cumulative touch count (0 if empty)
        zone{N}_last_touch_age: Bars since last touch (-1 if never/empty)
        zone{N}_inside: Currently inside zone (false if empty)
        zone{N}_instance_id: Stable hash for zone identity (0 if empty)

    Aggregate Outputs:
        active_count: Number of ACTIVE zones
        any_active: Any zone is ACTIVE
        any_touched: Event - any ACTIVE zone touched THIS bar
        any_inside: Price currently inside any ACTIVE zone
        first_active_lower: Lower bound of first ACTIVE zone by slot (None if none)
        first_active_upper: Upper bound of first ACTIVE zone by slot (None if none)
        first_active_idx: Slot index of first ACTIVE zone by slot (-1 if none)
        newest_active_idx: Slot of most recent ACTIVE (usually 0, -1 if none)
        source_version: Current source structure version

    Performance:
        - update(): O(levels * max_active) on regen, O(max_active) on interaction
        - get_value(): O(1) for slots, O(max_active) for aggregates
    """

    REQUIRED_PARAMS: list[str] = ["levels", "max_active"]
    OPTIONAL_PARAMS: dict[str, Any] = {
        "mode": "retracement",
        "width_pct": 0.002,
        "use_paired_source": True,
        "break_tolerance_pct": 0.001,  # 0.1% tolerance for zone break detection
    }
    DEPENDS_ON: list[str] = ["swing"]
    STRUCTURE_TYPE: str = "derived_zone"

    @classmethod
    def _validate_params(
        cls, struct_type: str, key: str, params: dict[str, Any]
    ) -> None:
        """Validate derived zone parameters."""
        # Validate levels
        levels = params.get("levels")
        if not isinstance(levels, list) or len(levels) == 0:
            raise ValueError(
                f"Structure '{key}': 'levels' must be a non-empty list\n"
                "\n"
                "Fix: levels: [0.382, 0.5, 0.618]"
            )

        for i, level in enumerate(levels):
            if not isinstance(level, (int, float)):
                raise ValueError(
                    f"Structure '{key}': 'levels[{i}]' must be a number\n"
                    "\n"
                    "Fix: levels: [0.382, 0.5, 0.618] or [-0.272, -0.618] for extensions"
                )

        # Validate max_active
        max_active = params.get("max_active")
        if not isinstance(max_active, int) or max_active < 1:
            raise ValueError(
                f"Structure '{key}': 'max_active' must be integer >= 1\n"
                "\n"
                "Fix: max_active: 5"
            )

        # Validate mode
        mode = params.get("mode", "retracement")
        if mode not in ("retracement", "extension"):
            raise ValueError(
                f"Structure '{key}': 'mode' must be 'retracement' or 'extension'\n"
                "\n"
                "Fix: mode: retracement"
            )

        # Validate width_pct
        width_pct = params.get("width_pct", 0.002)
        if not isinstance(width_pct, (int, float)) or width_pct <= 0:
            raise ValueError(
                f"Structure '{key}': 'width_pct' must be positive number\n"
                "\n"
                "Fix: width_pct: 0.002  # 0.2%"
            )

    def __init__(
        self,
        params: dict[str, Any],
        deps: dict[str, BaseIncrementalDetector],
    ) -> None:
        """Initialize derived zone detector."""
        self.source = deps["swing"]
        self.levels: list[float] = [float(lvl) for lvl in params["levels"]]
        self.max_active: int = params["max_active"]
        self.mode: str = params.get("mode", "retracement")
        self.width_pct: float = float(params.get("width_pct", 0.002))
        self.use_paired_source: bool = params.get("use_paired_source", True)
        self.break_tolerance_pct: float = float(params.get("break_tolerance_pct", 0.001))

        # Internal zone storage: list of dicts, most recent first
        # Each zone dict contains all zone fields
        self._zones: list[dict[str, Any]] = []

        # Track source version for regen detection
        # When use_paired_source=True, tracks pair_version instead of version
        self._source_version: int = 0

        # Track current bar for age calculations
        self._current_bar_idx: int = -1

    def update(self, bar_idx: int, bar: "BarData") -> None:
        """
        Process one bar: regen zones on source version change, update interactions.

        Called on EXEC TF close. Source structure may be on a higher TF
        but its values are forward-filled.

        When use_paired_source=True, regeneration triggers on pair_version changes
        (complete L->H or H->L sequences), using pair_high_level/pair_low_level.
        Otherwise, regeneration triggers on any pivot (version changes).

        Args:
            bar_idx: Current bar index.
            bar: Bar data with OHLCV and indicators.
        """
        self._current_bar_idx = bar_idx

        # Two-path state machine:
        # 1. REGEN PATH: Source swing pivots changed -> regenerate all zones
        # 2. INTERACTION PATH: Check price interactions with existing zones

        # Choose version key based on pairing mode
        version_key = "pair_version" if self.use_paired_source else "version"
        current_source_version = self.source.get_value(version_key)

        # REGEN PATH: Only on source version change (new swing pivot confirmed)
        if current_source_version != self._source_version:
            self._regenerate_zones(bar_idx, bar)
            self._source_version = current_source_version  # type: ignore[assignment]

        # INTERACTION PATH: Every exec close (check touches, breaks, age updates)
        self._update_zone_interactions(bar_idx, bar)

    def _regenerate_zones(self, bar_idx: int, bar: "BarData") -> None:
        """
        Regenerate zones from source swing levels.

        Creates new zones for each level from the source swing high/low.
        New zones are prepended to maintain most-recent-first ordering.
        Excess zones beyond max_active are dropped.

        When use_paired_source=True, uses pair_high_level/pair_low_level which
        are guaranteed to come from the same swing sequence (complete L->H or H->L).
        Otherwise, uses individual high_level/low_level which may be from
        different swing sequences.

        Args:
            bar_idx: Current bar index.
            bar: Bar data.
        """
        # Get source swing levels - use paired or individual based on mode
        try:
            if self.use_paired_source:
                high_level = self.source.get_value("pair_high_level")
                low_level = self.source.get_value("pair_low_level")
                high_idx = self.source.get_value("pair_high_idx")
                low_idx = self.source.get_value("pair_low_idx")
            else:
                high_level = self.source.get_value("high_level")
                low_level = self.source.get_value("low_level")
                high_idx = self.source.get_value("high_idx")
                low_idx = self.source.get_value("low_idx")
        except (KeyError, AttributeError):
            return

        # Need valid swing levels (not NaN, both present)
        if high_level != high_level or low_level != low_level:  # NaN check
            return
        if high_idx < 0 or low_idx < 0:  # type: ignore[operator]
            return

        # Calculate range
        range_val = high_level - low_level  # type: ignore[operator]
        if range_val <= 0:
            return

        # Create zones for each level
        for level in self.levels:
            # Calculate zone center based on mode
            if self.mode == "retracement":
                # Retracement: levels between high and low
                center = high_level - (range_val * level)  # type: ignore[operator]
            else:
                # Extension: levels projected beyond high
                center = high_level + (range_val * level)  # type: ignore[operator]

            # Calculate zone boundaries using width_pct
            width = center * self.width_pct
            lower = center - width / 2
            upper = center + width / 2

            # Compute stable zone hash
            instance_id = self._compute_zone_hash(
                source_version=self._source_version,
                pivot_high_idx=int(high_idx),
                pivot_low_idx=int(low_idx),
                level=level,
            )

            # Create new zone dict
            new_zone: dict[str, Any] = {
                "lower": lower,
                "upper": upper,
                "state": ZONE_STATE_ACTIVE,
                "anchor_idx": bar_idx,
                "age_bars": 0,
                "touched_this_bar": False,
                "touch_count": 0,
                "last_touch_bar": -1,
                "inside": False,
                "instance_id": instance_id,
                "level": level,  # Internal tracking
            }

            # Prepend to list (most recent first)
            self._zones.insert(0, new_zone)

        # Enforce max_active limit (drop oldest)
        while len(self._zones) > self.max_active:
            self._zones.pop()

    def _compute_zone_hash(
        self,
        source_version: int,
        pivot_high_idx: int,
        pivot_low_idx: int,
        level: float,
    ) -> int:
        """
        Compute stable zone hash using blake2b.

        Uses deterministic inputs to ensure reproducibility across runs/platforms.
        Level is encoded as scaled int (millionths) to avoid float hashing issues.

        Args:
            source_version: Source structure version at zone creation.
            pivot_high_idx: Bar index of source swing high.
            pivot_low_idx: Bar index of source swing low.
            level: Fibonacci ratio for this zone.

        Returns:
            Unsigned 32-bit hash for zone identity.
        """
        # Encode level deterministically: 0.618 -> "618000" (scaled to millionths)
        level_scaled = int(round(level * 1_000_000))

        # Build deterministic byte string
        data = (
            f"{self.STRUCTURE_TYPE}|"
            f"{source_version}|"
            f"{pivot_high_idx}|"
            f"{pivot_low_idx}|"
            f"{level_scaled}|"
            f"{self.mode}"
        ).encode("utf-8")

        # blake2b, truncated to 32-bit for JSON compatibility
        digest = hashlib.blake2b(data, digest_size=4).digest()
        return struct.unpack(">I", digest)[0]

    def _update_zone_interactions(self, bar_idx: int, bar: "BarData") -> None:
        """
        Update zone interaction state for the current bar.

        Updates touched/inside state and age for all zones.
        Handles zone break detection.

        Args:
            bar_idx: Current bar index.
            bar: Bar data.
        """
        # Get price for interaction checks
        price = self._get_price(bar)
        if price is None or price != price:  # None or NaN check
            return

        for zone in self._zones:
            # Reset event flag each bar
            zone["touched_this_bar"] = False

            # Skip non-active zones for interaction checks
            if zone["state"] != ZONE_STATE_ACTIVE:
                zone["age_bars"] = bar_idx - zone["anchor_idx"]
                zone["inside"] = False
                continue

            # Update age
            zone["age_bars"] = bar_idx - zone["anchor_idx"]

            # Check if price is inside zone
            lower = zone["lower"]
            upper = zone["upper"]
            currently_inside = lower <= price <= upper

            # Check touch (entering zone)
            if currently_inside:
                zone["touched_this_bar"] = True
                zone["touch_count"] += 1
                zone["last_touch_bar"] = bar_idx

            zone["inside"] = currently_inside

            # Check for zone break
            # Zone breaks when price closes completely beyond boundary
            # Skip break check on the creation bar - zones need at least one bar
            # to become reachable (price is often far from retracement levels
            # when the swing pair that created them just completed)
            if zone["anchor_idx"] < bar_idx:
                break_tol = 1.0 - self.break_tolerance_pct
                break_tol_upper = 1.0 + self.break_tolerance_pct
                if price < lower * break_tol:
                    zone["state"] = ZONE_STATE_BROKEN
                elif price > upper * break_tol_upper:
                    zone["state"] = ZONE_STATE_BROKEN

    def _get_price(self, bar: "BarData") -> float | None:
        """
        Get price for interaction checks.

        Args:
            bar: Bar data.

        Returns:
            Price value, or None if not available.
        """
        return bar.close

    def get_output_keys(self) -> list[str]:
        """
        Return list of all output keys (slots + aggregates).

        Dynamically generates slot keys for zone0 to zone{max_active-1}.
        """
        keys: list[str] = []

        # Slot fields for each zone
        slot_fields = [
            "lower", "upper", "state", "anchor_idx", "age_bars",
            "touched_this_bar", "touch_count", "last_touch_age",
            "inside", "instance_id"
        ]
        for i in range(self.max_active):
            for field in slot_fields:
                keys.append(f"zone{i}_{field}")

        # Aggregate fields
        keys.extend([
            "active_count",
            "any_active",
            "any_touched",
            "any_inside",
            "first_active_lower",
            "first_active_upper",
            "first_active_idx",
            "newest_active_idx",
            "source_version",
        ])

        return keys

    def get_value(self, key: str) -> float | int | str | bool | None:
        """
        Get output by key.

        Parses slot keys (zone{N}_{field}) and aggregate keys.
        Returns appropriate empty values for unpopulated slots.

        Args:
            key: Output key name.

        Returns:
            The output value. None for empty float slots.

        Raises:
            KeyError: If key is not valid.
        """
        # Try slot field first (zone0_lower, zone1_state, etc.)
        if key.startswith("zone") and "_" in key:
            return self._get_slot_value(key)

        # Aggregate fields
        if key == "active_count":
            return sum(1 for z in self._zones if z["state"] == ZONE_STATE_ACTIVE)

        if key == "any_active":
            return any(z["state"] == ZONE_STATE_ACTIVE for z in self._zones)

        if key == "any_touched":
            return any(
                z["touched_this_bar"]
                for z in self._zones
                if z["state"] == ZONE_STATE_ACTIVE
            )

        if key == "any_inside":
            return any(
                z["inside"]
                for z in self._zones
                if z["state"] == ZONE_STATE_ACTIVE
            )

        if key == "first_active_lower":
            _, lower, _ = self._get_first_active_bounds()
            return lower

        if key == "first_active_upper":
            _, _, upper = self._get_first_active_bounds()
            return upper

        if key == "first_active_idx":
            for idx, zone in enumerate(self._zones):
                if zone["state"] == ZONE_STATE_ACTIVE:
                    return idx
            return -1

        if key == "newest_active_idx":
            for idx, zone in enumerate(self._zones):
                if zone["state"] == ZONE_STATE_ACTIVE:
                    return idx
            return -1

        if key == "source_version":
            return self._source_version

        raise KeyError(key)

    def _get_slot_value(self, key: str) -> float | int | str | bool | None:
        """
        Get value for a slot field (zone{N}_{field}).

        Args:
            key: Slot key like "zone0_lower" or "zone2_state".

        Returns:
            The slot value, or empty value if slot is unpopulated.

        Raises:
            KeyError: If key format is invalid.
        """
        # Parse key: zone{N}_{field}
        try:
            # Find the underscore that separates zone index from field
            prefix_end = key.index("_")
            slot_idx = int(key[4:prefix_end])  # "zone" is 4 chars
            field = key[prefix_end + 1:]
        except (ValueError, IndexError) as e:
            raise KeyError(key) from e

        # Check if slot is populated
        if slot_idx >= len(self._zones):
            return self._get_empty_value(field)

        zone = self._zones[slot_idx]

        # Map field to zone dict key
        if field == "lower":
            return zone["lower"]
        elif field == "upper":
            return zone["upper"]
        elif field == "state":
            return zone["state"]
        elif field == "anchor_idx":
            return zone["anchor_idx"]
        elif field == "age_bars":
            return zone["age_bars"]
        elif field == "touched_this_bar":
            return zone["touched_this_bar"]
        elif field == "touch_count":
            return zone["touch_count"]
        elif field == "last_touch_age":
            last_touch = zone.get("last_touch_bar", -1)
            if last_touch < 0:
                return -1
            return self._current_bar_idx - last_touch
        elif field == "inside":
            return zone["inside"]
        elif field == "instance_id":
            return zone["instance_id"]
        else:
            raise KeyError(key)

    def _get_empty_value(self, field: str) -> float | int | str | bool | None:
        """
        Get the empty/default value for a field when slot is unpopulated.

        Uses locked decision: null for floats, "none" for state,
        -1 for ints, false for bools.

        Args:
            field: Field name.

        Returns:
            Empty value for the field type.
        """
        if field in ("lower", "upper"):
            return None  # null for floats (JSON-safe)
        elif field == "state":
            return ZONE_STATE_NONE
        elif field in ("anchor_idx", "age_bars", "last_touch_age", "instance_id"):
            return -1 if field != "instance_id" else 0
        elif field in ("touched_this_bar", "inside"):
            return False
        elif field == "touch_count":
            return 0
        else:
            return None

    def _get_first_active_bounds(self) -> tuple[int, Any, Any]:
        """
        Get bounds of first active zone (for first_active_* aggregates).

        Returns:
            Tuple of (idx, lower, upper). Returns (-1, None, None) if no active zones.
        """
        for idx, zone in enumerate(self._zones):
            if zone["state"] == ZONE_STATE_ACTIVE:
                return (idx, zone["lower"], zone["upper"])
        return (-1, None, None)

    def __repr__(self) -> str:
        """Return string representation for debugging."""
        return (
            f"IncrementalDerivedZone("
            f"levels={self.levels}, mode={self.mode!r}, "
            f"max_active={self.max_active}, zones={len(self._zones)})"
        )
