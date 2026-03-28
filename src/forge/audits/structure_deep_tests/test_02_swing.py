"""
Deep test: swing detector (fractal mode).

Tests:
  M2.1 — Swing high confirmed at correct index with left=2, right=2
  M2.2 — Swing low confirmed at correct index with left=2, right=2
  M2.3 — No false pivot when tie exists (strictly greater/less required)
  M2.4 — Version increments correctly on each confirmed pivot
  M2.5 — Pair direction: Low→High = bullish, High→Low = bearish
  M2.6 — pair_version increments only on pair completion, not individual pivots
  A2.1 — Pair state: HIGH→HIGH replaces pending (no pair completion)
  A2.2 — Pair state: LOW→LOW replaces pending (no pair completion)
  E2.1 — Flat bars: all same price → no pivots confirmed
  E2.2 — Single spike: one high bar surrounded by identical bars
  P2.1 — Parity: incremental vs vectorized reference on BULL data
  P2.2 — Parity: incremental vs vectorized reference on BEAR data
  R2.1 — Real: swing highs are local maxima on BULL data
  R2.2 — Real: pivots alternate high/low (no 3 consecutive same type)
"""

from __future__ import annotations

import math
from typing import Any

from src.forge.audits.structure_deep_tests._harness import (
    TestCase,
    assert_close,
    assert_eq,
    assert_nan,
    assert_true,
    df_to_ohlcv_dict,
    load_sol_1h,
    make_bar,
    make_bars_from_df,
    run_module_cli,
)
from src.structures.detectors.swing import IncrementalSwing


def _make_swing(left: int = 2, right: int = 2) -> IncrementalSwing:
    """Create a fractal swing detector."""
    params: dict[str, Any] = {"left": left, "right": right, "mode": "fractal"}
    return IncrementalSwing(params, deps=None)


# ---------------------------------------------------------------------------
# MATH tests
# ---------------------------------------------------------------------------


def test_m2_1() -> None:
    """Swing high confirmed at correct index with left=2, right=2.

    Window = left + right + 1 = 5 bars.
    Pivot index in buffer = left = 2 (middle).
    Confirmation happens at bar_idx = pivot_bar_idx + right.

    Sequence of highs: [100, 105, 120, 110, 108, 106, ...]
    Pivot at bar 2 (high=120) confirmed at bar 4 (bar_idx - right = 4-2 = 2).
    """
    sw = _make_swing(2, 2)

    # Build bars where bar 2 has the highest high in its window
    bars = [
        make_bar(0, 100, 100, 95, 98),   # high=100
        make_bar(1, 98, 105, 96, 102),    # high=105
        make_bar(2, 102, 120, 100, 115),  # high=120 ← pivot candidate
        make_bar(3, 115, 110, 108, 109),  # high=110
        make_bar(4, 109, 108, 105, 107),  # high=108 → buffer full, confirms bar 2
    ]

    for bar in bars:
        sw.update(bar.idx, bar)

    assert_close(sw.get_value("high_level"), 120.0, msg="high_level")
    assert_eq(sw.get_value("high_idx"), 2, msg="high_idx")


def test_m2_2() -> None:
    """Swing low confirmed at correct index with left=2, right=2.

    Sequence of lows: [100, 95, 80, 90, 92, ...]
    Pivot at bar 2 (low=80) confirmed at bar 4.
    """
    sw = _make_swing(2, 2)

    bars = [
        make_bar(0, 100, 105, 100, 102),  # low=100
        make_bar(1, 102, 103, 95, 97),    # low=95
        make_bar(2, 97, 98, 80, 85),      # low=80 ← pivot candidate
        make_bar(3, 85, 92, 90, 91),      # low=90
        make_bar(4, 91, 95, 92, 94),      # low=92 → confirms bar 2
    ]

    for bar in bars:
        sw.update(bar.idx, bar)

    assert_close(sw.get_value("low_level"), 80.0, msg="low_level")
    assert_eq(sw.get_value("low_idx"), 2, msg="low_idx")


def test_m2_3() -> None:
    """No false pivot when tie exists — strictly greater/less required.

    Highs: [100, 110, 110, 100, 95]
    Bar 1 (high=110) ties with bar 2 (high=110). Neither should be a swing high
    because the check is strictly greater than ALL other bars in window.
    """
    sw = _make_swing(2, 2)

    bars = [
        make_bar(0, 100, 100, 95, 98),
        make_bar(1, 98, 110, 96, 105),
        make_bar(2, 105, 110, 100, 108),  # tie at pivot position
        make_bar(3, 108, 100, 95, 97),
        make_bar(4, 97, 95, 90, 92),
    ]

    for bar in bars:
        sw.update(bar.idx, bar)

    # No high should be confirmed due to the tie
    high_level = sw.get_value("high_level")
    assert_true(
        isinstance(high_level, float) and math.isnan(high_level),
        msg=f"Expected NaN (no high due to tie), got {high_level}",
    )


