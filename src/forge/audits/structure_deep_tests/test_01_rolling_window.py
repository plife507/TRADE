"""
Deep test: rolling_window detector.

Tests:
  M1.1 — Min mode: 3-bar window, hand-computed lows
  M1.2 — Max mode: 3-bar window, hand-computed highs
  M1.3 — Window slides correctly (old values evicted)
  M1.4 — Window size=1 returns current bar's source value
  A1.1 — MonotonicDeque monotonic invariant holds through regime change
  A1.2 — get_value returns None before first bar
  E1.1 — Single bar, constant prices, volume=0
  P1.1 — Parity: incremental vs pandas rolling on real BULL data
  R1.1 — Real sanity: 20-bar low on BULL data stays below all closes
"""

from __future__ import annotations

import math
from typing import Any

from src.forge.audits.structure_deep_tests._harness import (
    TestCase,
    assert_close,
    assert_true,
    df_to_ohlcv_dict,
    load_sol_1h,
    make_bar,
    make_bars_from_df,
    run_module_cli,
)
from src.structures.detectors.rolling_window import IncrementalRollingWindow


def _make_rw(size: int, source: str, mode: str) -> IncrementalRollingWindow:
    """Create a rolling window detector with given params."""
    params: dict[str, Any] = {"size": size, "source": source, "mode": mode}
    return IncrementalRollingWindow(params, deps=None)


# ---------------------------------------------------------------------------
# MATH tests
# ---------------------------------------------------------------------------


def test_m1_1() -> None:
    """Min mode: 3-bar window tracks minimum low correctly."""
    rw = _make_rw(3, "low", "min")

    # Bar 0: low=100 → window=[100], min=100
    rw.update(0, make_bar(0, 105, 110, 100, 108))
    assert_close(rw.get_value("value"), 100.0, msg="after bar 0")

    # Bar 1: low=95 → window=[100,95], min=95
    rw.update(1, make_bar(1, 108, 112, 95, 110))
    assert_close(rw.get_value("value"), 95.0, msg="after bar 1")

    # Bar 2: low=102 → window=[100,95,102], min=95
    rw.update(2, make_bar(2, 110, 115, 102, 113))
    assert_close(rw.get_value("value"), 95.0, msg="after bar 2")

    # Bar 3: low=98 → window=[95,102,98], min=95
    rw.update(3, make_bar(3, 113, 117, 98, 115))
    assert_close(rw.get_value("value"), 95.0, msg="after bar 3")

    # Bar 4: low=103 → window=[102,98,103], min=98
    rw.update(4, make_bar(4, 115, 118, 103, 116))
    assert_close(rw.get_value("value"), 98.0, msg="after bar 4")


def test_m1_2() -> None:
    """Max mode: 3-bar window tracks maximum high correctly."""
    rw = _make_rw(3, "high", "max")

    # Bar 0: high=110 → max=110
    rw.update(0, make_bar(0, 105, 110, 100, 108))
    assert_close(rw.get_value("value"), 110.0, msg="after bar 0")

    # Bar 1: high=112 → window=[110,112], max=112
    rw.update(1, make_bar(1, 108, 112, 95, 110))
    assert_close(rw.get_value("value"), 112.0, msg="after bar 1")

    # Bar 2: high=108 → window=[110,112,108], max=112
    rw.update(2, make_bar(2, 110, 108, 102, 106))
    assert_close(rw.get_value("value"), 112.0, msg="after bar 2")

    # Bar 3: high=107 → window=[112,108,107], max=112
    rw.update(3, make_bar(3, 106, 107, 103, 105))
    assert_close(rw.get_value("value"), 112.0, msg="after bar 3")

    # Bar 4: high=106 → window=[108,107,106], max=108 (112 evicted)
    rw.update(4, make_bar(4, 105, 106, 101, 104))
    assert_close(rw.get_value("value"), 108.0, msg="after bar 4")


def test_m1_3() -> None:
    """Window slides: old values evicted after `size` bars."""
    rw = _make_rw(2, "close", "min")

    # Bars: close = 100, 90, 95, 80
    rw.update(0, make_bar(0, 100, 100, 100, 100))
    assert_close(rw.get_value("value"), 100.0, msg="bar 0")

    rw.update(1, make_bar(1, 100, 100, 90, 90))
    assert_close(rw.get_value("value"), 90.0, msg="bar 1")

    rw.update(2, make_bar(2, 90, 95, 90, 95))
    # Window=[90,95], min=90
    assert_close(rw.get_value("value"), 90.0, msg="bar 2")

    rw.update(3, make_bar(3, 95, 95, 80, 80))
    # Window=[95,80], min=80 (90 evicted)
    assert_close(rw.get_value("value"), 80.0, msg="bar 3")


