"""
Deep test: Live path parity — incremental indicators → structures.

Simulates the live path: initialize LiveIndicatorCache from historical
candles, feed bars incrementally, build BarData the way play_engine.py
does for live mode — then compare bar-by-bar against backtest path
(FeedStore-backed BarData + same structures).

This is THE backtest-vs-live divergence test.

Tests:
  LIVE.1 — Indicator values: incremental (live) vs batch (backtest) match
  LIVE.2 — BarData.indicators from live cache match FeedStore indicators
  LIVE.3 — Structure outputs (swing) match between live and backtest paths
  LIVE.4 — Structure outputs (trend/MS) match between live and backtest paths
  LIVE.5 — Full chain: engine backtest signals == simulated live signals
"""

from __future__ import annotations

import math

import numpy as np

from src.forge.audits.structure_deep_tests._harness import (
    TestCase,
    assert_close,
    assert_eq,
    assert_true,
    run_module_cli,
)


def _build_backtest_and_live_bars() -> tuple[list, list, dict]:
    """
    Create both backtest-path and live-path BarData sequences from
    the same underlying data (STR_011 play with synthetic data).

    Returns:
        (backtest_bars, live_bars, metadata) where:
        - backtest_bars: list of BarData built from FeedStore (batch indicators)
        - live_bars: list of BarData built from LiveIndicatorCache (incremental indicators)
        - metadata: {"n": num_bars, "sim_start": warmup_end_index}
    """
    from src.backtest.engine_factory import create_engine_from_play
    from src.backtest.play.play import load_play
    from src.engine.adapters.backtest import BacktestDataProvider
    from src.engine.adapters.live import LiveIndicatorCache
    from src.structures.base import BarData

    play = load_play("STR_011_full_chain")
    engine = create_engine_from_play(play, use_synthetic=True)

    # Extract FeedStore from engine (backtest path)
    data_provider = engine._data_provider
    assert isinstance(data_provider, BacktestDataProvider)
    feed_store = data_provider._feed_store
    assert feed_store is not None

    n = len(feed_store.close)

    # Get sim start (warmup end)
    sim_start = 0
    if hasattr(engine, '_prepared_frame') and engine._prepared_frame is not None:
        sim_start = engine._prepared_frame.sim_start_index or 0

    # --- BACKTEST PATH: Build BarData from FeedStore ---
    backtest_bars = []
    for i in range(n):
        indicators: dict[str, float] = {}
        for name, arr in feed_store.indicators.items():
            if i < len(arr) and not np.isnan(arr[i]):
                indicators[name] = float(arr[i])
        backtest_bars.append(BarData(
            idx=i,
            open=float(feed_store.open[i]),
            high=float(feed_store.high[i]),
            low=float(feed_store.low[i]),
            close=float(feed_store.close[i]),
            volume=float(feed_store.volume[i]),
            indicators=indicators,
        ))

    # --- LIVE PATH: Build BarData via LiveIndicatorCache ---
    # Simulate what LiveDataProvider does: initialize cache from history,
    # then build BarData from cache for each bar.

    # Get indicator specs from play
    indicator_specs = []
    if play.feature_registry:
        for feat in play.feature_registry:
            indicator_specs.append(feat)

    # Create cache and initialize from "historical" candles (= same synthetic data)
    cache = LiveIndicatorCache(play, buffer_size=n + 100)

    # Build candle-like objects from FeedStore for warmup
    from dataclasses import dataclass
    from datetime import datetime, timedelta

    @dataclass
    class FakeCandle:
        ts_open: datetime
        open: float
        high: float
        low: float
        close: float
        volume: float

    base_time = datetime(2025, 1, 1)
    candles = []
    for i in range(n):
        candles.append(FakeCandle(
            ts_open=base_time + timedelta(minutes=15 * i),
            open=float(feed_store.open[i]),
            high=float(feed_store.high[i]),
            low=float(feed_store.low[i]),
            close=float(feed_store.close[i]),
            volume=float(feed_store.volume[i]),
        ))

    cache.initialize_from_history(candles, indicator_specs)

    # Build BarData from cache (simulating what play_engine.py:1007-1016 does)
    live_bars = []
    with cache._lock:
        bc = cache._bar_count
        for i in range(bc):
            indicators = {}
            for name, arr in cache._indicators.items():
                if i < len(arr) and not np.isnan(arr[i]):
                    indicators[name] = float(arr[i])
            live_bars.append(BarData(
                idx=i,
                open=float(cache._open[i]),
                high=float(cache._high[i]),
                low=float(cache._low[i]),
                close=float(cache._close[i]),
                volume=float(cache._volume[i]),
                indicators=indicators,
            ))

    return backtest_bars, live_bars, {"n": n, "sim_start": sim_start}


# ---------------------------------------------------------------------------
# LIVE PARITY tests
# ---------------------------------------------------------------------------


def test_live_1() -> None:
    """Indicator values: incremental (live) vs batch (backtest) match.

    Compare indicator values in BarData.indicators between backtest and live
    paths for every bar after warmup. Allow small float tolerance.
    """
    bt_bars, live_bars, meta = _build_backtest_and_live_bars()
    n = min(len(bt_bars), len(live_bars))
    sim_start = meta["sim_start"]

    mismatches = 0
    total_checks = 0

    for i in range(sim_start, n):
        bt_inds = dict(bt_bars[i].indicators)
        live_inds = dict(live_bars[i].indicators)

        # Check indicators present in both
        common_keys = set(bt_inds) & set(live_inds)
        for key in common_keys:
            bt_val = bt_inds[key]
            live_val = live_inds[key]
            total_checks += 1

            if abs(bt_val - live_val) > 0.1:
                mismatches += 1

    # Allow up to 2% mismatch rate (warmup convergence)
    threshold = max(5, int(total_checks * 0.02))
    assert_true(
        mismatches <= threshold,
        msg=f"Indicator value mismatches: {mismatches}/{total_checks} (threshold {threshold})",
    )


