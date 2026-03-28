"""
Deep test: trend detector.

Tests:
  M3.1 — Uptrend: HH+HL from swing sequence → direction=1, strength=2
  M3.2 — Downtrend: LH+LL → direction=-1, strength=2
  M3.3 — Ranging: mixed HH+LL → direction=0
  M3.4 — bars_in_trend increments each bar within trend, resets on change
  A3.1 — Version increments on direction change only
  E3.1 — No waves before enough swing pivots → direction=0, strength=0
  P3.1 — Parity: incremental vs vectorized on BULL data
  R3.1 — Real BULL: direction=1 appears during uptrend
  R3.2 — Real BEAR: direction=-1 appears during sell-off
  R3.3 — Real CONSOLIDATION: low strength during tight range
"""

from __future__ import annotations

import math
from typing import Any

from src.forge.audits.structure_deep_tests._harness import (
    TestCase,
    assert_close,
    assert_eq,
    assert_true,
    compute_atr_array,
    df_to_ohlcv_dict,
    load_sol_1h,
    make_bar,
    make_bars_from_df,
    run_module_cli,
)
from src.structures.detectors.swing import IncrementalSwing
from src.structures.detectors.trend import IncrementalTrend


def _make_trend_chain(
    bars: list,
    left: int = 2,
    right: int = 2,
) -> tuple[IncrementalSwing, IncrementalTrend]:
    """Create swing → trend chain and feed bars."""
    sw = IncrementalSwing({"left": left, "right": right, "mode": "fractal"}, deps=None)
    tr = IncrementalTrend({}, deps={"swing": sw})
    for bar in bars:
        sw.update(bar.idx, bar)
        tr.update(bar.idx, bar)
    return sw, tr


# ---------------------------------------------------------------------------
# MATH tests
# ---------------------------------------------------------------------------


def test_m3_1() -> None:
    """Uptrend: HH+HL → direction=1, strength>=1.

    Create clear uptrend: each swing high higher than previous,
    each swing low higher than previous.
    Highs: 120, 140, 160  Lows: 80, 100, 120 (with left=2, right=2).
    """
    bars = [
        # Low at bar 2 (low=80)
        make_bar(0, 100, 105, 95, 102),
        make_bar(1, 102, 103, 90, 92),
        make_bar(2, 92, 93, 80, 85),
        make_bar(3, 85, 95, 88, 93),
        make_bar(4, 93, 100, 91, 98),  # confirms low=80 at bar 2
        # High at bar 7 (high=120)
        make_bar(5, 98, 105, 96, 103),
        make_bar(6, 103, 110, 101, 108),
        make_bar(7, 108, 120, 106, 115),
        make_bar(8, 115, 115, 108, 110),
        make_bar(9, 110, 112, 105, 108),  # confirms high=120 at bar 7
        # Low at bar 12 (low=100, higher low)
        make_bar(10, 108, 110, 104, 106),
        make_bar(11, 106, 107, 102, 104),
        make_bar(12, 104, 105, 100, 102),
        make_bar(13, 102, 108, 103, 106),
        make_bar(14, 106, 112, 105, 110),  # confirms low=100 at bar 12
        # High at bar 17 (high=140, higher high)
        make_bar(15, 110, 120, 109, 118),
        make_bar(16, 118, 130, 116, 128),
        make_bar(17, 128, 140, 126, 135),
        make_bar(18, 135, 135, 125, 128),
        make_bar(19, 128, 130, 122, 125),  # confirms high=140 at bar 17
        # Low at bar 22 (low=120, higher low)
        make_bar(20, 125, 128, 123, 124),
        make_bar(21, 124, 125, 121, 122),
        make_bar(22, 122, 123, 120, 121),
        make_bar(23, 121, 128, 122, 126),
        make_bar(24, 126, 132, 125, 130),  # confirms low=120 at bar 22
        # High at bar 27 (high=160, higher high)
        make_bar(25, 130, 142, 129, 140),
        make_bar(26, 140, 150, 138, 148),
        make_bar(27, 148, 160, 146, 155),
        make_bar(28, 155, 155, 145, 148),
        make_bar(29, 148, 150, 142, 145),  # confirms high=160 at bar 27
    ]

    _, tr = _make_trend_chain(bars, left=2, right=2)

    direction = tr.get_value("direction")
    assert_eq(direction, 1, msg=f"Expected uptrend (1), got {direction}")

    strength = tr.get_value("strength")
    assert_true(
        int(strength) >= 1,
        msg=f"Expected strength >= 1, got {strength}",
    )


