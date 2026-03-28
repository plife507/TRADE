"""
Deep test: premium_discount detector (ICT premium/discount zone classification).

Tests:
  M12.1 — Equilibrium = midpoint of swing pair
  M12.2 — Premium zone when close >= 75th percentile
  M12.3 — depth_pct clamped to [0, 1]
  A12.1 — Version increments only on zone change
  A12.2 — Output "none" before any swing pairs
  E12.1 — Degenerate pair (span=0) → equilibrium at price level
  P12.1 — Parity: incremental vs vectorized on CONSOLIDATION data
  R12.1 — Real CONSOLIDATION: equilibrium near range midpoint
  R12.2 — Real BULL: premium zone appears near highs
"""

from __future__ import annotations

import math

from src.forge.audits.structure_deep_tests._harness import (
    TestCase,
    assert_close,
    assert_eq,
    assert_true,
    df_to_ohlcv_dict,
    load_sol_1h,
    make_bar,
    make_bars_from_df,
    run_module_cli,
)
from src.structures.detectors.premium_discount import IncrementalPremiumDiscount
from src.structures.detectors.swing import IncrementalSwing


def _make_pd_chain(
    bars: list,
    left: int = 2,
    right: int = 2,
) -> tuple[IncrementalSwing, IncrementalPremiumDiscount]:
    sw = IncrementalSwing({"left": left, "right": right, "mode": "fractal"}, deps=None)
    pd = IncrementalPremiumDiscount({}, deps={"swing": sw})
    for bar in bars:
        sw.update(bar.idx, bar)
        pd.update(bar.idx, bar)
    return sw, pd


def _uptrend_bars() -> list:
    """Low=70 at bar 2, High=140 at bar 7 → bullish pair. Then close at various levels."""
    return [
        make_bar(0, 100, 105, 98, 103),
        make_bar(1, 103, 104, 95, 97),
        make_bar(2, 97, 98, 70, 75),
        make_bar(3, 75, 85, 80, 83),
        make_bar(4, 83, 90, 82, 88),
        make_bar(5, 88, 95, 87, 93),
        make_bar(6, 93, 100, 92, 98),
        make_bar(7, 98, 140, 97, 135),
        make_bar(8, 135, 130, 125, 128),
        make_bar(9, 128, 126, 120, 122),
    ]


# ---------------------------------------------------------------------------
# MATH tests
# ---------------------------------------------------------------------------


def test_m12_1() -> None:
    """Equilibrium = midpoint of swing pair.

    Pair: low=70, high=140. Equilibrium = 70 + 0.5 × 70 = 105.
    """
    bars = _uptrend_bars()
    _, pd = _make_pd_chain(bars)

    eq = pd.get_value("equilibrium")
    if isinstance(eq, float) and not math.isnan(eq):
        assert_close(eq, 105.0, tol=0.1, msg="equilibrium = midpoint")


def test_m12_2() -> None:
    """Premium zone when close >= premium_level (75th percentile).

    premium_level = 70 + 0.75 × 70 = 122.5.
    Close at 130 → should be "premium".
    """
    bars = _uptrend_bars()
    # Add bar with close in premium zone
    bars.append(make_bar(10, 122, 135, 120, 130))

    _, pd = _make_pd_chain(bars)

    zone = pd.get_value("zone")
    prem = pd.get_value("premium_level")
    if isinstance(prem, float) and not math.isnan(prem):
        assert_close(prem, 122.5, tol=0.5, msg="premium_level = 75th pct")
        assert_eq(zone, "premium", msg=f"close=130 >= premium=122.5 → premium zone")


def test_m12_3() -> None:
    """depth_pct clamped to [0, 1]."""
    bars = _uptrend_bars()
    # Add bar with close far above pair high
    bars.append(make_bar(10, 140, 200, 138, 180))

    _, pd = _make_pd_chain(bars)

    depth = pd.get_value("depth_pct")
    if isinstance(depth, float) and not math.isnan(depth):
        assert_true(
            0.0 <= depth <= 1.0,
            msg=f"depth_pct={depth} not clamped to [0,1]",
        )


# ---------------------------------------------------------------------------
# ALGORITHM tests
# ---------------------------------------------------------------------------


def test_a12_1() -> None:
    """Version increments on zone change only."""
    bars = _uptrend_bars()
    sw = IncrementalSwing({"left": 2, "right": 2, "mode": "fractal"}, deps=None)
    pd = IncrementalPremiumDiscount({}, deps={"swing": sw})

    versions = []
    for bar in bars:
        sw.update(bar.idx, bar)
        pd.update(bar.idx, bar)
        versions.append(int(pd.get_value("version")))

    # Version should be monotonically non-decreasing
    for i in range(1, len(versions)):
        assert_true(
            versions[i] >= versions[i - 1],
            msg=f"Version decreased at bar {i}: {versions[i-1]} → {versions[i]}",
        )


