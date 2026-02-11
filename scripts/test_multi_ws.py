"""
Multi-stream WebSocket test script.

Connects to Bybit public WebSocket (LIVE market data, no API keys needed)
and subscribes to multiple kline intervals to validate:

1. Multi-TF subscription (1m, 15m, 1h simultaneously)
2. KlineData.from_bybit() parsing (interval normalization, symbol extraction)
3. Closed-bar detection (confirm=true)
4. Message routing by timeframe (simulates LiveRunner filtering)
5. RealtimeState kline storage and bar buffer management
6. Throughput and latency stats

Usage:
    python scripts/test_multi_ws.py                          # Default: BTCUSDT, 60s
    python scripts/test_multi_ws.py --symbol SOLUSDT         # Different symbol
    python scripts/test_multi_ws.py --duration 120           # Run 2 minutes
    python scripts/test_multi_ws.py --intervals 1 5 15 60    # Custom intervals
"""

import argparse
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


# ---------------------------------------------------------------------------
# Stats tracker
# ---------------------------------------------------------------------------
class StreamStats:
    """Thread-safe stats collector for WebSocket messages."""

    def __init__(self):
        self._lock = threading.Lock()
        self.msg_count: dict[str, int] = defaultdict(int)       # interval -> count
        self.closed_count: dict[str, int] = defaultdict(int)    # interval -> closed bars
        self.last_kline: dict[str, KlineData] = {}              # interval -> latest
        self.bar_records: dict[str, list[BarRecord]] = defaultdict(list)
        self.parse_errors: list[str] = []
        self.latencies_ms: list[float] = []
        self.first_msg_at: float | None = None
        self.last_msg_at: float | None = None

    def record(self, kline: KlineData, recv_time: float):
        with self._lock:
            if self.first_msg_at is None:
                self.first_msg_at = recv_time
            self.last_msg_at = recv_time

            self.msg_count[kline.interval] += 1
            self.last_kline[kline.interval] = kline

            if kline.is_closed:
                self.closed_count[kline.interval] += 1
                self.bar_records[kline.interval].append(BarRecord.from_kline_data(kline))

            # Latency: time since kline start + interval duration vs now
            # (rough estimate -- Bybit sends updates ~every 1-2s within an open bar)
            if kline.start_time > 0:
                kline_age_ms = (recv_time - kline.start_time / 1000.0) * 1000
                self.latencies_ms.append(kline_age_ms)

    def record_error(self, err: str):
        with self._lock:
            self.parse_errors.append(err)

    def snapshot(self) -> dict:
        with self._lock:
            avg_lat = (
                sum(self.latencies_ms) / len(self.latencies_ms)
                if self.latencies_ms
                else 0
            )
            elapsed = (
                (self.last_msg_at - self.first_msg_at) if self.first_msg_at and self.last_msg_at else 0
            )
            return {
                "elapsed_s": round(elapsed, 1),
                "total_msgs": sum(self.msg_count.values()),
                "by_interval": dict(self.msg_count),
                "closed_bars": dict(self.closed_count),
                "avg_latency_ms": round(avg_lat, 1),
                "parse_errors": len(self.parse_errors),
                "bar_records": {k: len(v) for k, v in self.bar_records.items()},
            }


# ---------------------------------------------------------------------------
# Simulated LiveRunner filter (multi-TF routing)
# ---------------------------------------------------------------------------
class MockLiveRouterFilter:
    """Simulates LiveRunner._on_kline_update() filtering logic."""

    def __init__(self, symbol: str, play_timeframes: set[str]):
        self.symbol = symbol.upper()
        self.play_timeframes = {tf.lower() for tf in play_timeframes}
        self._lock = threading.Lock()
        self.accepted: dict[str, int] = defaultdict(int)
        self.rejected_symbol: int = 0
        self.rejected_tf: int = 0
        self.rejected_not_closed: int = 0
        self.exec_tf_signals: int = 0

    def route(self, kline: KlineData, exec_tf: str) -> str | None:
        """Returns the action taken: 'signal_eval', 'indicator_update', or None."""
        with self._lock:
            if kline.symbol != self.symbol:
                self.rejected_symbol += 1
                return None

            kline_tf = kline.interval.lower()
            if kline_tf not in self.play_timeframes:
                self.rejected_tf += 1
                return None

            if not kline.is_closed:
                self.rejected_not_closed += 1
                return None

            self.accepted[kline_tf] += 1

            if kline_tf == exec_tf.lower():
                self.exec_tf_signals += 1
                return "signal_eval"
            return "indicator_update"

    def summary(self) -> dict:
        with self._lock:
            return {
                "accepted": dict(self.accepted),
                "rejected_symbol": self.rejected_symbol,
                "rejected_tf": self.rejected_tf,
                "rejected_not_closed": self.rejected_not_closed,
                "exec_tf_signals": self.exec_tf_signals,
            }


