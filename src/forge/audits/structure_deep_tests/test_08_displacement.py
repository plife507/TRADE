"""
Deep test: displacement detector (strong impulsive candles via ATR).

Tests:
  M8.1 — Bullish displacement: large body, small wicks, close > open
  M8.2 — Bearish displacement: large body, small wicks, close < open
  M8.3 — Body/ATR ratio below threshold → no displacement
  M8.4 — Wick ratio above threshold → no displacement
  E8.1 — Doji candle (body=0) → no displacement
  E8.2 — No ATR indicator → no displacement
  P8.1 — Parity: incremental vs vectorized on BEAR data
  R8.1 — Real BEAR: displacement events fire during sell-off
  R8.2 — Real CONSOLIDATION: few/no displacement events
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
    make_bars_from_df,
    run_module_cli,
)
from src.structures.base import BarData
from src.structures.detectors.displacement import IncrementalDisplacement


def _make_disp(
    body_atr_min: float = 1.5,
    wick_ratio_max: float = 0.4,
) -> IncrementalDisplacement:
    return IncrementalDisplacement(
        {"atr_key": "atr", "body_atr_min": body_atr_min,
         "wick_ratio_max": wick_ratio_max},
        deps=None,
    )


def _bar_atr(idx: int, o: float, h: float, l: float, c: float, atr: float) -> BarData:
    return make_bar(idx, o, h, l, c, indicators={"atr": atr})


# ---------------------------------------------------------------------------
# MATH tests
# ---------------------------------------------------------------------------


def test_m8_1() -> None:
    """Bullish displacement: body/ATR=2.0 (>1.5), wick_ratio=0.2 (<0.4).

    open=100, close=120, high=122, low=99. ATR=10.
    body = 20, body_atr = 20/10 = 2.0.
    upper_wick = 122-120 = 2, lower_wick = 100-99 = 1. wick_ratio = 3/20 = 0.15.
    """
    d = _make_disp()
    bar = _bar_atr(0, 100, 122, 99, 120, 10.0)
    d.update(0, bar)

    assert_eq(d.get_value("is_displacement"), True, msg="should detect displacement")
    assert_eq(d.get_value("direction"), 1, msg="bullish direction")
    assert_close(d.get_value("body_atr_ratio"), 2.0, tol=0.01, msg="body_atr_ratio")
    assert_close(d.get_value("wick_ratio"), 0.15, tol=0.01, msg="wick_ratio")


def test_m8_2() -> None:
    """Bearish displacement: close < open.

    open=120, close=100, high=121, low=99. ATR=10.
    body = 20, direction = -1.
    """
    d = _make_disp()
    bar = _bar_atr(0, 120, 121, 99, 100, 10.0)
    d.update(0, bar)

    assert_eq(d.get_value("is_displacement"), True, msg="should detect")
    assert_eq(d.get_value("direction"), -1, msg="bearish direction")


def test_m8_3() -> None:
    """Body/ATR below threshold → no displacement.

    open=100, close=105, ATR=10. body_atr=0.5 < 1.5.
    """
    d = _make_disp()
    bar = _bar_atr(0, 100, 106, 99, 105, 10.0)
    d.update(0, bar)

    assert_eq(d.get_value("is_displacement"), False, msg="small body → no displacement")


def test_m8_4() -> None:
    """Wick ratio above threshold → no displacement.

    open=100, close=120, high=140, low=80. ATR=10.
    body=20, upper_wick=20, lower_wick=20. wick_ratio=40/20=2.0 > 0.4.
    """
    d = _make_disp()
    bar = _bar_atr(0, 100, 140, 80, 120, 10.0)
    d.update(0, bar)

    assert_eq(d.get_value("is_displacement"), False, msg="large wicks → no displacement")


# ---------------------------------------------------------------------------
# EDGE tests
# ---------------------------------------------------------------------------


def test_e8_1() -> None:
    """Doji (body=0) → no displacement."""
    d = _make_disp()
    bar = _bar_atr(0, 100, 110, 90, 100, 10.0)
    d.update(0, bar)

    assert_eq(d.get_value("is_displacement"), False, msg="doji → no displacement")


def test_e8_2() -> None:
    """No ATR indicator → no displacement."""
    d = _make_disp()
    bar = make_bar(0, 100, 130, 99, 125)  # No ATR
    d.update(0, bar)

    assert_eq(d.get_value("is_displacement"), False, msg="no ATR → no displacement")


# ---------------------------------------------------------------------------
# PARITY tests
# ---------------------------------------------------------------------------


def test_p8_1() -> None:
    """Parity: incremental vs vectorized on BEAR data."""
    from src.forge.audits.vectorized_references.displacement_reference import (
        vectorized_displacement,
    )

    df = load_sol_1h("BEAR")
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

    d = _make_disp()
    vec = vectorized_displacement(ohlcv, atr_arr)

    mismatches = 0
    for i, bar in enumerate(bars):
        d.update(i, bar)
        inc_det = d.get_value("is_displacement")
        vec_det = bool(vec["is_displacement"][i])
        if inc_det != vec_det:
            mismatches += 1

    threshold = max(3, n // 100)
    assert_true(
        mismatches <= threshold,
        msg=f"BEAR: {mismatches} displacement mismatches in {n} bars (threshold {threshold})",
    )


# ---------------------------------------------------------------------------
# REAL SANITY tests
# ---------------------------------------------------------------------------


def test_r8_1() -> None:
    """Real BEAR: displacement events fire during sell-off."""
    df = load_sol_1h("BEAR")
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

    d = _make_disp()
    count = 0
    for bar in bars:
        d.update(bar.idx, bar)
        if d.get_value("is_displacement"):
            count += 1

    assert_true(count > 0, msg=f"No displacements on BEAR regime ({count})")


def test_r8_2() -> None:
    """Real CONSOLIDATION: fewer displacement events than trending regime."""
    df = load_sol_1h("CONSOLIDATION")
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

    d = _make_disp()
    count = 0
    for bar in bars:
        d.update(bar.idx, bar)
        if d.get_value("is_displacement"):
            count += 1

    # Consolidation should have low displacement rate
    rate = count / len(bars) if len(bars) > 0 else 0
    assert_true(
        rate < 0.3,
        msg=f"CONSOLIDATION: {rate:.0%} displacement rate (expected < 30%)",
    )


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("M8.1", "MATH", "Bullish displacement detected", test_m8_1),
        TestCase("M8.2", "MATH", "Bearish displacement detected", test_m8_2),
        TestCase("M8.3", "MATH", "Below body_atr threshold", test_m8_3),
        TestCase("M8.4", "MATH", "Above wick_ratio threshold", test_m8_4),
        TestCase("E8.1", "EDGE", "Doji → no displacement", test_e8_1),
        TestCase("E8.2", "EDGE", "No ATR → no displacement", test_e8_2),
        TestCase("P8.1", "PARITY", "Inc vs vec (BEAR)", test_p8_1),
        TestCase("R8.1", "REAL", "BEAR: displacements fire", test_r8_1),
        TestCase("R8.2", "REAL", "CONSOLIDATION: low rate", test_r8_2),
    ]


if __name__ == "__main__":
    run_module_cli("displacement", get_tests())