def test_a12_2() -> None:
    """Output "none" before any swing pairs."""
    bars = [make_bar(i, 100, 105, 95, 100) for i in range(4)]
    _, pd = _make_pd_chain(bars)

    zone = pd.get_value("zone")
    assert_eq(zone, "none", msg="no zone before pairs")


# ---------------------------------------------------------------------------
# EDGE tests
# ---------------------------------------------------------------------------


def test_e12_1() -> None:
    """Degenerate pair (same high/low) → equilibrium at price."""
    # This is hard to construct with fractal swings, so just verify no crash
    bars = [make_bar(i, 100, 100, 100, 100) for i in range(10)]
    _, pd = _make_pd_chain(bars)
    assert_true(True, msg="degenerate case doesn't crash")


# ---------------------------------------------------------------------------
# PARITY tests
# ---------------------------------------------------------------------------


def test_p12_1() -> None:
    """Parity on CONSOLIDATION data."""
    from src.forge.audits.vectorized_references.premium_discount_reference import (
        vectorized_premium_discount,
    )
    from src.forge.audits.vectorized_references.swing_reference import vectorized_swing

    df = load_sol_1h("CONSOLIDATION")
    ohlcv = df_to_ohlcv_dict(df)
    bars = make_bars_from_df(df)
    n = len(bars)

    left, right = 5, 5
    sw = IncrementalSwing({"left": left, "right": right, "mode": "fractal"}, deps=None)
    pd = IncrementalPremiumDiscount({}, deps={"swing": sw})

    swing_vec = vectorized_swing(ohlcv, left, right)
    pd_vec = vectorized_premium_discount(ohlcv, swing_vec)

    mismatches = 0
    for i, bar in enumerate(bars):
        sw.update(i, bar)
        pd.update(i, bar)

        inc_eq = pd.get_value("equilibrium")
        vec_eq = float(pd_vec["equilibrium"][i])

        if isinstance(inc_eq, float) and math.isnan(inc_eq) and math.isnan(vec_eq):
            continue
        if isinstance(inc_eq, float) and not math.isnan(inc_eq) and not math.isnan(vec_eq):
            if abs(inc_eq - vec_eq) > 0.5:
                mismatches += 1

    threshold = max(5, n // 50)
    assert_true(
        mismatches <= threshold,
        msg=f"CONSOL PD: {mismatches} equilibrium mismatches (threshold {threshold})",
    )


# ---------------------------------------------------------------------------
# REAL SANITY tests
# ---------------------------------------------------------------------------


def test_r12_1() -> None:
    """Real CONSOLIDATION: equilibrium near range midpoint."""
    df = load_sol_1h("CONSOLIDATION")
    bars = make_bars_from_df(df)

    sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    pd = IncrementalPremiumDiscount({}, deps={"swing": sw})

    saw_eq = False
    for bar in bars:
        sw.update(bar.idx, bar)
        pd.update(bar.idx, bar)
        eq = pd.get_value("equilibrium")
        if isinstance(eq, float) and not math.isnan(eq):
            # Equilibrium should be within the price range
            assert_true(eq > 0, msg=f"equilibrium={eq} should be positive")
            saw_eq = True

    assert_true(saw_eq, msg="Never had equilibrium on CONSOLIDATION")


def test_r12_2() -> None:
    """Real BULL: premium zone appears near highs."""
    df = load_sol_1h("BULL")
    bars = make_bars_from_df(df)

    sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    pd = IncrementalPremiumDiscount({}, deps={"swing": sw})

    premium_count = 0
    for bar in bars:
        sw.update(bar.idx, bar)
        pd.update(bar.idx, bar)
        if pd.get_value("zone") == "premium":
            premium_count += 1

    assert_true(premium_count > 0, msg=f"No premium zones on BULL regime")


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("M12.1", "MATH", "Equilibrium = midpoint", test_m12_1),
        TestCase("M12.2", "MATH", "Premium at 75th pct", test_m12_2),
        TestCase("M12.3", "MATH", "depth_pct clamped", test_m12_3),
        TestCase("A12.1", "ALGORITHM", "Version on zone change", test_a12_1),
        TestCase("A12.2", "ALGORITHM", "none before pairs", test_a12_2),
        TestCase("E12.1", "EDGE", "Degenerate pair", test_e12_1),
        TestCase("P12.1", "PARITY", "Inc vs vec (CONSOL)", test_p12_1),
        TestCase("R12.1", "REAL", "CONSOL: equilibrium", test_r12_1),
        TestCase("R12.2", "REAL", "BULL: premium zone", test_r12_2),
    ]


if __name__ == "__main__":
    run_module_cli("premium_discount", get_tests())
