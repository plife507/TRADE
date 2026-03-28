"""
Runner for all structure detector deep tests.

Executes all test modules sequentially, collects results, and
outputs a JSON report.

Usage:
    python -m src.forge.audits.structure_deep_tests.run_all
    python -m src.forge.audits.structure_deep_tests.run_all --verbose
    python -m src.forge.audits.structure_deep_tests.run_all --json
"""

from __future__ import annotations

import json
import sys
import time
from typing import Any

from src.forge.audits.structure_deep_tests._harness import (
    TestCase,
    TestReport,
    assert_close,
    assert_true,
    compute_atr_array,
    df_to_ohlcv_dict,
    load_sol_1h,
    make_bars_from_df,
    run_test_module,
)

# Registry of test modules — add new modules here as they're created
TEST_MODULES: list[tuple[str, str]] = [
    ("rolling_window", "src.forge.audits.structure_deep_tests.test_01_rolling_window"),
    ("swing", "src.forge.audits.structure_deep_tests.test_02_swing"),
    # Phase 2:
    ("trend", "src.forge.audits.structure_deep_tests.test_03_trend"),
    ("zone", "src.forge.audits.structure_deep_tests.test_04_zone"),
    ("fibonacci", "src.forge.audits.structure_deep_tests.test_05_fibonacci"),
    ("derived_zone", "src.forge.audits.structure_deep_tests.test_06_derived_zone"),
    ("market_structure", "src.forge.audits.structure_deep_tests.test_07_market_structure"),
    # Phase 3:
    ("displacement", "src.forge.audits.structure_deep_tests.test_08_displacement"),
    ("fair_value_gap", "src.forge.audits.structure_deep_tests.test_09_fair_value_gap"),
    ("order_block", "src.forge.audits.structure_deep_tests.test_10_order_block"),
    ("liquidity_zones", "src.forge.audits.structure_deep_tests.test_11_liquidity_zones"),
    ("premium_discount", "src.forge.audits.structure_deep_tests.test_12_premium_discount"),
    ("breaker_block", "src.forge.audits.structure_deep_tests.test_13_breaker_block"),
    # Phase 5+6: Engine integration + live path parity
    ("engine_integration", "src.forge.audits.structure_deep_tests.test_14_engine_integration"),
    ("live_path_parity", "src.forge.audits.structure_deep_tests.test_15_live_path_parity"),
    # Phase 7: Production live engine parity
    ("live_engine_parity", "src.forge.audits.structure_deep_tests.test_16_live_engine_parity"),
]


def _import_tests(module_path: str) -> Any:
    """Dynamically import a test module and return its get_tests() function."""
    import importlib

    mod = importlib.import_module(module_path)
    return mod.get_tests()