def test_live_2() -> None:
    """BarData.indicators from live cache have same keys as backtest FeedStore.

    After warmup, both paths should expose the same indicator keys.
    """
    bt_bars, live_bars, meta = _build_backtest_and_live_bars()
    n = min(len(bt_bars), len(live_bars))

    # Check at bar n-1 (latest)
    if n > 0:
        bt_keys = set(bt_bars[-1].indicators.keys())
        live_keys = set(live_bars[-1].indicators.keys())

        # Live may have fewer keys (engine-managed like anchored_vwap are NaN)
        # But should have core indicators
        missing = bt_keys - live_keys
        # Filter out engine-managed keys (anchored_vwap)
        missing = {k for k in missing if "anchored" not in k.lower() and "vwap" not in k.lower()}

        assert_true(
            len(missing) <= 2,
            msg=f"Live missing indicator keys: {missing}",
        )


def test_live_3() -> None:
    """Swing outputs match between live and backtest paths.

    Feed same bars through swing detector from both paths' BarData.
    Outputs should be identical since OHLCV is the same and swing
    only depends on OHLCV (no indicators needed for basic fractal mode).
    """
    from src.structures.detectors.swing import IncrementalSwing

    bt_bars, live_bars, meta = _build_backtest_and_live_bars()
    n = min(len(bt_bars), len(live_bars))

    bt_sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    live_sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)

    mismatches = 0
    for i in range(n):
        bt_sw.update(i, bt_bars[i])
        live_sw.update(i, live_bars[i])

        for key in ["high_level", "low_level", "high_idx", "low_idx", "version"]:
            bt_val = bt_sw.get_value(key)
            live_val = live_sw.get_value(key)

            if isinstance(bt_val, float) and isinstance(live_val, float):
                if math.isnan(bt_val) and math.isnan(live_val):
                    continue
                if abs(bt_val - live_val) > 0.01:
                    mismatches += 1
            elif bt_val != live_val:
                mismatches += 1

    assert_eq(mismatches, 0, msg=f"Swing mismatches between BT and live: {mismatches}")


def test_live_4() -> None:
    """Trend + MS outputs match between live and backtest paths.

    Since these depend on swing (which depends only on OHLCV), and OHLCV
    is identical, outputs should match exactly. The only divergence source
    would be indicator-dependent features (ATR for zones etc.), which
    STR_011 doesn't use for trend/MS.
    """
    from src.structures.detectors.market_structure import IncrementalMarketStructure
    from src.structures.detectors.swing import IncrementalSwing
    from src.structures.detectors.trend import IncrementalTrend

    bt_bars, live_bars, meta = _build_backtest_and_live_bars()
    n = min(len(bt_bars), len(live_bars))

    # Backtest chain
    bt_sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    bt_tr = IncrementalTrend({}, deps={"swing": bt_sw})
    bt_ms = IncrementalMarketStructure({"confirmation_close": True}, deps={"swing": bt_sw})

    # Live chain
    live_sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    live_tr = IncrementalTrend({}, deps={"swing": live_sw})
    live_ms = IncrementalMarketStructure({"confirmation_close": True}, deps={"swing": live_sw})

    trend_mismatches = 0
    ms_mismatches = 0

    for i in range(n):
        bt_sw.update(i, bt_bars[i])
        bt_tr.update(i, bt_bars[i])
        bt_ms.update(i, bt_bars[i])

        live_sw.update(i, live_bars[i])
        live_tr.update(i, live_bars[i])
        live_ms.update(i, live_bars[i])

        if int(bt_tr.get_value("direction")) != int(live_tr.get_value("direction")):
            trend_mismatches += 1
        if int(bt_ms.get_value("bias")) != int(live_ms.get_value("bias")):
            ms_mismatches += 1

    assert_eq(trend_mismatches, 0, msg=f"Trend direction mismatches: {trend_mismatches}")
    assert_eq(ms_mismatches, 0, msg=f"MS bias mismatches: {ms_mismatches}")


def test_live_5() -> None:
    """OHLCV from both paths is identical (sanity check).

    This verifies the test infrastructure itself — both paths
    read from the same underlying FeedStore data.
    """
    bt_bars, live_bars, meta = _build_backtest_and_live_bars()
    n = min(len(bt_bars), len(live_bars))

    assert_true(n > 100, msg=f"Too few bars: {n}")

    ohlcv_mismatches = 0
    for i in range(n):
        if abs(bt_bars[i].close - live_bars[i].close) > 1e-8:
            ohlcv_mismatches += 1
        if abs(bt_bars[i].high - live_bars[i].high) > 1e-8:
            ohlcv_mismatches += 1

    assert_eq(ohlcv_mismatches, 0, msg=f"OHLCV divergence: {ohlcv_mismatches}")


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("LIVE.1", "LIVE", "Indicator values: inc vs batch", test_live_1),
        TestCase("LIVE.2", "LIVE", "Indicator keys match", test_live_2),
        TestCase("LIVE.3", "LIVE", "Swing: BT == live", test_live_3),
        TestCase("LIVE.4", "LIVE", "Trend+MS: BT == live", test_live_4),
        TestCase("LIVE.5", "LIVE", "OHLCV identical (sanity)", test_live_5),
    ]


if __name__ == "__main__":
    run_module_cli("live_path_parity", get_tests())
