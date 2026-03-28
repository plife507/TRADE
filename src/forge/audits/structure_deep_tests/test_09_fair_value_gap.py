"""
Deep test: fair_value_gap detector (3-candle imbalance gaps).

Tests:
  M9.1 — Bullish FVG: c3.low > c1.high → gap detected
  M9.2 — Bearish FVG: c3.high < c1.low → gap detected
  M9.3 — No gap when candles overlap
  M9.4 — Gap mitigated at 50% fill
  M9.5 — Gap invalidated when close crosses boundary
  A9.1 — new_this_bar resets each bar
  A9.2 — active counts track correctly
  A9.3 — max_active enforced (oldest pruned)
  E9.1 — Flat candles: no gaps
  P9.1 — Parity: incremental vs vectorized on BULL data
  P9.2 — Parity on BEAR data
  R9.1 — Real BULL: FVGs form during rally
  R9.2 — Real: fill_pct between 0 and 1
"""

from __future__ import annotations

import math

from src.forge.audits.structure_deep_tests._harness import (
    TestCase,
    assert_close,
    assert_eq,
    assert_true,
    compute_atr_array,
    df_to_ohlcv_dict,
    load_sol_1h,
    make_bar,
    run_module_cli,
)
from src.structures.base import BarData
from src.structures.detectors.fair_value_gap import IncrementalFVG


def _make_fvg(max_active: int = 5) -> IncrementalFVG:
    return IncrementalFVG(
        {"atr_key": "atr", "min_gap_atr": 0.0, "max_active": max_active},
        deps=None,
    )


def _bar_atr(idx: int, o: float, h: float, l: float, c: float, atr: float = 10.0) -> BarData:
    return make_bar(idx, o, h, l, c, indicators={"atr": atr})


# ---------------------------------------------------------------------------
# MATH tests
# ---------------------------------------------------------------------------


def test_m9_1() -> None:
    """Bullish FVG: candle3.low > candle1.high.

    c1: high=105. c2: any. c3: low=108 > 105 → bullish gap [105, 108].
    """
    fvg = _make_fvg()

    fvg.update(0, _bar_atr(0, 100, 105, 98, 103))  # c1: high=105
    fvg.update(1, _bar_atr(1, 103, 115, 102, 112))  # c2: large candle
    fvg.update(2, _bar_atr(2, 112, 120, 108, 118))  # c3: low=108 > 105

    assert_eq(fvg.get_value("new_this_bar"), True, msg="FVG detected")
    assert_eq(fvg.get_value("new_direction"), 1, msg="bullish direction")
    assert_close(fvg.get_value("new_lower"), 105.0, tol=0.01, msg="gap lower")
    assert_close(fvg.get_value("new_upper"), 108.0, tol=0.01, msg="gap upper")


def test_m9_2() -> None:
    """Bearish FVG: candle3.high < candle1.low.

    c1: low=95. c2: large drop. c3: high=92 < 95 → bearish gap [92, 95].
    """
    fvg = _make_fvg()

    fvg.update(0, _bar_atr(0, 100, 102, 95, 97))    # c1: low=95
    fvg.update(1, _bar_atr(1, 97, 98, 85, 87))       # c2: big drop
    fvg.update(2, _bar_atr(2, 87, 92, 80, 82))       # c3: high=92 < 95

    assert_eq(fvg.get_value("new_this_bar"), True, msg="FVG detected")
    assert_eq(fvg.get_value("new_direction"), -1, msg="bearish direction")
    assert_close(fvg.get_value("new_lower"), 92.0, tol=0.01, msg="gap lower")
    assert_close(fvg.get_value("new_upper"), 95.0, tol=0.01, msg="gap upper")


def test_m9_3() -> None:
    """No gap when candles overlap (c3.low <= c1.high for bullish)."""
    fvg = _make_fvg()

    fvg.update(0, _bar_atr(0, 100, 110, 98, 108))   # c1: high=110
    fvg.update(1, _bar_atr(1, 108, 112, 105, 110))   # c2
    fvg.update(2, _bar_atr(2, 110, 115, 109, 113))   # c3: low=109 < 110

    assert_eq(fvg.get_value("new_this_bar"), False, msg="no gap with overlap")


def test_m9_4() -> None:
    """Bullish FVG mitigated at 50% fill.

    Gap [105, 108], gap_range=3. 50% fill → price touches 106.5.
    Bar low = 106 → fill_pct = (108-106)/3 = 0.667 > 0.5 → mitigated.
    """
    fvg = _make_fvg()

    # Create bullish FVG
    fvg.update(0, _bar_atr(0, 100, 105, 98, 103))
    fvg.update(1, _bar_atr(1, 103, 115, 102, 112))
    fvg.update(2, _bar_atr(2, 112, 120, 108, 118))

    assert_eq(fvg.get_value("new_this_bar"), True, msg="FVG created")
    assert_eq(int(fvg.get_value("active_bull_count")), 1, msg="1 active bull")

    # Price retraces into gap: low=106 → fill_pct = (108-106)/3 = 0.667
    fvg.update(3, _bar_atr(3, 118, 119, 106, 108))

    mitigated = fvg.get_value("any_mitigated_this_bar")
    assert_eq(mitigated, True, msg="FVG should be mitigated at 0.667 fill")