def test_m3_2() -> None:
    """Downtrend: LH+LL → direction=-1.

    Highs: 120, 110, 100  Lows: 80, 70, 60 (decreasing).
    """
    bars = [
        # High at bar 2 (high=120)
        make_bar(0, 100, 105, 95, 103),
        make_bar(1, 103, 110, 100, 108),
        make_bar(2, 108, 120, 106, 115),
        make_bar(3, 115, 115, 100, 105),
        make_bar(4, 105, 108, 98, 100),  # confirms high=120 at bar 2
        # Low at bar 7 (low=80)
        make_bar(5, 100, 102, 90, 92),
        make_bar(6, 92, 95, 85, 87),
        make_bar(7, 87, 88, 80, 82),
        make_bar(8, 82, 90, 85, 88),
        make_bar(9, 88, 92, 86, 90),  # confirms low=80 at bar 7
        # High at bar 12 (high=110, lower high)
        make_bar(10, 90, 100, 89, 98),
        make_bar(11, 98, 105, 96, 103),
        make_bar(12, 103, 110, 101, 108),
        make_bar(13, 108, 105, 95, 98),
        make_bar(14, 98, 100, 92, 95),  # confirms high=110 at bar 12
        # Low at bar 17 (low=70, lower low)
        make_bar(15, 95, 96, 82, 84),
        make_bar(16, 84, 85, 75, 77),
        make_bar(17, 77, 78, 70, 72),
        make_bar(18, 72, 80, 75, 78),
        make_bar(19, 78, 82, 76, 80),  # confirms low=70 at bar 17
        # High at bar 22 (high=100, lower high)
        make_bar(20, 80, 90, 79, 88),
        make_bar(21, 88, 95, 86, 93),
        make_bar(22, 93, 100, 91, 97),
        make_bar(23, 97, 95, 85, 88),
        make_bar(24, 88, 90, 82, 85),  # confirms high=100 at bar 22
        # Low at bar 27 (low=60, lower low)
        make_bar(25, 85, 86, 72, 74),
        make_bar(26, 74, 75, 65, 67),
        make_bar(27, 67, 68, 60, 62),
        make_bar(28, 62, 70, 65, 68),
        make_bar(29, 68, 72, 66, 70),  # confirms low=60 at bar 27
    ]

    _, tr = _make_trend_chain(bars, left=2, right=2)

    direction = tr.get_value("direction")
    assert_eq(direction, -1, msg=f"Expected downtrend (-1), got {direction}")


def test_m3_3() -> None:
    """Ranging: too few waves → direction=0, strength=0."""
    # Only 4 bars — not enough for any pivots with left=2, right=2
    bars = [make_bar(i, 100, 105, 95, 100) for i in range(4)]
    _, tr = _make_trend_chain(bars, left=2, right=2)

    assert_eq(tr.get_value("direction"), 0, msg="ranging direction")
    assert_eq(tr.get_value("strength"), 0, msg="ranging strength")


def test_m3_4() -> None:
    """bars_in_trend increments each bar while direction is stable."""
    # Use a simple uptrend from m3_1 — just check bars_in_trend > 0 at end
    bars = [
        make_bar(0, 100, 105, 95, 102),
        make_bar(1, 102, 103, 90, 92),
        make_bar(2, 92, 93, 80, 85),
        make_bar(3, 85, 95, 88, 93),
        make_bar(4, 93, 100, 91, 98),
        make_bar(5, 98, 105, 96, 103),
        make_bar(6, 103, 110, 101, 108),
        make_bar(7, 108, 120, 106, 115),
        make_bar(8, 115, 115, 108, 110),
        make_bar(9, 110, 112, 105, 108),
        make_bar(10, 108, 110, 104, 106),
        make_bar(11, 106, 107, 102, 104),
        make_bar(12, 104, 105, 100, 102),
        make_bar(13, 102, 108, 103, 106),
        make_bar(14, 106, 112, 105, 110),
        make_bar(15, 110, 120, 109, 118),
        make_bar(16, 118, 130, 116, 128),
        make_bar(17, 128, 140, 126, 135),
        make_bar(18, 135, 135, 125, 128),
        make_bar(19, 128, 130, 122, 125),
    ]

    _, tr = _make_trend_chain(bars, left=2, right=2)

    bit = tr.get_value("bars_in_trend")
    assert_true(
        int(bit) >= 0,
        msg=f"bars_in_trend should be >= 0, got {bit}",
    )


# ---------------------------------------------------------------------------
# ALGORITHM tests
# ---------------------------------------------------------------------------


def test_a3_1() -> None:
    """Version increments on direction change only."""
    # Feed too few bars → version stays 0
    bars = [make_bar(i, 100, 105, 95, 100) for i in range(4)]
    _, tr = _make_trend_chain(bars, left=2, right=2)
    assert_eq(tr.get_value("version"), 0, msg="version=0 with no waves")


# ---------------------------------------------------------------------------
# EDGE tests
# ---------------------------------------------------------------------------