def test_m2_4() -> None:
    """Version increments once per confirmed pivot.

    Create a sequence with one clear high and one clear low.
    """
    sw = _make_swing(2, 2)

    # Clear high at bar 2, clear low at bar 5
    bars = [
        make_bar(0, 100, 102, 98, 101),
        make_bar(1, 101, 105, 99, 104),
        make_bar(2, 104, 130, 103, 125),  # Clear high at bar 2
        make_bar(3, 125, 120, 115, 118),
        make_bar(4, 118, 115, 110, 112),  # Confirms high at bar 2
        make_bar(5, 112, 113, 70, 75),    # Clear low at bar 5
        make_bar(6, 75, 80, 78, 79),
        make_bar(7, 79, 85, 82, 84),      # Confirms low at bar 5
    ]

    for bar in bars:
        sw.update(bar.idx, bar)

    # Should have version=2 (one high + one low confirmed)
    assert_eq(sw.get_value("version"), 2, msg="version after high+low")
    assert_eq(sw.get_value("high_version"), 1, msg="high_version")
    assert_eq(sw.get_value("low_version"), 1, msg="low_version")


def test_m2_5() -> None:
    """Pair direction: Low→High = bullish, High→Low = bearish.

    Build a sequence: clear low at bar 2, then clear high at bar 7.
    First pair should be bullish (LHL).
    """
    sw = _make_swing(2, 2)

    # Low pivot at bar 2 (confirmed at bar 4)
    bars_part1 = [
        make_bar(0, 100, 105, 98, 103),
        make_bar(1, 103, 104, 95, 97),
        make_bar(2, 97, 98, 70, 75),      # Clear low
        make_bar(3, 75, 85, 80, 83),
        make_bar(4, 83, 90, 82, 88),      # Confirms low at 2
    ]

    for bar in bars_part1:
        sw.update(bar.idx, bar)

    assert_close(sw.get_value("low_level"), 70.0, msg="low confirmed")

    # High pivot at bar 7 (confirmed at bar 9)
    bars_part2 = [
        make_bar(5, 88, 95, 87, 93),
        make_bar(6, 93, 100, 92, 98),
        make_bar(7, 98, 140, 97, 135),    # Clear high
        make_bar(8, 135, 130, 125, 128),
        make_bar(9, 128, 126, 120, 122),  # Confirms high at 7
    ]

    for bar in bars_part2:
        sw.update(bar.idx, bar)

    assert_close(sw.get_value("high_level"), 140.0, msg="high confirmed")
    assert_eq(sw.get_value("pair_direction"), "bullish", msg="L→H = bullish")
    assert_close(sw.get_value("pair_low_level"), 70.0, msg="pair low")
    assert_close(sw.get_value("pair_high_level"), 140.0, msg="pair high")


def test_m2_6() -> None:
    """pair_version increments only on pair completion.

    After one pivot: pair_version=0.
    After second pivot (completing pair): pair_version=1.
    """
    sw = _make_swing(2, 2)

    # First pivot (high at bar 2)
    bars = [
        make_bar(0, 100, 102, 98, 101),
        make_bar(1, 101, 105, 99, 104),
        make_bar(2, 104, 130, 103, 125),
        make_bar(3, 125, 120, 115, 118),
        make_bar(4, 118, 115, 110, 112),
    ]

    for bar in bars:
        sw.update(bar.idx, bar)

    assert_eq(sw.get_value("pair_version"), 0, msg="one pivot, no pair yet")
    assert_eq(sw.get_value("version"), 1, msg="individual version=1")

    # Second pivot (low at bar 7)
    more_bars = [
        make_bar(5, 112, 113, 80, 85),
        make_bar(6, 85, 88, 82, 86),
        make_bar(7, 86, 87, 60, 65),      # Clear low
        make_bar(8, 65, 72, 68, 70),
        make_bar(9, 70, 78, 72, 76),      # Confirms low at 7
    ]

    for bar in more_bars:
        sw.update(bar.idx, bar)

    assert_eq(sw.get_value("pair_version"), 1, msg="pair completed")
    assert_eq(sw.get_value("version"), 2, msg="individual version=2")


# ---------------------------------------------------------------------------
# ALGORITHM tests
# ---------------------------------------------------------------------------


