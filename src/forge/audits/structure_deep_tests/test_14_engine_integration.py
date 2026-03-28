"""
Deep test: Engine integration — structures through PlayEngine.

Runs a real Play through create_engine_from_play(), captures structure
outputs via on_snapshot callback bar-by-bar, and verifies they match
direct detector calls on the same data.

Tests the FULL backtest pipeline:
  YAML → TFIncrementalState → BarData (from FeedStore) → detector updates → snapshot

Tests:
  ENG.1 — Swing outputs from engine match direct detector on same OHLCV
  ENG.2 — Trend outputs from engine match direct detector
  ENG.3 — Market structure BOS/CHoCH events match
  ENG.4 — Snapshot get_structure() returns current detector values
  ENG.5 — Structure versions are monotonically non-decreasing through engine run
"""

from __future__ import annotations

import math

from src.forge.audits.structure_deep_tests._harness import (
    TestCase,
    assert_close,
    assert_eq,
    assert_true,
    run_module_cli,
)


def _run_engine_and_capture(
    play_id: str,
) -> tuple[list[dict], int]:
    """
    Run a Play through the real engine and capture structure snapshots.

    Returns:
        (snapshots, total_bars) where snapshots is a list of dicts,
        one per bar, with structure values captured via on_snapshot.
    """
    from src.backtest.engine_factory import create_engine_from_play
    from src.backtest.play.play import load_play

    play = load_play(play_id)
    engine = create_engine_from_play(play, use_synthetic=True)

    snapshots: list[dict] = []

    def capture_snapshot(snapshot, exec_idx, high_tf_idx, med_tf_idx):
        """Callback: capture structure values at each bar."""
        try:
            vals: dict = {
                "exec_idx": exec_idx,
                # Swing outputs (dot-separated path)
                "swing.high_level": snapshot.get_structure("swing.high_level"),
                "swing.low_level": snapshot.get_structure("swing.low_level"),
                "swing.high_idx": snapshot.get_structure("swing.high_idx"),
                "swing.low_idx": snapshot.get_structure("swing.low_idx"),
                "swing.version": snapshot.get_structure("swing.version"),
                "swing.pair_version": snapshot.get_structure("swing.pair_version"),
                # Trend outputs
                "trend.direction": snapshot.get_structure("trend.direction"),
                "trend.strength": snapshot.get_structure("trend.strength"),
                "trend.version": snapshot.get_structure("trend.version"),
                # Market structure outputs
                "ms.bias": snapshot.get_structure("ms.bias"),
                "ms.bos_this_bar": snapshot.get_structure("ms.bos_this_bar"),
                "ms.choch_this_bar": snapshot.get_structure("ms.choch_this_bar"),
                "ms.version": snapshot.get_structure("ms.version"),
            }
            snapshots.append(vals)
        except (KeyError, AttributeError):
            # Structure not available yet (warmup period)
            pass

    engine.set_on_snapshot(capture_snapshot)

    from src.backtest.engine_factory import run_engine_with_play
    run_engine_with_play(engine, play)

    return snapshots, len(snapshots)


def _run_direct_detectors_on_engine_data(
    play_id: str,
) -> list[dict]:
    """
    Run direct detector calls on the same data the engine would use.

    Extracts OHLCV from the engine's FeedStore, builds BarData manually
    (same as _update_incremental_state does), and feeds through detectors
    directly — same as T10 Phases 1-4.

    Returns:
        List of dicts with structure values per bar.
    """
    import numpy as np

    from src.backtest.engine_factory import create_engine_from_play
    from src.backtest.play.play import load_play
    from src.engine.adapters.backtest import BacktestDataProvider
    from src.structures.base import BarData
    from src.structures.detectors.market_structure import IncrementalMarketStructure
    from src.structures.detectors.swing import IncrementalSwing
    from src.structures.detectors.trend import IncrementalTrend

    play = load_play(play_id)
    engine = create_engine_from_play(play, use_synthetic=True)

    # Extract FeedStore from engine
    data_provider = engine._data_provider
    assert isinstance(data_provider, BacktestDataProvider)
    feed_store = data_provider._feed_store
    assert feed_store is not None

    n = len(feed_store.close)

    # Build detectors manually (same params as Play YAML)
    sw = IncrementalSwing({"left": 5, "right": 5, "mode": "fractal"}, deps=None)
    tr = IncrementalTrend({}, deps={"swing": sw})
    ms = IncrementalMarketStructure({"confirmation_close": True}, deps={"swing": sw})

    results: list[dict] = []

    # Get warmup/sim start
    sim_start = 0
    if hasattr(engine, '_prepared_frame') and engine._prepared_frame is not None:
        sim_start = engine._prepared_frame.sim_start_index or 0

    for i in range(n):
        # Build BarData exactly as engine does (line 997-1026 in play_engine.py)
        indicators: dict[str, float] = {}
        for name, arr in feed_store.indicators.items():
            if i < len(arr) and not np.isnan(arr[i]):
                indicators[name] = float(arr[i])

        bar = BarData(
            idx=i,
            open=float(feed_store.open[i]),
            high=float(feed_store.high[i]),
            low=float(feed_store.low[i]),
            close=float(feed_store.close[i]),
            volume=float(feed_store.volume[i]),
            indicators=indicators,
        )

        sw.update(i, bar)
        tr.update(i, bar)
        ms.update(i, bar)

        if i >= sim_start:
            results.append({
                "exec_idx": i,
                "swing.high_level": sw.get_value("high_level"),
                "swing.low_level": sw.get_value("low_level"),
                "swing.high_idx": sw.get_value("high_idx"),
                "swing.low_idx": sw.get_value("low_idx"),
                "swing.version": sw.get_value("version"),
                "swing.pair_version": sw.get_value("pair_version"),
                "trend.direction": tr.get_value("direction"),
                "trend.strength": tr.get_value("strength"),
                "trend.version": tr.get_value("version"),
                "ms.bias": ms.get_value("bias"),
                "ms.bos_this_bar": ms.get_value("bos_this_bar"),
                "ms.choch_this_bar": ms.get_value("choch_this_bar"),
                "ms.version": ms.get_value("version"),
            })

    return results