def _get_cross_detector_tests() -> list[TestCase]:
    """Cross-detector consistency tests X1-X5."""
    import math

    from src.structures.base import BarData
    from src.structures.detectors.displacement import IncrementalDisplacement
    from src.structures.detectors.fibonacci import IncrementalFibonacci
    from src.structures.detectors.order_block import IncrementalOrderBlock
    from src.structures.detectors.premium_discount import IncrementalPremiumDiscount
    from src.structures.detectors.swing import IncrementalSwing
    from src.structures.detectors.trend import IncrementalTrend

    def test_x1() -> None:
        """X1: Swing→Trend: when direction=1, recent waves show HH+HL."""
        df = load_sol_1h("BULL")
        bars = make_bars_from_df(df)

        sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
        tr = IncrementalTrend({}, deps={"swing": sw})

        for bar in bars:
            sw.update(bar.idx, bar)
            tr.update(bar.idx, bar)

        direction = tr.get_value("direction")
        if direction == 1:
            hh = tr.get_value("last_hh")
            hl = tr.get_value("last_hl")
            assert_true(
                bool(hh) or bool(hl),
                msg="Uptrend but no HH or HL flags",
            )

    def test_x2() -> None:
        """X2: Swing→Fibonacci: anchor_high == pair_high_level exactly."""
        df = load_sol_1h("BULL")
        bars = make_bars_from_df(df)

        sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
        fib = IncrementalFibonacci(
            {"levels": [0.5], "mode": "retracement", "use_paired_anchor": True},
            deps={"swing": sw},
        )

        for bar in bars:
            sw.update(bar.idx, bar)
            fib.update(bar.idx, bar)

        fib_ah = fib.get_value("anchor_high")
        sw_ph = sw.get_value("pair_high_level")

        if (isinstance(fib_ah, float) and not math.isnan(fib_ah)
                and isinstance(sw_ph, float) and not math.isnan(sw_ph)):
            assert_close(fib_ah, sw_ph, tol=1e-6, msg="fib anchor_high == swing pair_high")

    def test_x3() -> None:
        """X3: Swing→Premium/Discount: equilibrium == (pair_high+pair_low)/2."""
        df = load_sol_1h("CONSOLIDATION")
        bars = make_bars_from_df(df)

        sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
        pd = IncrementalPremiumDiscount({}, deps={"swing": sw})

        for bar in bars:
            sw.update(bar.idx, bar)
            pd.update(bar.idx, bar)

        eq = pd.get_value("equilibrium")
        ph = sw.get_value("pair_high_level")
        pl = sw.get_value("pair_low_level")

        if (isinstance(eq, float) and not math.isnan(eq)
                and isinstance(ph, float) and not math.isnan(ph)
                and isinstance(pl, float) and not math.isnan(pl)):
            expected = (ph + pl) / 2
            assert_close(eq, expected, tol=0.1, msg="equilibrium = (H+L)/2")

    def test_x4() -> None:
        """X4: Displacement→Order Block: every OB bar has displacement."""
        df = load_sol_1h("BEAR_BULL")
        ohlcv = df_to_ohlcv_dict(df)
        atr_arr = compute_atr_array(ohlcv["high"], ohlcv["low"], ohlcv["close"], 14)

        bars_list: list[BarData] = []
        for i in range(len(df)):
            indicators: dict[str, float] = {}
            if not math.isnan(atr_arr[i]):
                indicators["atr"] = float(atr_arr[i])
            bars_list.append(BarData(
                idx=i, open=float(df["open"].iloc[i]), high=float(df["high"].iloc[i]),
                low=float(df["low"].iloc[i]), close=float(df["close"].iloc[i]),
                volume=float(df["volume"].iloc[i]), indicators=indicators,
            ))

        sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
        disp = IncrementalDisplacement(
            {"atr_key": "atr", "body_atr_min": 1.5, "wick_ratio_max": 0.4}, deps=None)
        ob = IncrementalOrderBlock(
            {"atr_key": "atr", "use_body": True, "require_displacement": True,
             "body_atr_min": 1.5, "wick_ratio_max": 0.4, "max_active": 5,
             "lookback": 3},
            deps={"swing": sw},
        )

        violations = 0
        for bar in bars_list:
            sw.update(bar.idx, bar)
            disp.update(bar.idx, bar)
            ob.update(bar.idx, bar)

            if ob.get_value("new_this_bar"):
                if not disp.get_value("is_displacement"):
                    violations += 1

        assert_true(
            violations == 0,
            msg=f"OB without displacement on {violations} bars",
        )

    def test_x5() -> None:
        """X5: Breaker blocks form only when OB invalidated + CHoCH occurs.

        On BULL_BEAR data, check that breaker new_this_bar implies
        both OB any_invalidated and MS choch_this_bar.
        """
        from src.structures.detectors.breaker_block import IncrementalBreakerBlock
        from src.structures.detectors.market_structure import IncrementalMarketStructure

        df = load_sol_1h("BULL_BEAR")
        ohlcv = df_to_ohlcv_dict(df)
        atr_arr = compute_atr_array(ohlcv["high"], ohlcv["low"], ohlcv["close"], 14)

        bars_list: list[BarData] = []
        for i in range(len(df)):
            indicators: dict[str, float] = {}
            if not math.isnan(atr_arr[i]):
                indicators["atr"] = float(atr_arr[i])
            bars_list.append(BarData(
                idx=i, open=float(df["open"].iloc[i]), high=float(df["high"].iloc[i]),
                low=float(df["low"].iloc[i]), close=float(df["close"].iloc[i]),
                volume=float(df["volume"].iloc[i]), indicators=indicators,
            ))

        sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
        ob = IncrementalOrderBlock(
            {"atr_key": "atr", "use_body": True, "require_displacement": True,
             "body_atr_min": 1.5, "wick_ratio_max": 0.4, "max_active": 5,
             "lookback": 3},
            deps={"swing": sw},
        )
        ms = IncrementalMarketStructure({"confirmation_close": True}, deps={"swing": sw})
        bb = IncrementalBreakerBlock({"max_active": 5}, deps={"order_block": ob, "market_structure": ms})

        violations = 0
        for bar in bars_list:
            sw.update(bar.idx, bar)
            ob.update(bar.idx, bar)
            ms.update(bar.idx, bar)
            bb.update(bar.idx, bar)

            if bb.get_value("new_this_bar"):
                ob_inv = ob.get_value("any_invalidated_this_bar")
                ms_choch = ms.get_value("choch_this_bar")
                if not (ob_inv and ms_choch):
                    violations += 1

        assert_true(
            violations == 0,
            msg=f"Breaker without OB+CHoCH on {violations} bars",
        )

    return [
        TestCase("X1", "CROSS", "Swing→Trend: uptrend has HH/HL", test_x1),
        TestCase("X2", "CROSS", "Swing→Fib: anchor_high == pair_high", test_x2),
        TestCase("X3", "CROSS", "Swing→PD: equilibrium = midpoint", test_x3),
        TestCase("X4", "CROSS", "Displacement→OB: every OB has displacement", test_x4),
        TestCase("X5", "CROSS", "OB+MS→Breaker: concurrent triggers", test_x5),
    ]


