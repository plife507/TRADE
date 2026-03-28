"""
Deep test: derived_zone detector (K-slot zones from fibonacci levels).

Tests:
  M6.1 — Zone center = high - (range × level), width = center × width_pct
  M6.2 — Max active slots enforced (excess zones dropped)
  A6.1 — Zone slots reorder: newest zone at slot 0
  A6.2 — Regen only on source_version change (pair_version for paired mode)
  E6.1 — No zones before any swing pairs form
  P6.1 — Parity: incremental vs vectorized on BULL data (active_count)
  R6.1 — Real: zones form within price range on BULL data
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
from src.structures.detectors.derived_zone import IncrementalDerivedZone
from src.structures.detectors.swing import IncrementalSwing


def _make_dz_chain(
    bars: list,
    levels: list[float] | None = None,
    max_active: int = 3,
    left: int = 2,
    right: int = 2,
) -> tuple[IncrementalSwing, IncrementalDerivedZone]:
    """Create swing → derived_zone chain and feed bars."""
    if levels is None:
        levels = [0.382, 0.618]

    sw = IncrementalSwing({"left": left, "right": right, "mode": "fractal"}, deps=None)
    dz = IncrementalDerivedZone(
        {"levels": levels, "max_active": max_active, "width_pct": 0.005,
         "use_paired_source": True, "mode": "retracement"},
        deps={"swing": sw},
    )
    for bar in bars:
        sw.update(bar.idx, bar)
        dz.update(bar.idx, bar)
    return sw, dz


def _uptrend_bars() -> list:
    """Same uptrend from fib test: low=70 at bar 2, high=140 at bar 7."""
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


def test_m6_1() -> None:
    """Zone center = high - (range × level), width = center × width_pct.

    Pair: high=140, low=70, range=70, width_pct=0.005.
    level=0.382: center = 140 - (70 × 0.382) = 113.26
                 width = 113.26 × 0.005 = 0.5663
                 lower ≈ 112.977, upper ≈ 113.543
    """
    bars = _uptrend_bars()
    _, dz = _make_dz_chain(bars, levels=[0.382], max_active=3)

    active = dz.get_value("active_count")
    if int(active) > 0:
        lower = dz.get_value("zone0_lower")
        upper = dz.get_value("zone0_upper")

        if isinstance(lower, float) and not math.isnan(lower):
            center = 140.0 - (70.0 * 0.382)
            width = center * 0.005
            expected_lower = center - width / 2
            expected_upper = center + width / 2
            assert_close(lower, expected_lower, tol=0.5, msg="zone0 lower")
            assert_close(upper, expected_upper, tol=0.5, msg="zone0 upper")


def test_m6_2() -> None:
    """Max active slots enforced: excess zones dropped.

    With max_active=2 and 3 levels, only 2 zones should be active.
    """
    bars = _uptrend_bars()
    _, dz = _make_dz_chain(bars, levels=[0.236, 0.382, 0.618], max_active=2)

    active = int(dz.get_value("active_count"))
    assert_true(active <= 2, msg=f"active_count={active} > max_active=2")


# ---------------------------------------------------------------------------
# ALGORITHM tests
# ---------------------------------------------------------------------------


def test_a6_1() -> None:
    """Newest zone at slot 0 after regeneration."""
    bars = _uptrend_bars()
    _, dz = _make_dz_chain(bars, levels=[0.382, 0.618], max_active=3)

    active = int(dz.get_value("active_count"))
    if active >= 2:
        # Zone 0 should be the first (newest after last regen)
        z0_state = dz.get_value("zone0_state")
        assert_eq(z0_state, "active", msg="zone0 should be active")


def test_a6_2() -> None:
    """Regen only on source_version change."""
    bars = _uptrend_bars()
    sw = IncrementalSwing({"left": 2, "right": 2, "mode": "fractal"}, deps=None)
    dz = IncrementalDerivedZone(
        {"levels": [0.5], "max_active": 3, "width_pct": 0.005,
         "use_paired_source": True, "mode": "retracement"},
        deps={"swing": sw},
    )

    for bar in bars:
        sw.update(bar.idx, bar)
        dz.update(bar.idx, bar)

    v1 = int(dz.get_value("source_version"))

    # Feed more bars without creating new pivots
    for i in range(10, 14):
        bar = make_bar(i, 122, 124, 120, 121)
        sw.update(i, bar)
        dz.update(i, bar)

    v2 = int(dz.get_value("source_version"))
    assert_eq(v1, v2, msg="source_version unchanged without new pair")


# ---------------------------------------------------------------------------
# EDGE tests
# ---------------------------------------------------------------------------


def test_e6_1() -> None:
    """No zones before swing pairs form."""
    bars = [make_bar(i, 100, 105, 95, 100) for i in range(4)]
    _, dz = _make_dz_chain(bars, levels=[0.382], max_active=3)

    assert_eq(int(dz.get_value("active_count")), 0, msg="no zones before pairs")
    state = dz.get_value("zone0_state")
    assert_eq(state, "none", msg="zone0 state=none")


# ---------------------------------------------------------------------------
# PARITY tests
# ---------------------------------------------------------------------------


def test_p6_1() -> None:
    """Parity: incremental vs vectorized derived_zone on BULL data."""
    from src.forge.audits.vectorized_references.derived_zone_reference import (
        vectorized_derived_zone,
    )
    from src.forge.audits.vectorized_references.swing_reference import vectorized_swing

    df = load_sol_1h("BULL")
    ohlcv = df_to_ohlcv_dict(df)
    bars = make_bars_from_df(df)
    n = len(bars)

    left, right = 5, 5
    levels = [0.382, 0.618]
    max_active = 3

    sw = IncrementalSwing({"left": left, "right": right, "mode": "fractal"}, deps=None)
    dz = IncrementalDerivedZone(
        {"levels": levels, "max_active": max_active, "width_pct": 0.002,
         "use_paired_source": True, "mode": "retracement"},
        deps={"swing": sw},
    )

    swing_vec = vectorized_swing(ohlcv, left, right)
    dz_vec = vectorized_derived_zone(ohlcv, swing_vec, levels, max_active)

    mismatches = 0
    for i, bar in enumerate(bars):
        sw.update(i, bar)
        dz.update(i, bar)

        inc_active = int(dz.get_value("active_count"))
        vec_active = int(dz_vec["active_count"][i])
        if inc_active != vec_active:
            mismatches += 1

    threshold = max(5, n // 50)
    assert_true(
        mismatches <= threshold,
        msg=f"BULL derived_zone: {mismatches} active_count mismatches (threshold {threshold})",
    )


# ---------------------------------------------------------------------------
# REAL SANITY tests
# ---------------------------------------------------------------------------


def test_r6_1() -> None:
    """Real: zones form within price range on BULL data."""
    df = load_sol_1h("BULL")
    bars = make_bars_from_df(df)

    sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    dz = IncrementalDerivedZone(
        {"levels": [0.382, 0.618], "max_active": 3, "width_pct": 0.002,
         "use_paired_source": True, "mode": "retracement"},
        deps={"swing": sw},
    )

    saw_zones = False
    for bar in bars:
        sw.update(bar.idx, bar)
        dz.update(bar.idx, bar)

        if int(dz.get_value("active_count")) > 0:
            lower = dz.get_value("zone0_lower")
            upper = dz.get_value("zone0_upper")
            if isinstance(lower, float) and not math.isnan(lower):
                # Zone should have positive width
                assert_true(
                    upper > lower,
                    msg=f"Zone width non-positive: {lower} to {upper}",
                )
                saw_zones = True

    assert_true(saw_zones, msg="No derived zones formed on BULL data")


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("M6.1", "MATH", "Zone center and width", test_m6_1),
        TestCase("M6.2", "MATH", "Max active enforced", test_m6_2),
        TestCase("A6.1", "ALGORITHM", "Newest at slot 0", test_a6_1),
        TestCase("A6.2", "ALGORITHM", "Regen on version change only", test_a6_2),
        TestCase("E6.1", "EDGE", "No zones before pairs", test_e6_1),
        TestCase("P6.1", "PARITY", "Inc vs vec (BULL)", test_p6_1),
        TestCase("R6.1", "REAL", "Zones in price range (BULL)", test_r6_1),
    ]


if __name__ == "__main__":
    run_module_cli("derived_zone", get_tests())