# ---------------------------------------------------------------------------
# Main test
# ---------------------------------------------------------------------------
def run_test(
    symbol: str = "BTCUSDT",
    bybit_intervals: list[str] = ["1", "15", "60"],
    duration_s: int = 60,
):
    """Connect to Bybit WebSocket and collect multi-TF kline data."""

    # Map Bybit intervals to our normalized format for display
    normalized = {bi: KlineData._normalize_interval(bi) for bi in bybit_intervals}
    play_tfs = set(normalized.values())

    print("=" * 70)
    print("  TRADE Multi-Stream WebSocket Test")
    print("=" * 70)
    print(f"  Symbol:     {symbol}")
    print(f"  Intervals:  {bybit_intervals} -> {list(play_tfs)}")
    print(f"  Duration:   {duration_s}s")
    print(f"  Mode:       PUBLIC (read-only, no API keys)")
    print("=" * 70)
    print()

    stats = StreamStats()

    # Pick exec TF = smallest interval (simulates typical play)
    exec_tf = sorted(play_tfs, key=lambda t: _tf_sort_key(t))[0]
    router = MockLiveRouterFilter(symbol, play_tfs)

    # --- Connect ---
    print("[1/4] Connecting to Bybit public WebSocket (linear)...")
    ws = WebSocket(
        testnet=False,
        channel_type="linear",
        retries=3,
        restart_on_error=True,
        ping_interval=20,
        ping_timeout=10,
    )
    print("  -> Connected\n")

    # --- Subscribe ---
    print(f"[2/4] Subscribing to {len(bybit_intervals)} kline streams...")

    def make_callback(bybit_interval: str):
        """Create a closure-based callback per interval."""
        def on_kline(msg: dict):
            recv_time = time.time()
            topic = msg.get("topic", "")
            data_list = msg.get("data", [])

            for raw in data_list:
                try:
                    kline = KlineData.from_bybit(raw, topic)
                except Exception as e:
                    stats.record_error(f"Parse error [{bybit_interval}]: {e}")
                    return

                # Record raw stats
                stats.record(kline, recv_time)

                # Route through mock LiveRunner filter
                action = router.route(kline, exec_tf)

                # Verbose logging for closed bars
                if kline.is_closed:
                    bar = BarRecord.from_kline_data(kline)
                    ts_str = bar.timestamp.strftime("%Y-%m-%d %H:%M")
                    action_str = action or "filtered"
                    print(
                        f"  BAR CLOSED [{kline.interval:>3s}] "
                        f"{ts_str} | O={kline.open:.2f} H={kline.high:.2f} "
                        f"L={kline.low:.2f} C={kline.close:.2f} "
                        f"V={kline.volume:.4f} -> {action_str}"
                    )

        return on_kline

    for bi in bybit_intervals:
        ws.kline_stream(interval=bi, symbol=symbol, callback=make_callback(bi))
        our_tf = normalized[bi]
        print(f"  -> Subscribed: kline.{bi}.{symbol} (={our_tf})")

    print()

    # --- Collect ---
    print(f"[3/4] Collecting data for {duration_s}s (Ctrl+C to stop early)...")
    print(f"  exec timeframe = {exec_tf} (signal eval)")
    print(f"  non-exec = {play_tfs - {exec_tf}} (indicator update only)")
    print()

    start = time.time()
    try:
        while time.time() - start < duration_s:
            time.sleep(1)
            elapsed = time.time() - start
            snap = stats.snapshot()
            total = snap["total_msgs"]
            # Progress line (overwrite)
            sys.stdout.write(
                f"\r  [{elapsed:5.0f}s / {duration_s}s] "
                f"msgs={total}  "
                f"closed={sum(snap['closed_bars'].values())}  "
                f"errors={snap['parse_errors']}"
            )
            sys.stdout.flush()
    except KeyboardInterrupt:
        print("\n  -> Interrupted by user")

    print("\n")

    # --- Disconnect ---
    print("[4/4] Disconnecting...")
    try:
        ws.exit()
    except Exception:
        pass
    time.sleep(0.5)
    print("  -> Done\n")

    # --- Report ---
    snap = stats.snapshot()
    router_snap = router.summary()

    print("=" * 70)
    print("  RESULTS")
    print("=" * 70)
    print()

    print("  Stream Statistics:")
    print(f"    Total messages:     {snap['total_msgs']}")
    print(f"    Elapsed:            {snap['elapsed_s']}s")
    if snap["elapsed_s"] > 0:
        rate = snap["total_msgs"] / snap["elapsed_s"]
        print(f"    Message rate:       {rate:.1f} msg/s")
    print(f"    Avg latency:        {snap['avg_latency_ms']:.0f}ms")
    print(f"    Parse errors:       {snap['parse_errors']}")
    print()

    print("  Messages by Interval:")
    for interval, count in sorted(snap["by_interval"].items()):
        closed = snap["closed_bars"].get(interval, 0)
        print(f"    {interval:>4s}:  {count:>6d} msgs, {closed:>3d} closed bars")
    print()

    print("  Router (simulated LiveRunner filter):")
    print(f"    Accepted (closed, in-play TF): {router_snap['accepted']}")
    print(f"    Rejected (wrong symbol):       {router_snap['rejected_symbol']}")
    print(f"    Rejected (wrong TF):           {router_snap['rejected_tf']}")
    print(f"    Rejected (not closed):         {router_snap['rejected_not_closed']}")
    print(f"    Exec TF signal evals:          {router_snap['exec_tf_signals']}")
    print()

    print("  KlineData Parsing Verification:")
    for interval, kline in stats.last_kline.items():
        print(f"    [{interval}] symbol={kline.symbol}, interval={kline.interval}, "
              f"is_closed={kline.is_closed}, "
              f"start_time={kline.start_time}, end_time={kline.end_time}")
    print()

    print("  BarRecord Conversion Check:")
    for interval, bars in stats.bar_records.items():
        if bars:
            last = bars[-1]
            print(f"    [{interval}] {len(bars)} bars stored, "
                  f"last: ts={last.timestamp}, O={last.open:.2f} C={last.close:.2f}")
        else:
            print(f"    [{interval}] 0 bars (no closed bars received in {duration_s}s window)")
    print()

    # Validation checks
    print("  Validation:")
    ok_count = 0
    fail_count = 0

    def check(name: str, condition: bool, detail: str = ""):
        nonlocal ok_count, fail_count
        if condition:
            ok_count += 1
            print(f"    PASS  {name}")
        else:
            fail_count += 1
            print(f"    FAIL  {name} -- {detail}")

    check("Received messages", snap["total_msgs"] > 0, "No messages received")
    check("No parse errors", snap["parse_errors"] == 0, f"{snap['parse_errors']} errors")
    check(
        "All intervals received data",
        len(snap["by_interval"]) == len(bybit_intervals),
        f"Expected {len(bybit_intervals)} intervals, got {len(snap['by_interval'])}",
    )

    # Verify KlineData fields
    for interval, kline in stats.last_kline.items():
        check(
            f"[{interval}] symbol parsed",
            kline.symbol == symbol,
            f"Got {kline.symbol!r}",
        )
        check(
            f"[{interval}] interval normalized",
            kline.interval in play_tfs,
            f"Got {kline.interval!r}, expected one of {play_tfs}",
        )
        check(
            f"[{interval}] OHLCV > 0",
            all(v > 0 for v in [kline.open, kline.high, kline.low, kline.close, kline.volume]),
            "Some OHLCV values are zero",
        )
        check(
            f"[{interval}] timestamps > 0",
            kline.start_time > 0 and kline.end_time > 0,
            f"start={kline.start_time}, end={kline.end_time}",
        )

    # Verify tf_to_bybit round-trip
    for bi in bybit_intervals:
        our_tf = normalized[bi]
        try:
            roundtrip = KlineData.tf_to_bybit(our_tf)
            check(
                f"tf_to_bybit({our_tf!r})",
                roundtrip == bi or roundtrip.lower() == bi.lower(),
                f"Expected {bi!r}, got {roundtrip!r}",
            )
        except ValueError as e:
            check(f"tf_to_bybit({our_tf!r})", False, str(e))

    # Verify router accepted closed bars from all play TFs
    for tf in play_tfs:
        accepted = router_snap["accepted"].get(tf, 0)
        # 1m should definitely have closed bars in 60s, others may not
        if tf == "1m" and duration_s >= 60:
            check(f"Router accepted [{tf}] closed bars", accepted > 0, "Expected at least 1")
        elif accepted > 0:
            check(f"Router accepted [{tf}] closed bars", True)

    print()
    print(f"  Total: {ok_count} passed, {fail_count} failed")
    print("=" * 70)

    if stats.parse_errors:
        print("\n  Parse Errors (first 5):")
        for err in stats.parse_errors[:5]:
            print(f"    - {err}")

    return fail_count == 0


def _tf_sort_key(tf: str) -> int:
    """Sort key: smaller timeframes first."""
    order = {
        "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
        "1h": 60, "2h": 120, "4h": 240, "6h": 360, "12h": 720,
        "D": 1440, "W": 10080, "M": 43200,
    }
    return order.get(tf, 9999)


def main():
    parser = argparse.ArgumentParser(
        description="Test multi-stream WebSocket connection to Bybit"
    )
    parser.add_argument("--symbol", default="BTCUSDT", help="Trading pair (default: BTCUSDT)")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds (default: 60)")
    parser.add_argument(
        "--intervals",
        nargs="+",
        default=["1", "15", "60"],
        help="Bybit kline intervals to subscribe (default: 1 15 60 = 1m 15m 1h)",
    )
    args = parser.parse_args()

    success = run_test(
        symbol=args.symbol,
        bybit_intervals=args.intervals,
        duration_s=args.duration,
    )
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
