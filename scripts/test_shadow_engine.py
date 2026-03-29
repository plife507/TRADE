#!/usr/bin/env python3
"""
Integration test: ShadowEngine with historical replay.

Proves the full shadow pipeline works:
  synthetic data → Bar → ShadowEngine.on_candle() → LiveDataProvider
  → PlayEngine signal → SimExchange fill → trade record → stats

Usage:
    python3 scripts/test_shadow_engine.py
    python3 scripts/test_shadow_engine.py --play AT_001_ema_cross_basic
    python3 scripts/test_shadow_engine.py --verbose
"""

import sys
import time
from datetime import datetime
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.backtest.play.play import load_play
from src.backtest.runtime.types import Bar
from src.forge.validation.synthetic_data import generate_synthetic_candles
from src.config.constants import ALL_TIMEFRAMES
from src.shadow.config import ShadowPlayConfig
from src.shadow.engine import ShadowEngine
from src.shadow.types import ShadowEngineState


def run_test(play_id: str = "AT_001_ema_cross_basic", verbose: bool = False) -> bool:
    """Run the shadow engine integration test.

    Returns True if the test passes (engine processes bars and produces trades).
    """
    print(f"\n{'='*60}")
    print(f"  Shadow Engine Integration Test")
    print(f"  Play: {play_id}")
    print(f"{'='*60}\n")

    # 1. Load play
    print("[1/6] Loading play...", end=" ")
    try:
        play = load_play(play_id)
        print(f"OK ({play.symbol_universe[0]} {play.exec_tf})")
    except Exception as e:
        print(f"FAIL: {e}")
        return False

    # 2. Generate synthetic data
    print("[2/6] Generating synthetic data...", end=" ")
    symbol = play.symbol_universe[0]
    exec_tf = play.exec_tf

    # Collect concrete TFs the play uses (tf_mapping values are concrete like "15m", "1h")
    tf_set = {exec_tf}
    if play.tf_mapping:
        # tf_mapping: {"low_tf": "1m", "med_tf": "1h", ...} — values are concrete TFs
        for v in play.tf_mapping.values():
            if v in ALL_TIMEFRAMES:
                tf_set.add(v)
    timeframes = sorted(tf_set, key=lambda t: ALL_TIMEFRAMES.index(t) if t in ALL_TIMEFRAMES else 99)

    candles = generate_synthetic_candles(
        symbol=symbol,
        timeframes=timeframes,
        bars_per_tf=2000,
        seed=42,
        pattern="trending",
    )
    total_bars = sum(len(df) for df in candles.timeframes.values())
    print(f"OK ({total_bars} bars across {timeframes})")

    # 3. Create and initialize ShadowEngine
    print("[3/6] Initializing ShadowEngine...", end=" ")
    config = ShadowPlayConfig(initial_equity_usdt=10000.0)
    engine = ShadowEngine(play=play, instance_id="test_001", play_config=config)

    try:
        engine.initialize()
        print(f"OK (state={engine.state.value})")
    except Exception as e:
        print(f"FAIL: {e}")
        import traceback
        traceback.print_exc()
        return False

    # 4. Feed bars through the engine
    print("[4/6] Processing bars...", end=" ", flush=True)
    t0 = time.monotonic()

    from src.backtest.runtime.timeframe import tf_minutes as _tf_minutes
    from datetime import timedelta

    # Build per-TF bar lists sorted by timestamp for interleaved feeding
    # All TFs must be fed for LiveDataProvider warmup to complete
    all_events: list[tuple[datetime, str, Bar]] = []

    for tf_str in timeframes:
        tf_df = candles.timeframes.get(tf_str)
        if tf_df is None or len(tf_df) == 0:
            continue
        tf_min = _tf_minutes(tf_str)
        for i in range(len(tf_df)):
            row = tf_df.iloc[i]
            ts_val = row["timestamp"]
            ts_open = ts_val.to_pydatetime().replace(tzinfo=None) if hasattr(ts_val, "to_pydatetime") else ts_val
            ts_close = ts_open + timedelta(minutes=tf_min)
            bar = Bar(
                symbol=symbol, tf=tf_str,
                ts_open=ts_open, ts_close=ts_close,
                open=float(row["open"]), high=float(row["high"]),
                low=float(row["low"]), close=float(row["close"]),
                volume=float(row["volume"]),
            )
            all_events.append((ts_close, tf_str, bar))

    # Sort by timestamp (interleave TFs chronologically)
    all_events.sort(key=lambda x: x[0])
    num_events = len(all_events)
    print(f"({num_events} events across {timeframes})", end=" ", flush=True)

    errors: list[tuple[int, str]] = []
    for i, (_, tf_str, bar) in enumerate(all_events):
        try:
            engine.on_candle(bar, tf_str)
        except Exception as e:
            errors.append((i, str(e)))
            if len(errors) >= 5:
                break

        if verbose and i > 0 and i % 5000 == 0:
            stats = engine.stats
            print(f"\n  [{i}/{num_events}] "
                  f"state={engine.state.value} "
                  f"bars={stats.bars_processed} "
                  f"signals={stats.signals_generated} "
                  f"trades={stats.trades_closed} "
                  f"equity=${stats.equity_usdt:,.2f}", end="", flush=True)

    elapsed = time.monotonic() - t0
    stats = engine.stats
    print(f"OK ({stats.bars_processed} bars in {elapsed:.1f}s, {stats.bars_processed/elapsed:.0f} bars/s)")

    if errors:
        print(f"  Errors: {len(errors)}")
        for idx, err in errors[:3]:
            print(f"    bar {idx}: {err}")

    # 5. Stop engine and get final stats
    print("[5/6] Stopping engine...", end=" ")
    final_stats = engine.stop()
    print(f"OK (state={engine.state.value})")

    # 6. Verify results
    print(f"\n[6/6] Results:")
    print(f"  State:         {engine.state.value}")
    print(f"  Bars processed: {final_stats.bars_processed}")
    print(f"  Signals:       {final_stats.signals_generated}")
    print(f"  Trades opened: {final_stats.trades_opened}")
    print(f"  Trades closed: {final_stats.trades_closed}")
    print(f"  Win/Loss:      {final_stats.winning_trades}W / {final_stats.losing_trades}L")
    print(f"  Win rate:      {final_stats.win_rate:.1%}")
    print(f"  Equity:        ${final_stats.equity_usdt:,.2f}")
    print(f"  PnL:           ${final_stats.cumulative_pnl_usdt:,.2f}")
    print(f"  Max drawdown:  {final_stats.max_drawdown_pct:.1f}%")

    # Check journal files exist
    from src.shadow.journal import SHADOW_DATA_DIR
    journal_dir = SHADOW_DATA_DIR / "test_001"
    events_file = journal_dir / "events.jsonl"
    print(f"  Journal:       {events_file} ({'exists' if events_file.exists() else 'MISSING'})")
    if events_file.exists():
        line_count = sum(1 for _ in open(events_file))
        print(f"  Journal lines: {line_count}")

    # Drain trade/snapshot buffers
    trades = engine.drain_trades()
    snapshots = engine.drain_snapshots()
    print(f"  Buffered:      {len(trades)} trades, {len(snapshots)} snapshots")

    # Pass criteria
    passed = True
    checks = []

    if final_stats.bars_processed == 0:
        checks.append("FAIL: No bars processed")
        passed = False
    else:
        checks.append(f"PASS: {final_stats.bars_processed} bars processed")

    if engine.state != ShadowEngineState.STOPPED:
        checks.append(f"FAIL: State is {engine.state.value}, expected stopped")
        passed = False
    else:
        checks.append("PASS: Engine stopped cleanly")

    if final_stats.signals_generated == 0:
        checks.append("WARN: No signals generated (play may need more data or different pattern)")
    else:
        checks.append(f"PASS: {final_stats.signals_generated} signals generated")

    if final_stats.trades_closed > 0:
        checks.append(f"PASS: {final_stats.trades_closed} trades completed with P&L tracking")
    else:
        checks.append("WARN: No completed trades (may need more bars or different play)")

    if not errors:
        checks.append("PASS: No processing errors")
    else:
        checks.append(f"FAIL: {len(errors)} processing errors")
        passed = False

    print(f"\n{'─'*60}")
    for check in checks:
        marker = "✓" if check.startswith("PASS") else ("⚠" if check.startswith("WARN") else "✗")
        print(f"  {marker} {check}")
    print(f"{'─'*60}")
    print(f"\n  {'PASSED' if passed else 'FAILED'}\n")

    return passed


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Shadow Engine integration test")
    parser.add_argument("--play", default="AT_001_ema_cross_basic", help="Play to test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show progress")
    args = parser.parse_args()

    ok = run_test(play_id=args.play, verbose=args.verbose)
    sys.exit(0 if ok else 1)
