"""
Full engine stack WebSocket integration test.

Connects DIRECTLY to Bybit LIVE public WebSocket (no API keys, no demo
endpoint issues) and feeds real kline data through the actual engine stack:

1. Play YAML loading and feature spec parsing
2. LiveDataProvider initialization (buffers, indicator caches, TF routing)
3. LiveIndicatorCache incremental updates per closed bar
4. on_candle_close() multi-TF routing (low_tf/med_tf/high_tf)
5. Incremental vs vectorized indicator parity audit
6. Signal readiness path (get_candle, get_indicator at index -1)

Uses 1m as execution timeframe for fast closed-bar feedback (~60s).

NO orders. NO private streams. Read-only market data.

Usage:
    python scripts/test_engine_ws.py                               # Default play
    python scripts/test_engine_ws.py --play sol_ema_cross_demo     # Specific play
    python scripts/test_engine_ws.py --duration 180                # Run 3 minutes
"""

import argparse
import asyncio
import math
import queue
import sys
import time
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pybit.unified_trading import WebSocket

from src.data.realtime_models import KlineData, BarRecord
from src.engine.interfaces import Candle


# ---------------------------------------------------------------------------
# Result tracker
# ---------------------------------------------------------------------------
class EngineTestResults:
    """Thread-safe results collector."""

    def __init__(self):
        self._lock = threading.Lock()
        self.ws_msgs: dict[str, int] = defaultdict(int)
        self.ws_closed: dict[str, int] = defaultdict(int)
        self.callback_accepted: int = 0
        self.callback_filtered: int = 0
        self.dp_updates: dict[str, int] = defaultdict(int)
        self.dp_routing_errors: list[str] = []
        self.indicator_updates: dict[str, int] = defaultdict(int)
        self.indicator_values: dict[str, list[float]] = defaultdict(list)
        self.indicator_nans: dict[str, int] = defaultdict(int)
        self.readiness_checks: int = 0
        self.readiness_errors: list[str] = []
        self.parity_results: dict = {}

    def record_ws(self, interval: str, is_closed: bool):
        with self._lock:
            self.ws_msgs[interval] += 1
            if is_closed:
                self.ws_closed[interval] += 1

    def record_callback(self, accepted: bool):
        with self._lock:
            if accepted:
                self.callback_accepted += 1
            else:
                self.callback_filtered += 1

    def record_dp_update(self, tf_role: str):
        with self._lock:
            self.dp_updates[tf_role] += 1

    def record_dp_error(self, err: str):
        with self._lock:
            self.dp_routing_errors.append(err)

    def record_indicator(self, name: str, value: float):
        with self._lock:
            self.indicator_updates[name] += 1
            if math.isnan(value):
                self.indicator_nans[name] += 1
            else:
                self.indicator_values[name].append(value)

    def record_readiness_check(self, error: str | None = None):
        with self._lock:
            self.readiness_checks += 1
            if error:
                self.readiness_errors.append(error)


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------
async def run_test(
    play_path: str = "plays/sol_ema_cross_demo.yml",
    duration_s: int = 120,
):
    """Run full engine stack integration test."""
    import yaml
    from src.backtest.play.play import Play
    from src.engine.adapters.live import LiveDataProvider, LiveIndicatorCache
    from src.backtest.runtime.timeframe import tf_minutes as get_tf_minutes

    results = EngineTestResults()

    print("=" * 72)
    print("  TRADE Engine Stack WebSocket Integration Test")
    print("=" * 72)

    # ------------------------------------------------------------------
    # 1. Load Play, override TFs to 1m for fast feedback
    # ------------------------------------------------------------------
    print(f"\n[1/7] Loading Play: {play_path}")
    play_file = Path(play_path)
    if not play_file.is_absolute():
        play_file = Path(__file__).resolve().parent.parent / play_file
    if not play_file.exists():
        print(f"  FATAL: Play file not found: {play_file}")
        return False

    with open(play_file, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Override timeframes to 1m for fast closed-bar feedback
    raw["timeframes"] = {
        "low_tf": "1m",
        "med_tf": "1m",
        "high_tf": "1m",
        "exec": "low_tf",
    }
    play = Play.from_dict(raw)

    symbol = play.symbol_universe[0]
    exec_tf = "1m"

    print(f"  Symbol:    {symbol}")
    print(f"  Exec TF:   {exec_tf} (overridden for fast feedback)")
    print(f"  Features:  {len(play.features)} indicators")
    for feat in play.features:
        src = feat.input_source.value if hasattr(feat.input_source, 'value') else str(feat.input_source)
        print(f"    {feat.id}: {feat.indicator_type} (source={src})")
    print(f"  Duration:  {duration_s}s")

    # ------------------------------------------------------------------
    # 2. Initialize LiveDataProvider
    # ------------------------------------------------------------------
    print("\n[2/7] Initializing LiveDataProvider (standalone)...")
    data_provider = LiveDataProvider(play=play, demo=True)
    print(f"  TF mapping: {data_provider.tf_mapping}")

    # ------------------------------------------------------------------
    # 3. Initialize indicator caches from Play feature specs
    # ------------------------------------------------------------------
    print("\n[3/7] Initializing indicator caches from Play specs...")

    def feature_to_spec_dict(feat) -> dict:
        src = feat.input_source.value if hasattr(feat.input_source, 'value') else str(feat.input_source)
        return {
            "indicator_type": feat.indicator_type,
            "output_key": feat.id,
            "params": dict(feat.params),
            "input_source": src,
        }

    specs = [feature_to_spec_dict(f) for f in play.features if f.is_indicator]
    print(f"  Specs: {len(specs)}")

    # Fetch 200 historical 1m candles via REST to warm indicators.
    # EMA(200) needs 200+ bars, SMA(20) needs 20+.
    warmup_count = 250
    print(f"  Fetching {warmup_count} seed candles via REST...")
    from pybit.unified_trading import HTTP
    http = HTTP()
    resp = http.get_kline(category="linear", symbol=symbol, interval="1", limit=warmup_count)
    seed_bars = []
    if resp and resp.get("result", {}).get("list"):
        # Bybit returns newest first, reverse for chronological order
        for row in reversed(resp["result"]["list"]):
            seed_bars.append(BarRecord(
                timestamp=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).replace(tzinfo=None),
                open=float(row[1]), high=float(row[2]),
                low=float(row[3]), close=float(row[4]), volume=float(row[5]),
            ))
        print(f"  Got {len(seed_bars)} bars, last C={seed_bars[-1].close:.2f}")

    data_provider._low_tf_indicators.initialize_from_history(seed_bars, specs)

    # Also fill the low_tf buffer so warmup check passes
    for bar in seed_bars:
        data_provider._low_tf_buffer.append(Candle(
            ts_open=bar.timestamp, ts_close=bar.timestamp,
            open=bar.open, high=bar.high, low=bar.low,
            close=bar.close, volume=bar.volume,
        ))
    data_provider._check_all_tf_warmup()

    cache = data_provider._low_tf_indicators
    print(f"  Incremental: {list(cache._incremental.keys())}")
    print(f"  Indicators:  {list(cache._indicators.keys())}")
    print(f"  Buffer:      {len(data_provider.low_tf_buffer)} bars")
    print(f"  Ready:       {data_provider.is_ready()}")

    # Show initial indicator values
    for ind_name in cache._indicators:
        try:
            v = cache.get(ind_name, -1)
            print(f"    {ind_name} = {v:.6f}")
        except (IndexError, KeyError):
            print(f"    {ind_name} = ERR")

    # ------------------------------------------------------------------
    # 4. Connect to Bybit LIVE public WebSocket
    # ------------------------------------------------------------------
    print("\n[4/7] Connecting to Bybit LIVE public WebSocket...")
    ws = WebSocket(
        testnet=False,
        channel_type="linear",
        retries=3,
        restart_on_error=True,
        ping_interval=20,
        ping_timeout=10,
    )
    print("  -> Connected (LIVE public, read-only)")

    # ------------------------------------------------------------------
    # 5. Subscribe and wire callback
    # ------------------------------------------------------------------
    print(f"\n[5/7] Subscribing to kline.1.{symbol}...")

    candle_queue: queue.Queue = queue.Queue(maxsize=200)

    def on_kline(msg: dict):
        topic = msg.get("topic", "")
        for raw_k in msg.get("data", []):
            try:
                kline = KlineData.from_bybit(raw_k, topic)
            except Exception as e:
                print(f"  PARSE ERROR: {e}")
                return

            results.record_ws(kline.interval, kline.is_closed)

            if kline.symbol != symbol or kline.interval.lower() != "1m":
                results.record_callback(accepted=False)
                return

            if not kline.is_closed:
                results.record_callback(accepted=False)
                return

            results.record_callback(accepted=True)

            if kline.end_time > 0:
                close_ts_ms = kline.end_time + 1
            else:
                close_ts_ms = kline.start_time + 60_000

            candle = Candle(
                ts_open=datetime.fromtimestamp(kline.start_time / 1000.0, tz=timezone.utc),
                ts_close=datetime.fromtimestamp(close_ts_ms / 1000.0, tz=timezone.utc),
                open=kline.open, high=kline.high,
                low=kline.low, close=kline.close,
                volume=kline.volume,
            )

            try:
                candle_queue.put_nowait((candle, kline.interval))
            except queue.Full:
                try:
                    candle_queue.get_nowait()
                except queue.Empty:
                    pass
                candle_queue.put_nowait((candle, kline.interval))

    ws.kline_stream(interval=1, symbol=symbol, callback=on_kline)
    print(f"  -> Subscribed\n")

    # ------------------------------------------------------------------
    # 6. Processing loop
    # ------------------------------------------------------------------
    start_time = time.time()
    stop_event = asyncio.Event()

    async def process_loop():
        while not stop_event.is_set():
            try:
                try:
                    candle, timeframe = candle_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.1)
                    continue

                ts_str = candle.ts_open.strftime("%H:%M:%S")

                # --- Route through LiveDataProvider ---
                try:
                    data_provider.on_candle_close(candle, timeframe=timeframe)
                    tf_role = data_provider._get_tf_role_for_timeframe(timeframe)
                    results.record_dp_update(tf_role)
                except ValueError as e:
                    results.record_dp_error(str(e))
                    print(f"  ROUTING ERROR: {e}")
                    continue

                # --- Read indicator values ---
                ind_cache = data_provider._get_indicator_cache_for_role(tf_role)
                for ind_name in list(ind_cache._indicators.keys()):
                    try:
                        val = ind_cache.get(ind_name, -1)
                        results.record_indicator(ind_name, val)
                    except (IndexError, KeyError):
                        pass

                # --- Readiness check (simulates engine.process_bar) ---
                try:
                    latest = data_provider.get_candle(-1)
                    for ind_name in list(ind_cache._indicators.keys()):
                        ind_cache.get(ind_name, -1)
                    results.record_readiness_check()
                except Exception as e:
                    results.record_readiness_check(error=str(e))

                # --- Log ---
                ind_summary = ""
                for ind_name in list(ind_cache._indicators.keys())[:4]:
                    try:
                        v = ind_cache.get(ind_name, -1)
                        if not math.isnan(v):
                            ind_summary += f" {ind_name}={v:.2f}"
                        else:
                            ind_summary += f" {ind_name}=NaN"
                    except (IndexError, KeyError):
                        pass

                print(
                    f"  [{timeframe:>3s}] {ts_str} "
                    f"C={candle.close:<10.2f} V={candle.volume:<12.4f} "
                    f"buf={ind_cache.length:<4d}{ind_summary}"
                )

            except Exception as e:
                print(f"  LOOP ERROR: {e}")
                import traceback
                traceback.print_exc()

    loop_task = asyncio.create_task(process_loop())

    try:
        while time.time() - start_time < duration_s:
            await asyncio.sleep(1)
            elapsed = time.time() - start_time
            total_ws = sum(results.ws_msgs.values())
            total_closed = sum(results.ws_closed.values())
            total_dp = sum(results.dp_updates.values())
            sys.stdout.write(
                f"\r  [{elapsed:5.0f}s / {duration_s}s] "
                f"ws={total_ws} closed={total_closed} "
                f"dp={total_dp} checks={results.readiness_checks}"
            )
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n  -> Interrupted by user")

    stop_event.set()
    loop_task.cancel()
    try:
        await loop_task
    except asyncio.CancelledError:
        pass

    print("\n")

    # ------------------------------------------------------------------
    # 7. Parity audit + results
    # ------------------------------------------------------------------
    print("[6/7] Running incremental vs vectorized parity audit...")
    parity = data_provider._low_tf_indicators.audit_incremental_parity()
    results.parity_results = parity
    if parity:
        for name, result in parity.items():
            status = "PASS" if result.get("pass", False) else "FAIL"
            max_diff = result.get("max_diff", -1)
            mismatches = result.get("num_mismatches", -1)
            err = result.get("error", "")
            extra = f" ({err})" if err else ""
            print(f"    {status}  {name}: max_diff={max_diff:.2e}, mismatches={mismatches}{extra}")
    else:
        print("    (no incremental indicators to audit)")

    print(f"\n[7/7] Disconnecting...")
    try:
        ws.exit()
    except Exception:
        pass
    time.sleep(0.5)
    print("  -> Done\n")

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------
    print("=" * 72)
    print("  RESULTS")
    print("=" * 72)

    total_ws = sum(results.ws_msgs.values())
    total_closed = sum(results.ws_closed.values())
    total_dp = sum(results.dp_updates.values())
    elapsed = time.time() - start_time

    print(f"\n  WebSocket: {total_ws} msgs, {total_closed} closed in {elapsed:.0f}s")

    print(f"\n  DataProvider: {total_dp} on_candle_close() calls")
    for role, count in sorted(results.dp_updates.items()):
        print(f"    {role}: {count}")
    if results.dp_routing_errors:
        print(f"    ERRORS: {results.dp_routing_errors[:3]}")

    print(f"\n  Indicators:")
    for name in sorted(results.indicator_updates.keys()):
        count = results.indicator_updates[name]
        nans = results.indicator_nans.get(name, 0)
        vals = results.indicator_values.get(name, [])
        if vals:
            print(f"    {name}: {count} updates, {nans} NaN, "
                  f"last={vals[-1]:.6f}, range=[{min(vals):.6f}, {max(vals):.6f}]")
        else:
            print(f"    {name}: {count} updates, ALL NaN")

    print(f"\n  Readiness: {results.readiness_checks} checks, "
          f"{len(results.readiness_errors)} errors")

    print(f"\n  Buffers: low_tf={len(data_provider.low_tf_buffer)} bars")
    print(f"  Ready: {data_provider.is_ready()}")

    total_parity = len(results.parity_results)
    passed_parity = sum(1 for r in results.parity_results.values() if r.get("pass", False))
    print(f"\n  Parity: {passed_parity}/{total_parity} pass")

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------
    print(f"\n  Validation:")
    ok = 0
    fail = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal ok, fail
        if condition:
            ok += 1
            print(f"    PASS  {name}")
        else:
            fail += 1
            print(f"    FAIL  {name} -- {detail}")

    check("WebSocket received data", total_ws > 0)
    check("Closed bars received", total_closed > 0, f"0 in {duration_s}s")
    check("No routing errors", len(results.dp_routing_errors) == 0,
          str(results.dp_routing_errors[:3]))
    check("DataProvider got all closed bars", total_dp == total_closed,
          f"dp={total_dp} vs closed={total_closed}")
    check("No readiness errors", len(results.readiness_errors) == 0,
          str(results.readiness_errors[:3]))

    for name, count in results.indicator_updates.items():
        nans = results.indicator_nans.get(name, 0)
        check(f"{name} updated", count > 0)
        # First few bars will be NaN (warmup), that's expected
        # But not ALL should be NaN if we have enough bars
        if count > 10:
            check(f"{name} producing values", nans < count,
                  f"All {count} updates NaN")

    buf_len = len(data_provider.low_tf_buffer)
    expected_buf = len(seed_bars) + total_dp
    check("Buffer grew", buf_len >= expected_buf,
          f"buf={buf_len} vs expected>={expected_buf} (seed={len(seed_bars)}+dp={total_dp})")

    if total_parity > 0:
        check("Parity audit", passed_parity == total_parity,
              f"{total_parity - passed_parity} diverged")

    print(f"\n  Total: {ok} passed, {fail} failed")
    print("=" * 72)

    return fail == 0


def main():
    parser = argparse.ArgumentParser(
        description="Full engine stack WebSocket integration test"
    )
    parser.add_argument(
        "--play", default="plays/sol_ema_cross_demo.yml",
        help="Path to Play YAML (default: plays/sol_ema_cross_demo.yml)",
    )
    parser.add_argument(
        "--duration", type=int, default=120,
        help="Test duration in seconds (default: 120)",
    )
    args = parser.parse_args()

    success = asyncio.run(run_test(play_path=args.play, duration_s=args.duration))
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