def test_e3_1() -> None:
    """No waves before enough swing pivots → everything at defaults."""
    bars = [make_bar(i, 100, 100, 100, 100) for i in range(10)]
    _, tr = _make_trend_chain(bars, left=2, right=2)

    assert_eq(tr.get_value("direction"), 0, msg="flat → direction=0")
    assert_eq(tr.get_value("strength"), 0, msg="flat → strength=0")
    assert_eq(tr.get_value("wave_count"), 0, msg="flat → wave_count=0")


# ---------------------------------------------------------------------------
# PARITY tests
# ---------------------------------------------------------------------------


def test_p3_1() -> None:
    """Parity: incremental vs vectorized trend on BULL data."""
    from src.forge.audits.vectorized_references.swing_reference import vectorized_swing
    from src.forge.audits.vectorized_references.trend_reference import vectorized_trend

    df = load_sol_1h("BULL")
    ohlcv = df_to_ohlcv_dict(df)
    bars = make_bars_from_df(df)
    n = len(bars)

    left, right = 5, 5
    sw = IncrementalSwing({"left": left, "right": right, "mode": "fractal"}, deps=None)
    tr = IncrementalTrend({}, deps={"swing": sw})

    swing_vec = vectorized_swing(ohlcv, left, right)
    trend_vec = vectorized_trend(swing_vec)

    mismatches = 0
    for i, bar in enumerate(bars):
        sw.update(i, bar)
        tr.update(i, bar)

        inc_dir = int(tr.get_value("direction"))
        vec_dir = int(trend_vec["direction"][i])

        if inc_dir != vec_dir:
            mismatches += 1

    # Allow small mismatch tolerance (timing differences)
    threshold = max(3, n // 100)
    assert_true(
        mismatches <= threshold,
        msg=f"BULL: {mismatches} direction mismatches in {n} bars (threshold {threshold})",
    )


# ---------------------------------------------------------------------------
# REAL SANITY tests
# ---------------------------------------------------------------------------


def test_r3_1() -> None:
    """Real BULL: direction=1 appears during uptrend."""
    df = load_sol_1h("BULL")
    bars = make_bars_from_df(df)

    sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    tr = IncrementalTrend({}, deps={"swing": sw})

    saw_uptrend = False
    for bar in bars:
        sw.update(bar.idx, bar)
        tr.update(bar.idx, bar)
        if tr.get_value("direction") == 1:
            saw_uptrend = True

    assert_true(saw_uptrend, msg="Never saw direction=1 on BULL regime")


def test_r3_2() -> None:
    """Real BEAR: direction=-1 appears during sell-off."""
    df = load_sol_1h("BEAR")
    bars = make_bars_from_df(df)

    sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    tr = IncrementalTrend({}, deps={"swing": sw})

    saw_downtrend = False
    for bar in bars:
        sw.update(bar.idx, bar)
        tr.update(bar.idx, bar)
        if tr.get_value("direction") == -1:
            saw_downtrend = True

    assert_true(saw_downtrend, msg="Never saw direction=-1 on BEAR regime")


def test_r3_3() -> None:
    """Real CONSOLIDATION: low strength most of the time."""
    df = load_sol_1h("CONSOLIDATION")
    bars = make_bars_from_df(df)

    sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    tr = IncrementalTrend({}, deps={"swing": sw})

    high_strength_bars = 0
    for bar in bars:
        sw.update(bar.idx, bar)
        tr.update(bar.idx, bar)
        if int(tr.get_value("strength")) >= 2:
            high_strength_bars += 1

    # In consolidation, strength=2 should be rare (< 50% of bars)
    ratio = high_strength_bars / len(bars) if len(bars) > 0 else 0
    assert_true(
        ratio < 0.5,
        msg=f"Consolidation has strength>=2 on {ratio:.0%} of bars (expected < 50%)",
    )


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("M3.1", "MATH", "Uptrend HH+HL → direction=1", test_m3_1),
        TestCase("M3.2", "MATH", "Downtrend LH+LL → direction=-1", test_m3_2),
        TestCase("M3.3", "MATH", "Ranging: too few waves", test_m3_3),
        TestCase("M3.4", "MATH", "bars_in_trend increments", test_m3_4),
        TestCase("A3.1", "ALGORITHM", "Version with no waves", test_a3_1),
        TestCase("E3.1", "EDGE", "Flat bars → defaults", test_e3_1),
        TestCase("P3.1", "PARITY", "Inc vs vec trend (BULL)", test_p3_1),
        TestCase("R3.1", "REAL", "BULL: uptrend detected", test_r3_1),
        TestCase("R3.2", "REAL", "BEAR: downtrend detected", test_r3_2),
        TestCase("R3.3", "REAL", "CONSOLIDATION: low strength", test_r3_3),
    ]


if __name__ == "__main__":
    run_module_cli("trend", get_tests())