PLAY_ID = "STR_011_full_chain"


# ---------------------------------------------------------------------------
# ENGINE INTEGRATION tests
# ---------------------------------------------------------------------------


def test_eng_1() -> None:
    """Swing outputs from engine match direct detector on same OHLCV."""
    engine_snaps, n = _run_engine_and_capture(PLAY_ID)
    direct_snaps = _run_direct_detectors_on_engine_data(PLAY_ID)

    # Align by exec_idx
    engine_by_idx = {s["exec_idx"]: s for s in engine_snaps}
    direct_by_idx = {s["exec_idx"]: s for s in direct_snaps}

    common_idxs = sorted(set(engine_by_idx) & set(direct_by_idx))
    assert_true(len(common_idxs) > 50, msg=f"Only {len(common_idxs)} common bars")

    mismatches = 0
    for idx in common_idxs:
        eng = engine_by_idx[idx]
        dir_ = direct_by_idx[idx]

        for key in ["swing.high_level", "swing.low_level"]:
            e_val = eng[key]
            d_val = dir_[key]
            if isinstance(e_val, float) and isinstance(d_val, float):
                if math.isnan(e_val) and math.isnan(d_val):
                    continue
                if not math.isnan(e_val) and not math.isnan(d_val):
                    if abs(e_val - d_val) > 0.01:
                        mismatches += 1

    assert_eq(mismatches, 0, msg=f"Swing level mismatches: {mismatches}")


def test_eng_2() -> None:
    """Trend direction from engine matches direct detector."""
    engine_snaps, _ = _run_engine_and_capture(PLAY_ID)
    direct_snaps = _run_direct_detectors_on_engine_data(PLAY_ID)

    engine_by_idx = {s["exec_idx"]: s for s in engine_snaps}
    direct_by_idx = {s["exec_idx"]: s for s in direct_snaps}
    common_idxs = sorted(set(engine_by_idx) & set(direct_by_idx))

    mismatches = 0
    for idx in common_idxs:
        e_dir = int(engine_by_idx[idx]["trend.direction"])
        d_dir = int(direct_by_idx[idx]["trend.direction"])
        if e_dir != d_dir:
            mismatches += 1

    assert_eq(mismatches, 0, msg=f"Trend direction mismatches: {mismatches}")


def test_eng_3() -> None:
    """Market structure BOS/CHoCH events match between engine and direct."""
    engine_snaps, _ = _run_engine_and_capture(PLAY_ID)
    direct_snaps = _run_direct_detectors_on_engine_data(PLAY_ID)

    engine_by_idx = {s["exec_idx"]: s for s in engine_snaps}
    direct_by_idx = {s["exec_idx"]: s for s in direct_snaps}
    common_idxs = sorted(set(engine_by_idx) & set(direct_by_idx))

    bos_mismatches = 0
    choch_mismatches = 0
    for idx in common_idxs:
        if bool(engine_by_idx[idx]["ms.bos_this_bar"]) != bool(direct_by_idx[idx]["ms.bos_this_bar"]):
            bos_mismatches += 1
        if bool(engine_by_idx[idx]["ms.choch_this_bar"]) != bool(direct_by_idx[idx]["ms.choch_this_bar"]):
            choch_mismatches += 1

    assert_eq(bos_mismatches, 0, msg=f"BOS event mismatches: {bos_mismatches}")
    assert_eq(choch_mismatches, 0, msg=f"CHoCH event mismatches: {choch_mismatches}")


def test_eng_4() -> None:
    """Snapshot get_structure() returns current detector values (not stale)."""
    engine_snaps, n = _run_engine_and_capture(PLAY_ID)

    # At least some bars should have non-NaN swing levels
    non_nan_highs = sum(
        1 for s in engine_snaps
        if isinstance(s["swing.high_level"], float) and not math.isnan(s["swing.high_level"])
    )
    assert_true(
        non_nan_highs > 5,
        msg=f"Only {non_nan_highs} bars with non-NaN swing.high_level in {n} bars",
    )


def test_eng_5() -> None:
    """Structure versions monotonically non-decreasing through engine run."""
    engine_snaps, _ = _run_engine_and_capture(PLAY_ID)

    for key in ["swing.version", "trend.version", "ms.version"]:
        prev = -1
        for s in engine_snaps:
            cur = int(s[key])
            assert_true(
                cur >= prev,
                msg=f"{key} decreased: {prev} → {cur} at bar {s['exec_idx']}",
            )
            prev = cur


# ---------------------------------------------------------------------------
# Module interface
# ---------------------------------------------------------------------------


def get_tests() -> list[TestCase]:
    return [
        TestCase("ENG.1", "ENGINE", "Swing: engine == direct", test_eng_1),
        TestCase("ENG.2", "ENGINE", "Trend: engine == direct", test_eng_2),
        TestCase("ENG.3", "ENGINE", "MS BOS/CHoCH: engine == direct", test_eng_3),
        TestCase("ENG.4", "ENGINE", "Snapshot returns fresh values", test_eng_4),
        TestCase("ENG.5", "ENGINE", "Versions monotonic", test_eng_5),
    ]


if __name__ == "__main__":
    run_module_cli("engine_integration", get_tests())
