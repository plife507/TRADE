"""
Tier 2: Derived Zone Tests.

Tests the K-slot zone management system where zones derived from swing
points are tracked in fixed slots (zone0, zone1, ..., zoneK-1).

Key concepts:
- Zones are derived from swing points
- K slots hold the most recent K zones
- zone0 is always the newest zone
- Aggregates summarize across all slots (any_active, active_count, etc.)
- When a new zone is created, it shifts into zone0, pushing others down
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum

from ..runner import TestResult


class ZoneState(Enum):
    """Zone lifecycle states."""
    NONE = "NONE"
    ACTIVE = "ACTIVE"
    TOUCHED = "TOUCHED"
    BROKEN = "BROKEN"


@dataclass
class Zone:
    """A single derived zone."""
    state: ZoneState = ZoneState.NONE
    lower: float = 0.0
    upper: float = 0.0
    inside: bool = False


@dataclass
class DerivedZones:
    """K-slot derived zone container with aggregates."""
    k: int = 3  # Number of slots
    slots: list[Zone] = field(default_factory=list)

    # Aggregates
    any_active: bool = False
    any_touched: bool = False
    any_inside: bool = False
    active_count: int = 0
    closest_active_lower: float = 0.0
    closest_active_upper: float = 0.0

    def __post_init__(self):
        """Initialize empty slots."""
        if not self.slots:
            self.slots = [Zone() for _ in range(self.k)]

    def add_zone(self, lower: float, upper: float) -> None:
        """Add a new zone at slot 0, shifting others down."""
        # Shift existing zones down (drop oldest if at capacity)
        self.slots = [Zone(state=ZoneState.ACTIVE, lower=lower, upper=upper)] + self.slots[:-1]
        self._update_aggregates()

    def update_price(self, close: float) -> None:
        """Update zone states based on current close price."""
        for zone in self.slots:
            if zone.state == ZoneState.NONE:
                continue

            # Check if price is inside zone
            zone.inside = zone.lower <= close <= zone.upper

            # For demand zones (assuming zones are below current price when active)
            if close < zone.lower:
                zone.state = ZoneState.BROKEN
            elif zone.inside:
                zone.state = ZoneState.TOUCHED

        self._update_aggregates()

    def _update_aggregates(self) -> None:
        """Recompute aggregate fields."""
        active_zones = [z for z in self.slots if z.state == ZoneState.ACTIVE]
        touched_zones = [z for z in self.slots if z.state == ZoneState.TOUCHED]
        inside_zones = [z for z in self.slots if z.inside]

        self.any_active = len(active_zones) > 0
        self.any_touched = len(touched_zones) > 0
        self.any_inside = len(inside_zones) > 0
        self.active_count = len(active_zones)

        # Closest active zone (highest lower bound = closest to current price for demand)
        if active_zones:
            closest = max(active_zones, key=lambda z: z.lower)
            self.closest_active_lower = closest.lower
            self.closest_active_upper = closest.upper
        else:
            self.closest_active_lower = 0.0
            self.closest_active_upper = 0.0


def run_tests() -> list[TestResult]:
    """Run all derived zone tests."""
    tests: list[TestResult] = []

    tests.append(test_zone_creation())
    tests.append(test_zone_inside())
    tests.append(test_zone_break())
    tests.append(test_zone_overflow())

    return tests


# =============================================================================
# Derived Zone Tests
# =============================================================================

def test_zone_creation() -> TestResult:
    """T2_050: New swing -> zone0 populated, active_count=1.

    Trading scenario: First swing low detected, creates a demand zone.
    Zone0 should be populated with ACTIVE state.
    """
    test_id = "T2_050"
    start = time.perf_counter()

    try:
        zones = DerivedZones(k=3)
        zones.add_zone(lower=75.0, upper=80.0)

        checks = [
            zones.slots[0].state == ZoneState.ACTIVE,
            zones.slots[0].lower == 75.0,
            zones.slots[0].upper == 80.0,
            zones.active_count == 1,
            zones.any_active is True,
        ]

        if all(checks):
            return TestResult(
                test_id=test_id,
                passed=True,
                message="zone0 = ACTIVE [75, 80], active_count=1",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Checks failed: state={zones.slots[0].state}, count={zones.active_count}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_zone_inside() -> TestResult:
    """T2_051: Price enters zone -> zone0_inside=True, any_inside=True.

    Trading scenario: Price retraces into the demand zone.
    This is a potential entry signal.
    """
    test_id = "T2_051"
    start = time.perf_counter()

    try:
        zones = DerivedZones(k=3)
        zones.add_zone(lower=75.0, upper=80.0)
        zones.update_price(close=77.0)  # Inside the zone

        checks = [
            zones.slots[0].inside is True,
            zones.any_inside is True,
            zones.slots[0].state == ZoneState.TOUCHED,
        ]

        if all(checks):
            return TestResult(
                test_id=test_id,
                passed=True,
                message="zone0_inside=True, state=TOUCHED",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"inside={zones.slots[0].inside}, state={zones.slots[0].state}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_zone_break() -> TestResult:
    """T2_052: Price breaks zone -> zone0_state=BROKEN, active_count=0.

    Trading scenario: Price broke through the demand zone.
    Zone is invalidated - support failed.
    """
    test_id = "T2_052"
    start = time.perf_counter()

    try:
        zones = DerivedZones(k=3)
        zones.add_zone(lower=75.0, upper=80.0)
        zones.update_price(close=74.0)  # Broke below zone

        checks = [
            zones.slots[0].state == ZoneState.BROKEN,
            zones.active_count == 0,
            zones.any_active is False,
        ]

        if all(checks):
            return TestResult(
                test_id=test_id,
                passed=True,
                message="zone0_state=BROKEN, active_count=0",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"state={zones.slots[0].state}, count={zones.active_count}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_zone_overflow() -> TestResult:
    """T2_053: Max active overflow -> oldest dropped, newest at zone0.

    Trading scenario: More zones than K slots.
    Oldest zone should be dropped, newest should be at zone0.
    """
    test_id = "T2_053"
    start = time.perf_counter()

    try:
        zones = DerivedZones(k=3)

        # Add 4 zones (more than K=3)
        zones.add_zone(lower=70.0, upper=75.0)  # Will be dropped
        zones.add_zone(lower=75.0, upper=80.0)  # -> zone2
        zones.add_zone(lower=80.0, upper=85.0)  # -> zone1
        zones.add_zone(lower=85.0, upper=90.0)  # -> zone0 (newest)

        checks = [
            zones.slots[0].lower == 85.0,  # Newest at zone0
            zones.slots[1].lower == 80.0,
            zones.slots[2].lower == 75.0,
            zones.active_count == 3,
        ]

        if all(checks):
            return TestResult(
                test_id=test_id,
                passed=True,
                message="zone0=[85,90], oldest [70,75] dropped",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            lowers = [z.lower for z in zones.slots]
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Slot lowers: {lowers}, count={zones.active_count}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


if __name__ == "__main__":
    results = run_tests()
    passed = sum(1 for r in results if r.passed)
    print(f"Derived zone tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
