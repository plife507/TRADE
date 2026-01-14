"""
Tier 2: Zone Detection Tests.

Tests supply/demand zone creation and state management.

Zones are price areas derived from swing points:
- Demand Zone: Area below a swing low where buyers stepped in
- Supply Zone: Area above a swing high where sellers stepped in

Zone states:
- NONE: No zone exists
- ACTIVE: Zone is valid and untested
- TOUCHED: Price entered zone but didn't break it
- BROKEN: Price broke through the zone (invalidated)
"""

from __future__ import annotations

import time
from enum import Enum

from ..runner import TestResult


class ZoneState(Enum):
    """Zone lifecycle states."""
    NONE = "NONE"
    ACTIVE = "ACTIVE"
    TOUCHED = "TOUCHED"
    BROKEN = "BROKEN"


def run_tests() -> list[TestResult]:
    """Run all zone detection tests."""
    tests: list[TestResult] = []

    tests.append(test_demand_zone_creation())
    tests.append(test_supply_zone_creation())
    tests.append(test_zone_break())
    tests.append(test_zone_hold())

    return tests


def _create_demand_zone(
    swing_low: float,
    atr: float,
    width_multiplier: float = 1.0,
) -> tuple[float, float]:
    """
    Create demand zone from swing low.

    Zone extends below the swing low by ATR * width_multiplier.

    Returns (lower_bound, upper_bound) tuple.
    """
    zone_height = atr * width_multiplier
    lower = swing_low - zone_height
    upper = swing_low
    return (lower, upper)


def _create_supply_zone(
    swing_high: float,
    atr: float,
    width_multiplier: float = 1.0,
) -> tuple[float, float]:
    """
    Create supply zone from swing high.

    Zone extends above the swing high by ATR * width_multiplier.

    Returns (lower_bound, upper_bound) tuple.
    """
    zone_height = atr * width_multiplier
    lower = swing_high
    upper = swing_high + zone_height
    return (lower, upper)


def _check_zone_state(
    close: float,
    zone_lower: float,
    zone_upper: float,
    zone_type: str,  # "demand" or "supply"
) -> ZoneState:
    """
    Check zone state based on current close price.

    For demand zones (below price):
    - ACTIVE: close > zone_upper (price above zone)
    - TOUCHED: zone_lower <= close <= zone_upper (price in zone)
    - BROKEN: close < zone_lower (price broke below zone)

    For supply zones (above price):
    - ACTIVE: close < zone_lower (price below zone)
    - TOUCHED: zone_lower <= close <= zone_upper (price in zone)
    - BROKEN: close > zone_upper (price broke above zone)
    """
    if zone_type == "demand":
        if close < zone_lower:
            return ZoneState.BROKEN
        elif close <= zone_upper:
            return ZoneState.TOUCHED
        else:
            return ZoneState.ACTIVE
    else:  # supply
        if close > zone_upper:
            return ZoneState.BROKEN
        elif close >= zone_lower:
            return ZoneState.TOUCHED
        else:
            return ZoneState.ACTIVE


# =============================================================================
# Zone Creation Tests
# =============================================================================

def test_demand_zone_creation() -> TestResult:
    """T2_020: Demand zone (low=80, ATR=5, width=1.0) -> [75, 80].

    Trading scenario: Swing low at 80, ATR=5 gives zone height.
    Zone spans from 75 to 80 (below the swing low).
    """
    test_id = "T2_020"
    start = time.perf_counter()

    try:
        zone = _create_demand_zone(swing_low=80.0, atr=5.0, width_multiplier=1.0)
        expected = (75.0, 80.0)

        if zone == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Demand zone = [{zone[0]}, {zone[1]}]",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {zone}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_supply_zone_creation() -> TestResult:
    """T2_021: Supply zone (high=100, ATR=5, width=1.0) -> [100, 105].

    Trading scenario: Swing high at 100, ATR=5 gives zone height.
    Zone spans from 100 to 105 (above the swing high).
    """
    test_id = "T2_021"
    start = time.perf_counter()

    try:
        zone = _create_supply_zone(swing_high=100.0, atr=5.0, width_multiplier=1.0)
        expected = (100.0, 105.0)

        if zone == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Supply zone = [{zone[0]}, {zone[1]}]",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected}, got {zone}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


# =============================================================================
# Zone State Tests
# =============================================================================

def test_zone_break() -> TestResult:
    """T2_022: Zone break (close=74, lower=75) -> BROKEN.

    Trading scenario: Price broke below demand zone.
    Zone is invalidated - no longer a valid support area.
    """
    test_id = "T2_022"
    start = time.perf_counter()

    try:
        state = _check_zone_state(
            close=74.0,
            zone_lower=75.0,
            zone_upper=80.0,
            zone_type="demand",
        )
        expected = ZoneState.BROKEN

        if state == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Zone state = {state.value} (price broke zone)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected.value}, got {state.value}",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
    except Exception as e:
        return TestResult(
            test_id=test_id,
            passed=False,
            message=f"Error: {e}",
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def test_zone_hold() -> TestResult:
    """T2_023: Zone hold (close=75, lower=75) -> TOUCHED (not broken).

    Trading scenario: Price touched the zone boundary but didn't break.
    Zone remains valid (touched but not invalidated).
    """
    test_id = "T2_023"
    start = time.perf_counter()

    try:
        state = _check_zone_state(
            close=75.0,
            zone_lower=75.0,
            zone_upper=80.0,
            zone_type="demand",
        )
        expected = ZoneState.TOUCHED

        if state == expected:
            return TestResult(
                test_id=test_id,
                passed=True,
                message=f"Zone state = {state.value} (touched, not broken)",
                duration_ms=(time.perf_counter() - start) * 1000,
            )
        else:
            return TestResult(
                test_id=test_id,
                passed=False,
                message=f"Expected {expected.value}, got {state.value}",
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
    print(f"Zone detection tests: {passed}/{len(results)} passed")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  {status}: {r.test_id} - {r.message}")