def main() -> None:
    verbose = "--verbose" in sys.argv or "-v" in sys.argv
    json_output = "--json" in sys.argv

    t0 = time.perf_counter()
    reports: list[TestReport] = []

    for name, module_path in TEST_MODULES:
        if verbose:
            print(f"\n{'='*60}")
            print(f" {name}")
            print(f"{'='*60}")

        tests = _import_tests(module_path)
        report = run_test_module(name, tests, verbose=verbose)
        reports.append(report)

        if not json_output:
            print(report.summary_line())

    # Phase 4: Cross-detector consistency tests
    if verbose:
        print(f"\n{'='*60}")
        print(f" cross_detector")
        print(f"{'='*60}")

    cross_tests = _get_cross_detector_tests()
    cross_report = run_test_module("cross_detector", cross_tests, verbose=verbose)
    reports.append(cross_report)

    if not json_output:
        print(cross_report.summary_line())

    total_duration = (time.perf_counter() - t0) * 1000
    total_passed = sum(r.passed for r in reports)
    total_failed = sum(r.failed for r in reports)
    total_tests = sum(r.total for r in reports)

    if json_output:
        result = {
            "status": "PASS" if total_failed == 0 else "FAIL",
            "total_passed": total_passed,
            "total_failed": total_failed,
            "total_tests": total_tests,
            "duration_ms": round(total_duration, 1),
            "modules": [r.to_dict() for r in reports],
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*60}")
        status = "PASS" if total_failed == 0 else "FAIL"
        print(
            f"[{status}] Total: {total_passed}/{total_tests} passed "
            f"({total_duration:.0f}ms)"
        )
        if total_failed > 0:
            print(f"\nFailed modules:")
            for r in reports:
                if r.failed > 0:
                    print(f"  {r.detector_name}: {r.failed} failures")

    sys.exit(0 if total_failed == 0 else 1)


if __name__ == "__main__":
    main()
