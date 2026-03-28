"""
Deep test: Live engine parity — production on_candle_close() path.

Feeds the exact same candle sequence through TWO paths:
  1. BACKTEST: FeedStore → BarData → direct detector.update()
  2. LIVE:     LiveDataProvider.on_candle_close() → cache.update() →
               _update_structure_state_for_tf() → TFIncrementalState.update()

Compares structure outputs bar-by-bar. This tests the ACTUAL production
code path that runs in live trading — not a simulation of it.

Layers exercised:
  - LiveIndicatorCache.update() (O(1) incremental per bar)
  - _update_tf_buffer() (buffer append, trim, global_bar_count)
  - _update_structure_state_for_tf() (indicator snapshot under lock)
  - TFIncrementalState.update() (dependency-ordered detector chain)
  - Buffer trim survival (500-bar window over 24K+ bars)

Tests:
  PROD.1 — Swing outputs: 0 version mismatches across all bars
  PROD.2 — Trend direction: 0 mismatches across all bars
  PROD.3 — Market structure bias: 0 mismatches across all bars
  PROD.4 — RSI indicator: incremental matches batch to <0.01 tolerance
  PROD.5 — Buffer trim survival: structures correct after buffer wraps
  PROD.6 — Global bar index monotonic and correct
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


def _setup_both_paths(max_bars: int | None = None):
    """
    Create backtest + live paths from same synthetic data.

    Returns (bt_detectors, live_dp, candles, feed_store, warmup_n, test_end)
    """
    from datetime import datetime, timedelta

    from src.backtest.engine_factory import create_engine_from_play
    from src.backtest.play.play import load_play
    from src.engine.adapters.backtest import BacktestDataProvider
    from src.engine.adapters.live import LiveDataProvider
    from src.engine.interfaces import Candle
    from src.structures.base import BarData
    from src.structures.detectors.market_structure import IncrementalMarketStructure
    from src.structures.detectors.swing import IncrementalSwing
    from src.structures.detectors.trend import IncrementalTrend

    play = load_play("STR_011_full_chain")
    bt_engine = create_engine_from_play(play, use_synthetic=True)
    dp = bt_engine._data_provider
    assert isinstance(dp, BacktestDataProvider)
    fs = dp._feed_store
    assert fs is not None
    n = len(fs.close)
    test_end = min(n, max_bars) if max_bars else n

    base_time = datetime(2025, 1, 1)
    candles = [
        Candle(
            ts_open=base_time + timedelta(minutes=15 * i),
            ts_close=base_time + timedelta(minutes=15 * (i + 1)),
            open=float(fs.open[i]),
            high=float(fs.high[i]),
            low=float(fs.low[i]),
            close=float(fs.close[i]),
            volume=float(fs.volume[i]),
        )
        for i in range(test_end)
    ]

    # Backtest path: direct detectors
    bt_sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    bt_tr = IncrementalTrend({}, deps={"swing": bt_sw})
    bt_ms = IncrementalMarketStructure({"confirmation_close": True}, deps={"swing": bt_sw})

    # Live path: LiveDataProvider
    live_dp = LiveDataProvider(play, demo=True)
    warmup_n = live_dp._warmup_bars
    live_dp._low_tf_indicators.initialize_from_history(
        candles[:warmup_n],
        live_dp._get_indicator_specs_for_tf("low_tf"),
    )
    live_dp._init_structure_states()

    # Warm up structures on both paths
    for i in range(warmup_n):
        indicators: dict[str, float] = {}
        for name, arr in fs.indicators.items():
            if i < len(arr) and not np.isnan(arr[i]):
                indicators[name] = float(arr[i])
        bar = BarData(
            idx=i,
            open=float(fs.open[i]),
            high=float(fs.high[i]),
            low=float(fs.low[i]),
            close=float(fs.close[i]),
            volume=float(fs.volume[i]),
            indicators=indicators,
        )
        bt_sw.update(i, bar)
        bt_tr.update(i, bar)
        bt_ms.update(i, bar)
        live_dp._update_structure_state_for_tf(
            live_dp._low_tf_structure, i, candles[i], "low_tf"
        )

    live_dp._global_bar_count["low_tf"] = warmup_n
    live_dp._low_tf_buffer = list(candles[:warmup_n])

    return (bt_sw, bt_tr, bt_ms), live_dp, candles, fs, warmup_n, test_end


def _feed_bar(bt_detectors, live_dp, candle, fs, bar_idx):
    """Feed one bar through both paths."""
    from src.structures.base import BarData

    bt_sw, bt_tr, bt_ms = bt_detectors

    indicators: dict[str, float] = {}
    for name, arr in fs.indicators.items():
        if bar_idx < len(arr) and not np.isnan(arr[bar_idx]):
            indicators[name] = float(arr[bar_idx])

    bar = BarData(
        idx=bar_idx,
        open=float(fs.open[bar_idx]),
        high=float(fs.high[bar_idx]),
        low=float(fs.low[bar_idx]),
        close=float(fs.close[bar_idx]),
        volume=float(fs.volume[bar_idx]),
        indicators=indicators,
    )
    bt_sw.update(bar_idx, bar)
    bt_tr.update(bar_idx, bar)
    bt_ms.update(bar_idx, bar)

    live_dp.on_candle_close(candle, timeframe="15m")


# ---------------------------------------------------------------------------
# PRODUCTION PARITY tests
# ---------------------------------------------------------------------------


def test_prod_1() -> None:
    """Swing outputs: 0 version mismatches across all bars."""
    (bt_sw, _, _), live_dp, candles, fs, warmup_n, test_end = _setup_both_paths()

    from src.structures.detectors.trend import IncrementalTrend
    from src.structures.detectors.market_structure import IncrementalMarketStructure
    bt_tr = IncrementalTrend({}, deps={"swing": bt_sw})
    bt_ms = IncrementalMarketStructure({"confirmation_close": True}, deps={"swing": bt_sw})

    mismatches = 0
    for i in range(warmup_n, test_end):
        _feed_bar((bt_sw, bt_tr, bt_ms), live_dp, candles[i], fs, i)

        bt_ver = bt_sw.get_value("version")
        live_ver = live_dp._low_tf_structure.get_value("swing", "version")
        if bt_ver != live_ver:
            mismatches += 1

        bt_high = bt_sw.get_value("high_level")
        live_high = live_dp._low_tf_structure.get_value("swing", "high_level")
        if isinstance(bt_high, float) and isinstance(live_high, float):
            if not (math.isnan(bt_high) and math.isnan(live_high)):
                if abs(bt_high - live_high) > 0.001:
                    mismatches += 1

    bars = test_end - warmup_n
    assert_eq(mismatches, 0, msg=f"Swing mismatches: {mismatches} in {bars} bars")


def test_prod_2() -> None:
    """Trend direction: 0 mismatches across all bars."""
    (bt_sw, bt_tr, bt_ms), live_dp, candles, fs, warmup_n, test_end = _setup_both_paths()

    mismatches = 0
    for i in range(warmup_n, test_end):
        _feed_bar((bt_sw, bt_tr, bt_ms), live_dp, candles[i], fs, i)

        bt_dir = int(bt_tr.get_value("direction"))
        live_dir = int(live_dp._low_tf_structure.get_value("trend", "direction"))
        if bt_dir != live_dir:
            mismatches += 1

    bars = test_end - warmup_n
    assert_eq(mismatches, 0, msg=f"Trend mismatches: {mismatches} in {bars} bars")


def test_prod_3() -> None:
    """Market structure bias: 0 mismatches across all bars."""
    (bt_sw, bt_tr, bt_ms), live_dp, candles, fs, warmup_n, test_end = _setup_both_paths()

    mismatches = 0
    for i in range(warmup_n, test_end):
        _feed_bar((bt_sw, bt_tr, bt_ms), live_dp, candles[i], fs, i)

        bt_bias = int(bt_ms.get_value("bias"))
        live_bias = int(live_dp._low_tf_structure.get_value("ms", "bias"))
        if bt_bias != live_bias:
            mismatches += 1

    bars = test_end - warmup_n
    assert_eq(mismatches, 0, msg=f"MS bias mismatches: {mismatches} in {bars} bars")


def test_prod_4() -> None:
    """RSI indicator: incremental per-bar matches batch to <0.01."""
    (bt_sw, bt_tr, bt_ms), live_dp, candles, fs, warmup_n, test_end = _setup_both_paths()

    max_diff = 0.0
    mismatches = 0

    for i in range(warmup_n, test_end):
        _feed_bar((bt_sw, bt_tr, bt_ms), live_dp, candles[i], fs, i)

        bt_rsi = float(fs.indicators["rsi_14"][i])
        cache = live_dp._low_tf_indicators
        live_rsi = float(cache._indicators["rsi_14"][cache._bar_count - 1])

        if not math.isnan(bt_rsi) and not math.isnan(live_rsi):
            diff = abs(bt_rsi - live_rsi)
            max_diff = max(max_diff, diff)
            if diff > 0.01:
                mismatches += 1

    bars = test_end - warmup_n
    assert_eq(
        mismatches, 0,
        msg=f"RSI mismatches (>0.01): {mismatches} in {bars} bars, max_diff={max_diff:.8f}",
    )


def test_prod_5() -> None:
    """Buffer trim survival: structures correct after buffer wraps past buffer_size.

    With buffer_size=500 and 24K+ bars, the buffer trims ~48 times.
    Structure outputs must remain correct throughout.
    """
    (bt_sw, bt_tr, bt_ms), live_dp, candles, fs, warmup_n, test_end = _setup_both_paths()

    for i in range(warmup_n, test_end):
        _feed_bar((bt_sw, bt_tr, bt_ms), live_dp, candles[i], fs, i)

    # After all bars: final structure state must match
    bars = test_end - warmup_n
    bt_final_ver = bt_sw.get_value("version")
    live_final_ver = live_dp._low_tf_structure.get_value("swing", "version")
    assert_eq(
        bt_final_ver, live_final_ver,
        msg=f"Final swing version: BT={bt_final_ver}, Live={live_final_ver} after {bars} bars",
    )

    bt_final_dir = int(bt_tr.get_value("direction"))
    live_final_dir = int(live_dp._low_tf_structure.get_value("trend", "direction"))
    assert_eq(bt_final_dir, live_final_dir, msg="Final trend direction")

    # Buffer should have been trimmed (bar count >> buffer_size)
    global_count = live_dp._global_bar_count["low_tf"]
    buf_len = len(live_dp._low_tf_buffer)
    assert_true(
        global_count > live_dp._buffer_size,
        msg=f"Expected buffer trims: global={global_count}, buf_size={live_dp._buffer_size}",
    )
    assert_true(
        buf_len <= live_dp._buffer_size,
        msg=f"Buffer exceeds max: {buf_len} > {live_dp._buffer_size}",
    )


def test_prod_6() -> None:
    """Global bar index is monotonic and equals warmup + bars fed."""
    (bt_sw, bt_tr, bt_ms), live_dp, candles, fs, warmup_n, test_end = _setup_both_paths()

    for i in range(warmup_n, test_end):
        _feed_bar((bt_sw, bt_tr, bt_ms), live_dp, candles[i], fs, i)

    expected = test_end  # warmup_n + (test_end - warmup_n)
    actual = live_dp._global_bar_count["low_tf"]
    assert_eq(actual, expected, msg=f"Global bar count: expected {expected}, got {actual}")


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("PROD.1", "PROD", "Swing: 0 mismatches (full run)", test_prod_1),
        TestCase("PROD.2", "PROD", "Trend: 0 mismatches (full run)", test_prod_2),
        TestCase("PROD.3", "PROD", "MS bias: 0 mismatches (full run)", test_prod_3),
        TestCase("PROD.4", "PROD", "RSI: incremental == batch", test_prod_4),
        TestCase("PROD.5", "PROD", "Buffer trim survival", test_prod_5),
        TestCase("PROD.6", "PROD", "Global bar index correct", test_prod_6),
    ]


if __name__ == "__main__":
    run_module_cli("live_engine_parity", get_tests())