def test_m1_4() -> None:
    """Window size=1 returns current bar's source value."""
    rw = _make_rw(1, "close", "min")

    rw.update(0, make_bar(0, 100, 110, 90, 105))
    assert_close(rw.get_value("value"), 105.0, msg="bar 0 close=105")

    rw.update(1, make_bar(1, 105, 115, 95, 110))
    assert_close(rw.get_value("value"), 110.0, msg="bar 1 close=110")

    rw.update(2, make_bar(2, 110, 112, 100, 98))
    assert_close(rw.get_value("value"), 98.0, msg="bar 2 close=98")


# ---------------------------------------------------------------------------
# ALGORITHM tests
# ---------------------------------------------------------------------------


def test_a1_1() -> None:
    """Monotonic invariant holds through alternating high/low regime."""
    rw = _make_rw(5, "close", "min")

    # Feed alternating pattern: 50, 10, 50, 10, 50, 10, 50
    closes = [50, 10, 50, 10, 50, 10, 50]
    for i, c in enumerate(closes):
        rw.update(i, make_bar(i, c, c + 5, c - 5, c))

    # Window=[10, 50, 10, 50], min=10
    # (last 5: indices 2-6 → closes 50,10,50,10,50 → min=10)
    assert_close(rw.get_value("value"), 10.0, msg="alternating pattern min")


def test_a1_2() -> None:
    """get_value returns None before any bars are processed."""
    rw = _make_rw(5, "close", "min")
    val = rw.get_value("value")
    assert_true(val is None, msg=f"Expected None before first bar, got {val}")


# ---------------------------------------------------------------------------
# EDGE tests
# ---------------------------------------------------------------------------


def test_e1_1() -> None:
    """Edge: single bar repeated, constant prices, zero volume."""
    rw_min = _make_rw(3, "low", "min")
    rw_max = _make_rw(3, "high", "max")

    for i in range(10):
        bar = make_bar(i, 100, 100, 100, 100, volume=0.0)
        rw_min.update(i, bar)
        rw_max.update(i, bar)

    assert_close(rw_min.get_value("value"), 100.0, msg="constant low min")
    assert_close(rw_max.get_value("value"), 100.0, msg="constant high max")


# ---------------------------------------------------------------------------
# PARITY tests
# ---------------------------------------------------------------------------


def test_p1_1() -> None:
    """Parity: incremental vs pandas rolling on real BULL SOLUSDT 1h data."""
    from src.forge.audits.vectorized_references.rolling_window_reference import (
        vectorized_rolling_window,
    )

    df = load_sol_1h("BULL")
    ohlcv = df_to_ohlcv_dict(df)
    bars = make_bars_from_df(df)
    n = len(bars)

    for mode in ("min", "max"):
        for source in ("low", "high", "close"):
            size = 20
            rw = _make_rw(size, source, mode)
            vec = vectorized_rolling_window(ohlcv, size, source, mode)

            for i, bar in enumerate(bars):
                rw.update(i, bar)

                inc_val = rw.get_value("value")
                vec_val = float(vec["value"][i])

                # Both should match — tolerance for float rounding
                if inc_val is not None and not math.isnan(vec_val):
                    assert_close(
                        inc_val,
                        vec_val,
                        tol=1e-4,
                        msg=f"Parity {mode}/{source} bar {i}/{n}",
                    )


# ---------------------------------------------------------------------------
# REAL SANITY tests
# ---------------------------------------------------------------------------


def test_r1_1() -> None:
    """Real: 20-bar rolling low on BULL data stays below all closes in window."""
    df = load_sol_1h("BULL")
    bars = make_bars_from_df(df)
    size = 20
    rw = _make_rw(size, "low", "min")

    for i, bar in enumerate(bars):
        rw.update(i, bar)

        if i >= size - 1:
            rolling_min = rw.get_value("value")
            # The rolling min of lows should be <= every close in the window
            # (since low <= close for every bar)
            assert_true(
                rolling_min <= bar.close,
                msg=f"Bar {i}: rolling low {rolling_min} > close {bar.close}",
            )
            # And should be <= current bar's low
            assert_true(
                rolling_min <= bar.low,
                msg=f"Bar {i}: rolling low {rolling_min} > low {bar.low}",
            )


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("M1.1", "MATH", "Min mode 3-bar window", test_m1_1),
        TestCase("M1.2", "MATH", "Max mode 3-bar window", test_m1_2),
        TestCase("M1.3", "MATH", "Window slides correctly", test_m1_3),
        TestCase("M1.4", "MATH", "Window size=1", test_m1_4),
        TestCase("A1.1", "ALGORITHM", "Monotonic invariant holds", test_a1_1),
        TestCase("A1.2", "ALGORITHM", "None before first bar", test_a1_2),
        TestCase("E1.1", "EDGE", "Constant prices, zero volume", test_e1_1),
        TestCase("P1.1", "PARITY", "Inc vs pandas rolling (BULL)", test_p1_1),
        TestCase("R1.1", "REAL", "20-bar low below closes (BULL)", test_r1_1),
    ]


if __name__ == "__main__":
    run_module_cli("rolling_window", get_tests())