def test_m9_5() -> None:
    """Bullish FVG invalidated when close < lower.

    Gap [105, 108]. Close=100 < 105 → invalidated.
    """
    fvg = _make_fvg()

    fvg.update(0, _bar_atr(0, 100, 105, 98, 103))
    fvg.update(1, _bar_atr(1, 103, 115, 102, 112))
    fvg.update(2, _bar_atr(2, 112, 120, 108, 118))

    # Price crashes below gap
    fvg.update(3, _bar_atr(3, 118, 118, 95, 100))

    # Gap should be invalidated (active count drops)
    assert_eq(int(fvg.get_value("active_bull_count")), 0, msg="gap invalidated")


# ---------------------------------------------------------------------------
# ALGORITHM tests
# ---------------------------------------------------------------------------


def test_a9_1() -> None:
    """new_this_bar resets each bar."""
    fvg = _make_fvg()

    fvg.update(0, _bar_atr(0, 100, 105, 98, 103))
    fvg.update(1, _bar_atr(1, 103, 115, 102, 112))
    fvg.update(2, _bar_atr(2, 112, 120, 108, 118))  # FVG fires
    assert_eq(fvg.get_value("new_this_bar"), True, msg="FVG on bar 2")

    fvg.update(3, _bar_atr(3, 118, 119, 114, 117))  # low=114 < bar1.high=115 → no new FVG
    assert_eq(fvg.get_value("new_this_bar"), False, msg="reset on bar 3")


def test_a9_2() -> None:
    """Active counts track correctly."""
    fvg = _make_fvg()

    # No active initially
    fvg.update(0, _bar_atr(0, 100, 100, 100, 100))
    assert_eq(int(fvg.get_value("active_bull_count")), 0, msg="initial bull=0")
    assert_eq(int(fvg.get_value("active_bear_count")), 0, msg="initial bear=0")


def test_a9_3() -> None:
    """max_active enforced — oldest pruned."""
    fvg = _make_fvg(max_active=1)

    # Create first bullish FVG
    fvg.update(0, _bar_atr(0, 100, 105, 98, 103))
    fvg.update(1, _bar_atr(1, 103, 115, 102, 112))
    fvg.update(2, _bar_atr(2, 112, 120, 108, 118))
    assert_eq(int(fvg.get_value("active_bull_count")), 1, msg="first FVG")

    # Create second bullish FVG (should prune first)
    fvg.update(3, _bar_atr(3, 118, 122, 115, 120))
    fvg.update(4, _bar_atr(4, 120, 135, 119, 132))
    fvg.update(5, _bar_atr(5, 132, 142, 125, 140))  # low=125 > high=122

    count = int(fvg.get_value("active_bull_count"))
    assert_true(count <= 1, msg=f"max_active=1 but count={count}")


# ---------------------------------------------------------------------------
# EDGE tests
# ---------------------------------------------------------------------------


def test_e9_1() -> None:
    """Flat candles produce no gaps."""
    fvg = _make_fvg()
    for i in range(10):
        fvg.update(i, _bar_atr(i, 100, 100, 100, 100))

    assert_eq(fvg.get_value("new_this_bar"), False, msg="no gap on flat")
    assert_eq(int(fvg.get_value("active_bull_count")), 0, msg="no bull gaps")
    assert_eq(int(fvg.get_value("active_bear_count")), 0, msg="no bear gaps")


# ---------------------------------------------------------------------------
# PARITY tests
# ---------------------------------------------------------------------------