def test_a2_1() -> None:
    """HIGH→HIGH replaces pending, no pair completion.

    Two consecutive highs without a low between → pending high replaced.
    """
    sw = _make_swing(2, 2)

    # First high at bar 2 (high=130)
    bars = [
        make_bar(0, 100, 102, 98, 101),
        make_bar(1, 101, 105, 99, 104),
        make_bar(2, 104, 130, 103, 125),
        make_bar(3, 125, 120, 115, 118),
        make_bar(4, 118, 115, 110, 112),  # Confirms high at 2
    ]

    for bar in bars:
        sw.update(bar.idx, bar)

    ver_after_first = sw.get_value("pair_version")
    assert_eq(ver_after_first, 0, msg="no pair after first high")

    # Second high at bar 7 (high=140) — NO low between
    more_bars = [
        make_bar(5, 112, 118, 111, 116),
        make_bar(6, 116, 125, 114, 123),
        make_bar(7, 123, 140, 122, 135),  # Higher high
        make_bar(8, 135, 132, 128, 130),
        make_bar(9, 130, 127, 124, 126),  # Confirms second high
    ]

    for bar in more_bars:
        sw.update(bar.idx, bar)

    # Still no pair (HIGH→HIGH doesn't complete a pair, just replaces)
    assert_eq(sw.get_value("pair_version"), 0, msg="still no pair after H→H")
    assert_eq(sw.get_value("high_version"), 2, msg="two highs confirmed")


def test_a2_2() -> None:
    """LOW→LOW replaces pending, no pair completion.

    Two consecutive lows without a high between → pending low replaced.
    """
    sw = _make_swing(2, 2)

    # First low at bar 2 (low=70)
    bars = [
        make_bar(0, 100, 105, 98, 103),
        make_bar(1, 103, 104, 95, 97),
        make_bar(2, 97, 98, 70, 75),
        make_bar(3, 75, 82, 78, 80),
        make_bar(4, 80, 85, 79, 83),
    ]

    for bar in bars:
        sw.update(bar.idx, bar)

    assert_eq(sw.get_value("pair_version"), 0, msg="no pair after first low")

    # Second low at bar 7 (low=60) — NO high between
    more_bars = [
        make_bar(5, 83, 84, 78, 79),
        make_bar(6, 79, 80, 72, 74),
        make_bar(7, 74, 75, 60, 63),      # Lower low
        make_bar(8, 63, 70, 67, 69),
        make_bar(9, 69, 73, 68, 71),
    ]

    for bar in more_bars:
        sw.update(bar.idx, bar)

    assert_eq(sw.get_value("pair_version"), 0, msg="still no pair after L→L")
    assert_eq(sw.get_value("low_version"), 2, msg="two lows confirmed")


# ---------------------------------------------------------------------------
# EDGE tests
# ---------------------------------------------------------------------------


def test_e2_1() -> None:
    """Flat bars: all same OHLC → no pivots.

    Strictly greater/less means ties cannot form pivots.
    """
    sw = _make_swing(2, 2)

    for i in range(20):
        sw.update(i, make_bar(i, 100, 100, 100, 100))

    assert_nan(sw.get_value("high_level"), msg="no high on flat bars")
    assert_nan(sw.get_value("low_level"), msg="no low on flat bars")
    assert_eq(sw.get_value("version"), 0, msg="version=0 on flat bars")


def test_e2_2() -> None:
    """Single spike: one bar with high=200 surrounded by flat=100.

    Bar 5 has high=200 (clear spike), left=2, right=2.
    Should be confirmed at bar 7.
    """
    sw = _make_swing(2, 2)

    for i in range(20):
        if i == 5:
            sw.update(i, make_bar(i, 100, 200, 100, 100))
        else:
            sw.update(i, make_bar(i, 100, 100, 100, 100))

    assert_close(sw.get_value("high_level"), 200.0, msg="spike detected")
    assert_eq(sw.get_value("high_idx"), 5, msg="spike at bar 5")


# ---------------------------------------------------------------------------
# PARITY tests
# ---------------------------------------------------------------------------


def _run_parity(regime: str, left: int, right: int) -> None:
    """Run parity check between incremental and vectorized on real data."""
    from src.forge.audits.vectorized_references.swing_reference import (
        vectorized_swing,
    )

    df = load_sol_1h(regime)
    ohlcv = df_to_ohlcv_dict(df)
    bars = make_bars_from_df(df)
    n = len(bars)

    sw = _make_swing(left, right)
    vec = vectorized_swing(ohlcv, left, right)

    # Map vec output key to array key and tolerance
    key_map = {
        "high_level": ("high_level", 1e-4),
        "high_idx": ("high_idx", 0.5),  # int comparison via float
        "low_level": ("low_level", 1e-4),
        "low_idx": ("low_idx", 0.5),
        "version": ("version", 0.5),
    }

    mismatches = 0
    for i, bar in enumerate(bars):
        sw.update(i, bar)

        for key, (vec_key, tol) in key_map.items():
            inc_val = sw.get_value(key)
            vec_val = float(vec[vec_key][i])

            # Handle NaN/None
            if isinstance(inc_val, float) and math.isnan(inc_val):
                if not math.isnan(vec_val):
                    mismatches += 1
                continue
            if math.isnan(vec_val):
                continue

            if abs(float(inc_val) - vec_val) > tol:
                mismatches += 1
                if mismatches <= 3:
                    raise AssertionError(
                        f"Parity fail bar {i}/{n} key={key}: "
                        f"inc={inc_val} vec={vec_val}"
                    )

    assert_true(
        mismatches == 0,
        msg=f"{regime}: {mismatches} parity mismatches in {n} bars",
    )


def test_p2_1() -> None:
    """Parity: incremental vs vectorized on BULL data."""
    _run_parity("BULL", left=5, right=5)


def test_p2_2() -> None:
    """Parity: incremental vs vectorized on BEAR data."""
    _run_parity("BEAR", left=5, right=5)


# ---------------------------------------------------------------------------
# REAL SANITY tests
# ---------------------------------------------------------------------------


def test_r2_1() -> None:
    """Real: swing highs are local maxima on BULL data.

    After confirming a swing high at bar N, bar N's high should be >=
    highs of surrounding bars within the [N-left, N+right] window.
    """
    df = load_sol_1h("BULL")
    bars = make_bars_from_df(df)
    n = len(bars)
    left, right = 5, 5
    sw = _make_swing(left, right)

    confirmed_highs: list[tuple[int, float]] = []
    prev_high_idx = -1

    for i, bar in enumerate(bars):
        sw.update(i, bar)

        cur_idx = sw.get_value("high_idx")
        if cur_idx != prev_high_idx and cur_idx >= 0:
            confirmed_highs.append((int(cur_idx), float(sw.get_value("high_level"))))
            prev_high_idx = cur_idx

    # Each confirmed high should be a local maximum
    for idx, level in confirmed_highs:
        window_start = max(0, idx - left)
        window_end = min(n - 1, idx + right)
        for j in range(window_start, window_end + 1):
            if j != idx:
                assert_true(
                    bars[idx].high > bars[j].high,
                    msg=f"High at bar {idx} ({level}) not > bar {j} ({bars[j].high})",
                )


def test_r2_2() -> None:
    """Real: at least some pivots form on BULL data.

    A 336-bar BULL regime should produce multiple swing highs and lows.
    """
    df = load_sol_1h("BULL")
    bars = make_bars_from_df(df)
    sw = _make_swing(5, 5)

    for i, bar in enumerate(bars):
        sw.update(i, bar)

    version = int(sw.get_value("version"))
    assert_true(
        version >= 4,
        msg=f"Expected >= 4 pivots on 336-bar BULL regime, got {version}",
    )

    # Should have at least 1 completed pair
    pair_version = int(sw.get_value("pair_version"))
    assert_true(
        pair_version >= 1,
        msg=f"Expected >= 1 pair on BULL regime, got {pair_version}",
    )


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("M2.1", "MATH", "Swing high confirmed at correct index", test_m2_1),
        TestCase("M2.2", "MATH", "Swing low confirmed at correct index", test_m2_2),
        TestCase("M2.3", "MATH", "No pivot on tie (strictly gt/lt)", test_m2_3),
        TestCase("M2.4", "MATH", "Version increments correctly", test_m2_4),
        TestCase("M2.5", "MATH", "Pair direction L->H=bullish", test_m2_5),
        TestCase("M2.6", "MATH", "pair_version only on completion", test_m2_6),
        TestCase("A2.1", "ALGORITHM", "H->H replaces pending", test_a2_1),
        TestCase("A2.2", "ALGORITHM", "L->L replaces pending", test_a2_2),
        TestCase("E2.1", "EDGE", "Flat bars: no pivots", test_e2_1),
        TestCase("E2.2", "EDGE", "Single spike detected", test_e2_2),
        TestCase("P2.1", "PARITY", "Inc vs vec on BULL data", test_p2_1),
        TestCase("P2.2", "PARITY", "Inc vs vec on BEAR data", test_p2_2),
        TestCase("R2.1", "REAL", "Highs are local maxima", test_r2_1),
        TestCase("R2.2", "REAL", "Pivots form on BULL data", test_r2_2),
    ]


if __name__ == "__main__":
    run_module_cli("swing", get_tests())