def _run_fvg_parity(regime: str) -> None:
    """Run FVG parity check."""
    from src.forge.audits.vectorized_references.fair_value_gap_reference import (
        vectorized_fair_value_gap,
    )

    df = load_sol_1h(regime)
    ohlcv = df_to_ohlcv_dict(df)
    atr_arr = compute_atr_array(ohlcv["high"], ohlcv["low"], ohlcv["close"], 14)
    n = len(df)

    bars = []
    for i in range(n):
        indicators: dict[str, float] = {}
        if not math.isnan(atr_arr[i]):
            indicators["atr"] = float(atr_arr[i])
        bars.append(BarData(
            idx=i, open=float(df["open"].iloc[i]), high=float(df["high"].iloc[i]),
            low=float(df["low"].iloc[i]), close=float(df["close"].iloc[i]),
            volume=float(df["volume"].iloc[i]), indicators=indicators,
        ))

    fvg = _make_fvg()
    vec = vectorized_fair_value_gap(ohlcv, atr_arr)

    mismatches = 0
    for i, bar in enumerate(bars):
        fvg.update(i, bar)

        inc_new = fvg.get_value("new_this_bar")
        vec_new = bool(vec["new_this_bar"][i])
        if inc_new != vec_new:
            mismatches += 1

    threshold = max(3, n // 50)
    assert_true(
        mismatches <= threshold,
        msg=f"{regime} FVG: {mismatches} new_this_bar mismatches in {n} bars (threshold {threshold})",
    )


def test_p9_1() -> None:
    """Parity on BULL data."""
    _run_fvg_parity("BULL")


def test_p9_2() -> None:
    """Parity on BEAR data."""
    _run_fvg_parity("BEAR")


# ---------------------------------------------------------------------------
# REAL SANITY tests
# ---------------------------------------------------------------------------


def test_r9_1() -> None:
    """Real BULL: FVGs form during rally."""
    df = load_sol_1h("BULL")
    ohlcv = df_to_ohlcv_dict(df)
    atr_arr = compute_atr_array(ohlcv["high"], ohlcv["low"], ohlcv["close"], 14)

    bars = []
    for i in range(len(df)):
        indicators: dict[str, float] = {}
        if not math.isnan(atr_arr[i]):
            indicators["atr"] = float(atr_arr[i])
        bars.append(BarData(
            idx=i, open=float(df["open"].iloc[i]), high=float(df["high"].iloc[i]),
            low=float(df["low"].iloc[i]), close=float(df["close"].iloc[i]),
            volume=float(df["volume"].iloc[i]), indicators=indicators,
        ))

    fvg = _make_fvg()
    total_gaps = 0
    for bar in bars:
        fvg.update(bar.idx, bar)
        if fvg.get_value("new_this_bar"):
            total_gaps += 1

    assert_true(total_gaps > 0, msg=f"No FVGs on BULL regime")


def test_r9_2() -> None:
    """Real: fill_pct outputs are between 0 and 1 when valid."""
    df = load_sol_1h("BULL")
    ohlcv = df_to_ohlcv_dict(df)
    atr_arr = compute_atr_array(ohlcv["high"], ohlcv["low"], ohlcv["close"], 14)

    bars = []
    for i in range(len(df)):
        indicators: dict[str, float] = {}
        if not math.isnan(atr_arr[i]):
            indicators["atr"] = float(atr_arr[i])
        bars.append(BarData(
            idx=i, open=float(df["open"].iloc[i]), high=float(df["high"].iloc[i]),
            low=float(df["low"].iloc[i]), close=float(df["close"].iloc[i]),
            volume=float(df["volume"].iloc[i]), indicators=indicators,
        ))

    fvg = _make_fvg()
    checked = False
    for bar in bars:
        fvg.update(bar.idx, bar)
        bull_fp = fvg.get_value("nearest_bull_fill_pct")
        bear_fp = fvg.get_value("nearest_bear_fill_pct")

        for fp in [bull_fp, bear_fp]:
            if isinstance(fp, float) and not math.isnan(fp):
                assert_true(
                    0.0 <= fp <= 1.0,
                    msg=f"fill_pct={fp} out of [0,1] at bar {bar.idx}",
                )
                checked = True

    assert_true(checked, msg="Never had valid fill_pct values")


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("M9.1", "MATH", "Bullish FVG detection", test_m9_1),
        TestCase("M9.2", "MATH", "Bearish FVG detection", test_m9_2),
        TestCase("M9.3", "MATH", "No gap on overlap", test_m9_3),
        TestCase("M9.4", "MATH", "Mitigated at 50% fill", test_m9_4),
        TestCase("M9.5", "MATH", "Invalidated on close cross", test_m9_5),
        TestCase("A9.1", "ALGORITHM", "new_this_bar resets", test_a9_1),
        TestCase("A9.2", "ALGORITHM", "Active counts", test_a9_2),
        TestCase("A9.3", "ALGORITHM", "max_active enforced", test_a9_3),
        TestCase("E9.1", "EDGE", "Flat candles: no gaps", test_e9_1),
        TestCase("P9.1", "PARITY", "Inc vs vec (BULL)", test_p9_1),
        TestCase("P9.2", "PARITY", "Inc vs vec (BEAR)", test_p9_2),
        TestCase("R9.1", "REAL", "FVGs form (BULL)", test_r9_1),
        TestCase("R9.2", "REAL", "fill_pct in [0,1]", test_r9_2),
    ]


if __name__ == "__main__":
    run_module_cli("fair_value_gap", get_tests())
