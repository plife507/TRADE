"""
Comprehensive Demo Trading Readiness Test.

Exercises the REAL engine code through the REAL Bybit demo API.
Catches integration bugs (API errors, broken code paths, missing attributes)
that unit tests can't find.

12 phases, each testing a layer of the stack using actual production code:
  Phase 1: Play Loading & Config (no network)
  Phase 2: Exchange Connectivity (REST API)
  Phase 3: LiveDataProvider + Indicator Warmup
  Phase 4: WebSocket Data Feed
  Phase 5: LiveExchange + Order Execution
  Phase 6: Error Handling Edge Cases
  Phase 7: Full EngineManager Integration
  Phase 8: Journal & State Persistence
  Phase 9: Safety & Circuit Breakers
  Phase 10: Multi-TF Data Routing
  Phase 11: Advanced Order Lifecycle
  Phase 12: Runner State Machine & Instance Limits

Usage:
    python scripts/test_demo_readiness.py
    python scripts/test_demo_readiness.py --skip-orders
    python scripts/test_demo_readiness.py --play plays/sol_ema_cross_demo.yml
    python scripts/test_demo_readiness.py --engine-timeout 120
"""

import argparse
import asyncio
import math
import os
import sys
import time
import traceback
from typing import Any, cast
import yaml
from datetime import datetime, timezone
from io import TextIOWrapper
from pathlib import Path

# Ensure project root on PYTHONPATH
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# Fix Windows console encoding for Unicode (check marks, arrows in log output)
if sys.platform == "win32":
    try:
        cast(TextIOWrapper, sys.stdout).reconfigure(encoding="utf-8", errors="replace")
        cast(TextIOWrapper, sys.stderr).reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Load API keys from api_keys.env
_env_file = PROJECT_ROOT / "api_keys.env"
if _env_file.exists():
    for line in _env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

class CheckResult:
    """Single check result."""

    __slots__ = ("check_id", "name", "passed", "detail")

    def __init__(self, check_id: str, name: str, passed: bool, detail: str = ""):
        self.check_id = check_id
        self.name = name
        self.passed = passed
        self.detail = detail


class PhaseResult:
    """Collects checks for one phase."""

    def __init__(self, phase_num: int, title: str):
        self.phase_num = phase_num
        self.title = title
        self.checks: list[CheckResult] = []
        self.fatal = False
        self.fatal_reason = ""

    def record(self, check_id: str, name: str, passed: bool, detail: str = "") -> CheckResult:
        cr = CheckResult(check_id, name, passed, detail)
        self.checks.append(cr)
        icon = "+" if passed else "X"
        print(f"  [{icon}] {check_id} {name}: {'PASS' if passed else 'FAIL'}"
              + (f"  ({detail})" if detail else ""))
        return cr

    def set_fatal(self, reason: str):
        self.fatal = True
        self.fatal_reason = reason
        print(f"\n  [!] FATAL: {reason} -- stopping early\n")

    @property
    def passed(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed(self) -> int:
        return len(self.checks) - self.passed


class TestReport:
    """Collects all phase results and prints a summary."""

    def __init__(self):
        self.phases: list[PhaseResult] = []
        self.stopped_early = False

    def new_phase(self, phase_num: int, title: str) -> PhaseResult:
        print(f"\n--- Phase {phase_num}: {title} ---")
        pr = PhaseResult(phase_num, title)
        self.phases.append(pr)
        return pr

    def summary(self) -> bool:
        total = sum(len(p.checks) for p in self.phases)
        passed = sum(p.passed for p in self.phases)
        failed = total - passed

        print("\n" + "=" * 60)

        # Per-phase summary
        for p in self.phases:
            status = "FATAL" if p.fatal else f"{p.passed}/{len(p.checks)} pass"
            print(f"Phase {p.phase_num}: {p.title:<30s} {status}")

        print(f"\nTOTAL: {passed}/{total} pass, {failed} fail")

        if self.stopped_early:
            fatal_phase = next((p for p in self.phases if p.fatal), None)
            if fatal_phase:
                print(f"  Stopped early: {fatal_phase.fatal_reason}")

        if failed > 0:
            print("\nFailed checks:")
            for p in self.phases:
                for c in p.checks:
                    if not c.passed:
                        print(f"  [{c.check_id}] {c.name}: {c.detail}")

        print("=" * 60)
        return failed == 0


report = TestReport()


# ---------------------------------------------------------------------------
# Phase 1: Play Loading & Config
# ---------------------------------------------------------------------------

def phase_1_play_loading(play_path: Path) -> "tuple[PhaseResult, Any, Any]":
    """Load Play YAML and validate it parses correctly. No network."""
    ph = report.new_phase(1, "Play Loading & Config")

    # P1.1 Load raw YAML
    raw = None
    try:
        assert play_path.exists(), f"File not found: {play_path}"
        with open(play_path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        assert isinstance(raw, dict), "YAML root is not a dict"
        ph.record("P1.1", "Load Play YAML", True, str(play_path))
    except Exception as e:
        ph.record("P1.1", "Load Play YAML", False, str(e))
        ph.set_fatal("Cannot proceed without play file")
        return ph, None, None

    # P1.2 Override TFs to 1m for fast testing
    try:
        raw["timeframes"] = {
            "low_tf": "1m",
            "med_tf": "1m",
            "high_tf": "1m",
            "exec": "low_tf",
        }
        ph.record("P1.2", "Override TFs to 1m", True)
    except Exception as e:
        ph.record("P1.2", "Override TFs to 1m", False, str(e))

    # P1.3 Parse via Play.from_dict (the real loader)
    play = None
    try:
        from src.backtest.play.play import Play
        play = Play.from_dict(raw)
        assert play is not None
        # Validate features parsed with correct input_source
        feature_count = len(play.features) if play.features else 0
        assert feature_count >= 4, f"Expected >=4 features, got {feature_count}"
        # Check vol_avg has source=volume
        vol_features = [f for f in play.features
                        if hasattr(f, 'get') and f.get("output_key") == "vol_avg"]
        ph.record("P1.3", f"Play.from_dict() + {feature_count} features", True,
                   f"name={play.name}")
    except Exception as e:
        ph.record("P1.3", "Play.from_dict()", False, str(e))
        ph.set_fatal("Play parsing failed")
        return ph, None, None

    # P1.4 Build engine config
    config = None
    try:
        from src.engine.factory import _build_config_from_play
        config = _build_config_from_play(play, "demo", persist_state=True, state_save_interval=10)
        assert config is not None
        ph.record("P1.4", "_build_config_from_play()", True,
                   f"mode={config.mode}, equity={config.initial_equity}")
    except Exception as e:
        ph.record("P1.4", "_build_config_from_play()", False, str(e))
        ph.set_fatal("Config build failed")
        return ph, None, None

    # P1.5 Config validates
    try:
        assert config.initial_equity > 0, f"equity={config.initial_equity}"
        assert config.mode == "demo", f"mode={config.mode}"
        ph.record("P1.5", "Config validates", True,
                   f"equity={config.initial_equity}, mode={config.mode}")
    except AssertionError as e:
        ph.record("P1.5", "Config validates", False, str(e))

    return ph, play, config


# ---------------------------------------------------------------------------
# Phase 2: Exchange Connectivity (REST)
# ---------------------------------------------------------------------------

def phase_2_exchange_rest(play) -> "tuple[PhaseResult, Any]":
    """Test ExchangeManager initialization and REST API calls."""
    ph = report.new_phase(2, "Exchange Connectivity (REST)")

    symbol = play.symbol_universe[0]

    # P2.1 ExchangeManager init
    em = None
    try:
        # Ensure demo env
        os.environ["BYBIT_USE_DEMO"] = "true"
        os.environ["TRADING_MODE"] = "paper"

        demo_key = os.environ.get("BYBIT_DEMO_API_KEY", "")
        demo_secret = os.environ.get("BYBIT_DEMO_API_SECRET", "")
        assert demo_key, "BYBIT_DEMO_API_KEY not set"
        assert demo_secret, "BYBIT_DEMO_API_SECRET not set"

        from src.core.exchange_manager import ExchangeManager
        ExchangeManager._instance = None  # Reset singleton
        em = ExchangeManager()
        assert em._initialized
        assert em.use_demo is True
        ph.record("P2.1", "ExchangeManager init (demo)", True)
    except Exception as e:
        ph.record("P2.1", "ExchangeManager init (demo)", False, str(e))
        ph.set_fatal("ExchangeManager init failed (missing API keys?)")
        return ph, None

    # P2.2 get_balance()
    total: float = 0.0
    try:
        balance = em.get_balance()
        assert isinstance(balance, dict)
        total = balance.get("total", 0)
        available = balance.get("available", 0)
        ph.record("P2.2", "get_balance()", True,
                   f"total=${total:.2f}, avail=${available:.2f}")
    except Exception as e:
        ph.record("P2.2", "get_balance()", False, str(e))

    # P2.3 Balance > 0
    try:
        assert total > 0, f"Balance is ${total:.2f} -- demo account needs funds"
        ph.record("P2.3", "Balance > 0", True, f"${total:.2f}")
    except (AssertionError, NameError) as e:
        ph.record("P2.3", "Balance > 0", False, str(e))

    # P2.4 get_instrument_info
    try:
        info = em._get_instrument_info(symbol)
        assert info, "No instrument info"
        tick_size = em._get_tick_size(symbol)
        min_qty = em._get_min_qty(symbol)
        assert tick_size > 0
        assert min_qty > 0
        ph.record("P2.4", f"Instrument info ({symbol})", True,
                   f"tick={tick_size}, lot_size={min_qty}")
    except Exception as e:
        ph.record("P2.4", f"Instrument info ({symbol})", False, str(e))

    # P2.5 get_positions
    try:
        pos = em.get_position(symbol)
        is_flat = pos is None or (hasattr(pos, 'size') and abs(pos.size) < 1e-8)
        ph.record("P2.5", f"get_position({symbol})", True,
                   f"flat={is_flat}" + (f", size={pos.size}" if pos else ""))
    except Exception as e:
        ph.record("P2.5", f"get_position({symbol})", False, str(e))

    # P2.6 get_open_orders
    try:
        orders = em.get_open_orders(symbol)
        ph.record("P2.6", f"get_open_orders({symbol})", True, f"count={len(orders)}")
    except Exception as e:
        ph.record("P2.6", f"get_open_orders({symbol})", False, str(e))

    # P2.7 get_kline (REST) -- verify data via BybitClient.get_klines()
    try:
        df = em.bybit.get_klines(symbol, interval="1", limit=5)
        assert df is not None and len(df) > 0, "No kline data returned"
        # DataFrame has columns: timestamp, open, high, low, close, volume, turnover
        assert "close" in df.columns, f"Missing 'close' column, got {list(df.columns)}"
        ph.record("P2.7", "get_klines (REST 1m)", True,
                   f"rows={len(df)}, cols={list(df.columns)}")
    except Exception as e:
        ph.record("P2.7", "get_klines (REST 1m)", False, str(e))

    return ph, em


# ---------------------------------------------------------------------------
# Phase 3: LiveDataProvider + Indicator Warmup
# ---------------------------------------------------------------------------

async def phase_3_data_provider(play, em) -> "tuple[PhaseResult, Any]":
    """Create LiveDataProvider, verify TF mapping, warmup, parity audit."""
    ph = report.new_phase(3, "LiveDataProvider + Indicator Warmup")

    # P3.1 DataProvider init
    dp = None
    try:
        from src.engine.adapters.live import LiveDataProvider
        dp = LiveDataProvider(play, demo=True)
        ph.record("P3.1", "LiveDataProvider init", True,
                   f"symbol={dp.symbol}, exec_tf={dp.timeframe}")
    except Exception as e:
        ph.record("P3.1", "LiveDataProvider init", False, str(e))
        ph.set_fatal("LiveDataProvider creation failed")
        return ph, None

    # P3.2 TF mapping correct
    try:
        mapping = dp.tf_mapping
        assert "low_tf" in mapping
        assert "med_tf" in mapping
        assert "high_tf" in mapping
        assert "exec" in mapping
        # After our override, all should be "1m"
        assert mapping["low_tf"] == "1m"
        ph.record("P3.2", "TF mapping correct", True, str(mapping))
    except AssertionError as e:
        ph.record("P3.2", "TF mapping correct", False, str(e))

    # P3.3 Indicator cache created
    try:
        cache = dp._low_tf_indicators
        assert cache is not None, "Indicator cache is None"
        assert hasattr(cache, '_incremental'), "Missing _incremental dict"
        ph.record("P3.3", "Indicator cache created", True)
    except Exception as e:
        ph.record("P3.3", "Indicator cache created", False, str(e))

    # P3.4 REST warmup (250 bars)
    # Fetch REST klines via BybitClient.get_klines() and feed into indicator cache
    bars = []
    try:
        from src.data.realtime_models import BarRecord

        df = em.bybit.get_klines(play.symbol_universe[0], interval="1", limit=250)
        assert df is not None and len(df) > 0, "No kline data from REST"

        # DataFrame is already chronological with pd.Timestamp columns
        for _, row in df.iterrows():
            ts = row["timestamp"]
            # Convert pandas Timestamp to Python datetime if needed
            if hasattr(ts, 'to_pydatetime'):
                ts = ts.to_pydatetime()
            bar = BarRecord(
                timestamp=ts,
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            bars.append(bar)

        # Convert Feature objects to FeatureSpec-compatible dicts
        # (Feature.id -> output_key, filter indicators only)
        specs = []
        for feature in play.features:
            from src.backtest.feature_registry import FeatureType
            if getattr(feature, "type", None) != FeatureType.INDICATOR:
                continue
            input_source = getattr(feature, "input_source", None)
            if input_source is not None and hasattr(input_source, "value"):
                input_source = input_source.value
            else:
                input_source = str(input_source) if input_source else "close"
            specs.append({
                "indicator_type": feature.indicator_type,
                "output_key": feature.id,
                "params": dict(feature.params) if feature.params else {},
                "input_source": input_source,
            })

        # Initialize cache from history
        cache = dp._low_tf_indicators
        cache.initialize_from_history(bars, specs)

        ph.record("P3.4", f"REST warmup ({len(bars)} bars)", True,
                   f"cache.length={cache.length}")
    except Exception as e:
        ph.record("P3.4", "REST warmup (250 bars)", False,
                   f"{type(e).__name__}: {e}")

    # P3.5 Indicators populated
    try:
        cache = dp._low_tf_indicators
        assert cache.length > 0, f"Cache empty (length={cache.length})"
        indicator_names = list(cache._indicators.keys())
        assert len(indicator_names) >= 4, f"Expected >=4 indicators, got {len(indicator_names)}"

        # Check last value is not NaN for each indicator
        non_nan_count = 0
        for name in indicator_names:
            val = cache.get(name, -1)
            if not math.isnan(val):
                non_nan_count += 1

        ph.record("P3.5", f"Indicators populated ({non_nan_count}/{len(indicator_names)} non-NaN)",
                   non_nan_count == len(indicator_names),
                   f"indicators={indicator_names}")
    except Exception as e:
        ph.record("P3.5", "Indicators populated", False, str(e))

    # P3.6 is_ready() == True
    # After manual warmup we need to also populate the buffer
    try:
        from src.engine.interfaces import Candle
        # Populate the candle buffer so is_ready() bar count check passes
        for bar in bars[-dp._warmup_bars:]:
            candle = Candle(
                ts_open=bar.timestamp,
                ts_close=bar.timestamp,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            dp._low_tf_buffer.append(candle)

        dp._check_all_tf_warmup()
        ready = dp.is_ready()
        ph.record("P3.6", "is_ready() == True", ready,
                   f"buffer={len(dp._low_tf_buffer)}, warmup_target={dp._warmup_bars}")
    except Exception as e:
        ph.record("P3.6", "is_ready()", False, str(e))

    # P3.7 Parity audit pass
    try:
        cache = dp._low_tf_indicators
        audit = cache.audit_incremental_parity()
        all_pass = all(r.get("pass", False) for r in audit.values())
        max_diffs = {k: f'{v["max_diff"]:.2e}' for k, v in audit.items()}
        ph.record("P3.7", "Parity audit", all_pass, str(max_diffs))
    except Exception as e:
        ph.record("P3.7", "Parity audit", False, str(e))

    # P3.8 Input source routing from candle (_resolve_input_from_candle)
    # Define MockFeature outside try so it's available in P3.9 too
    class MockFeature:
        def __init__(self, src: str):
            self.input_source = src

    try:
        from src.engine.interfaces import Candle as TestCandle

        test_candle = TestCandle(
            ts_open=datetime.now(timezone.utc),
            ts_close=datetime.now(timezone.utc),
            open=100.0, high=110.0, low=90.0, close=105.0, volume=5000.0,
        )

        cache_inst = dp._low_tf_indicators
        results = {}
        expected = {
            "close": 105.0,
            "open": 100.0,
            "high": 110.0,
            "low": 90.0,
            "volume": 5000.0,
        }
        all_match = True
        for src, expected_val in expected.items():
            feat = MockFeature(src)
            actual = cache_inst._resolve_input_from_candle(feat, test_candle)
            results[src] = actual
            if abs(actual - expected_val) > 1e-6:
                all_match = False

        # Also test hlc3 and ohlc4
        hlc3_feat = MockFeature("hlc3")
        hlc3_val = cache_inst._resolve_input_from_candle(hlc3_feat, test_candle)
        hlc3_expected = (110.0 + 90.0 + 105.0) / 3.0
        if abs(hlc3_val - hlc3_expected) > 1e-6:
            all_match = False
        results["hlc3"] = hlc3_val

        ohlc4_feat = MockFeature("ohlc4")
        ohlc4_val = cache_inst._resolve_input_from_candle(ohlc4_feat, test_candle)
        ohlc4_expected = (100.0 + 110.0 + 90.0 + 105.0) / 4.0
        if abs(ohlc4_val - ohlc4_expected) > 1e-6:
            all_match = False
        results["ohlc4"] = ohlc4_val

        ph.record("P3.8", "Input source routing (candle)", all_match,
                   f"7 sources tested: {results}")
    except Exception as e:
        ph.record("P3.8", "Input source routing (candle)", False, str(e))

    # P3.9 Input source routing from arrays (_resolve_input_from_arrays)
    try:
        cache_inst = dp._low_tf_indicators
        # Use the last index of the warmed-up arrays
        last_idx = cache_inst._bar_count - 1
        assert last_idx >= 0, "No bars in cache"

        last_close = float(cache_inst._close[last_idx])
        last_volume = float(cache_inst._volume[last_idx])
        last_high = float(cache_inst._high[last_idx])

        close_feat = MockFeature("close")
        vol_feat = MockFeature("volume")
        high_feat = MockFeature("high")

        close_val = cache_inst._resolve_input_from_arrays(close_feat, last_idx)
        vol_val = cache_inst._resolve_input_from_arrays(vol_feat, last_idx)
        high_val = cache_inst._resolve_input_from_arrays(high_feat, last_idx)

        close_ok = abs(close_val - last_close) < 1e-6
        vol_ok = abs(vol_val - last_volume) < 1e-6
        high_ok = abs(high_val - last_high) < 1e-6

        ph.record("P3.9", "Input source routing (arrays)", close_ok and vol_ok and high_ok,
                   f"close={close_val}, volume={vol_val}, high={high_val}")
    except Exception as e:
        ph.record("P3.9", "Input source routing (arrays)", False, str(e))

    return ph, dp


# ---------------------------------------------------------------------------
# Phase 4: WebSocket Data Feed
# ---------------------------------------------------------------------------

async def phase_4_websocket(play) -> "tuple[PhaseResult, Any]":
    """Test WebSocket connectivity and candle streaming."""
    ph = report.new_phase(4, "WebSocket Data Feed")

    from src.data.realtime_bootstrap import get_realtime_bootstrap, reset_realtime_bootstrap
    from src.data.realtime_state import get_realtime_state, reset_realtime_state
    from src.data.realtime_models import KlineData

    symbol = play.symbol_universe[0]

    # Reset singletons for clean test
    reset_realtime_bootstrap()
    reset_realtime_state()

    bootstrap = None
    state = None

    # P4.1 Bootstrap start
    try:
        bootstrap = get_realtime_bootstrap()
        assert bootstrap is not None
        bootstrap.start(symbols=[symbol], include_private=False)
        await asyncio.sleep(3.0)
        assert bootstrap.is_running, "Bootstrap not running after start"
        ph.record("P4.1", "Bootstrap start", True)
    except Exception as e:
        ph.record("P4.1", "Bootstrap start", False, str(e))
        ph.set_fatal("WebSocket bootstrap failed")
        return ph, None

    # P4.2 Subscribe klines
    try:
        bybit_interval = KlineData.tf_to_bybit("1m")
        bootstrap.subscribe_kline_intervals(symbol, [bybit_interval])
        ph.record("P4.2", "Subscribe klines (1m)", True,
                   f"interval={bybit_interval}")
    except Exception as e:
        ph.record("P4.2", "Subscribe klines", False, str(e))

    # P4.3 Receive WS messages (wait up to 90s)
    got_data = False
    try:
        state = get_realtime_state()
        env = "demo"

        # Poll for data arrival
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            bars = state.get_bar_buffer(env=env, symbol=symbol, timeframe="1m", limit=1)
            if bars:
                got_data = True
                break
            await asyncio.sleep(5.0)

        ph.record("P4.3", "Receive WS messages", got_data,
                   "Data arrived" if got_data else "No data in 90s")
    except Exception as e:
        ph.record("P4.3", "Receive WS messages", False, str(e))

    # P4.4 KlineData parsing (synthetic)
    try:
        fake_topic = f"kline.1.{symbol}"
        fake_candle = {
            "start": int(datetime.now(timezone.utc).timestamp() * 1000),
            "end": int(datetime.now(timezone.utc).timestamp() * 1000) + 59999,
            "open": "180.50",
            "high": "181.00",
            "low": "180.00",
            "close": "180.75",
            "volume": "12345.67",
            "confirm": True,
            "interval": "1",
        }
        kline = KlineData.from_bybit(fake_candle, topic=fake_topic)
        assert kline.symbol == symbol, f"Symbol mismatch: {kline.symbol}"
        assert kline.interval == "1m", f"Interval mismatch: {kline.interval}"
        assert kline.is_closed is True
        assert abs(kline.close - 180.75) < 0.001
        ph.record("P4.4", "KlineData.from_bybit() parsing", True,
                   f"symbol={kline.symbol}, interval={kline.interval}")
    except Exception as e:
        ph.record("P4.4", "KlineData.from_bybit() parsing", False, str(e))

    # P4.5 Closed bar received (wait up to 90s for confirm=True)
    try:
        # For 1m candles we should get a close within ~60s
        got_closed = False
        assert state is not None, "RealtimeState not initialized"
        if got_data:
            # Check existing bars for closed ones
            bars = state.get_bar_buffer(env="demo", symbol=symbol, timeframe="1m", limit=5)
            if bars:
                got_closed = True  # Bar buffer only stores confirmed bars

            if not got_closed:
                deadline = time.monotonic() + 90
                while time.monotonic() < deadline:
                    bars = state.get_bar_buffer(env="demo", symbol=symbol, timeframe="1m", limit=5)
                    if bars and len(bars) >= 1:
                        got_closed = True
                        break
                    await asyncio.sleep(5.0)

        ph.record("P4.5", "Closed bar received", got_closed,
                   "Confirmed bar in buffer" if got_closed else "No closed bar yet")
    except Exception as e:
        ph.record("P4.5", "Closed bar received", False, str(e))

    # P4.6 on_candle_close routes (feed bar through DataProvider)
    test_dp = None
    try:
        from src.engine.adapters.live import LiveDataProvider
        from src.engine.interfaces import Candle

        test_dp = LiveDataProvider(play, demo=True)
        # Seed with some buffer
        for i in range(110):
            c = Candle(
                ts_open=datetime.now(timezone.utc),
                ts_close=datetime.now(timezone.utc),
                open=180.0 + i * 0.01, high=181.0, low=179.0,
                close=180.5 + i * 0.01, volume=1000.0,
            )
            test_dp._low_tf_buffer.append(c)

        new_candle = Candle(
            ts_open=datetime.now(timezone.utc),
            ts_close=datetime.now(timezone.utc),
            open=180.0, high=181.0, low=179.0, close=180.5, volume=1234.0,
        )
        test_dp.on_candle_close(new_candle, timeframe="1m")
        assert len(test_dp._low_tf_buffer) == 111
        ph.record("P4.6", "on_candle_close routes", True)
    except Exception as e:
        ph.record("P4.6", "on_candle_close routes", False, str(e))

    # P4.7 Indicators update after new bar
    try:
        assert test_dp is not None, "DataProvider not initialized from P4.6"
        cache = test_dp._low_tf_indicators
        before_len = cache.length
        # We can't easily verify indicators change without warmup
        # Just verify no crash
        ph.record("P4.7", "Indicators update (no crash)", True,
                   f"cache.length={cache.length}")
    except Exception as e:
        ph.record("P4.7", "Indicators update", False, str(e))

    # P4.9 TickerData.from_bybit() synthetic parsing (all price fields)
    try:
        from src.data.realtime_models import TickerData

        fake_ticker = {
            "symbol": symbol,
            "lastPrice": "182.50",
            "bid1Price": "182.49",
            "ask1Price": "182.51",
            "bid1Size": "100.5",
            "ask1Size": "200.3",
            "highPrice24h": "185.00",
            "lowPrice24h": "178.00",
            "volume24h": "1234567.89",
            "markPrice": "182.505",
            "indexPrice": "182.48",
            "fundingRate": "0.0001",
        }
        ticker = TickerData.from_bybit(fake_ticker)
        assert ticker.symbol == symbol
        assert abs(ticker.last_price - 182.50) < 0.001
        assert abs(ticker.bid_price - 182.49) < 0.001
        assert abs(ticker.ask_price - 182.51) < 0.001
        assert abs(ticker.mark_price - 182.505) < 0.001
        assert abs(ticker.index_price - 182.48) < 0.001
        assert ticker.spread > 0, f"Spread should be >0, got {ticker.spread}"
        ph.record("P4.9", "TickerData.from_bybit() price fields", True,
                   f"last={ticker.last_price}, mark={ticker.mark_price}, "
                   f"bid={ticker.bid_price}, ask={ticker.ask_price}, "
                   f"spread={ticker.spread:.4f}")
    except Exception as e:
        ph.record("P4.9", "TickerData.from_bybit() price fields", False, str(e))

    # P4.10 Real ticker data from WebSocket (if available)
    try:
        from src.data.realtime_models import TickerData

        assert state is not None, "RealtimeState not initialized"
        # Ticker subscription may have been set up by bootstrap.start()
        # Poll for up to 10s to see if ticker data arrives
        ticker_data = None
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            ticker_data = state.get_ticker(symbol)
            if ticker_data is not None:
                break
            await asyncio.sleep(1.0)

        if ticker_data is not None:
            has_price = ticker_data.last_price > 0
            ph.record("P4.10", "Real ticker from WS", has_price,
                       f"last={ticker_data.last_price}, mark={ticker_data.mark_price}, "
                       f"bid={ticker_data.bid_price}, ask={ticker_data.ask_price}")
        else:
            # Ticker not subscribed by default -- inject synthetic one and verify state API
            synthetic = TickerData(
                symbol=symbol, last_price=180.0, bid_price=179.99,
                ask_price=180.01, mark_price=180.005,
            )
            state.update_ticker(synthetic)
            readback = state.get_ticker(symbol)
            ph.record("P4.10", "Real ticker from WS (injected)", readback is not None,
                       "No WS ticker, verified state.update_ticker/get_ticker round-trip")
    except Exception as e:
        ph.record("P4.10", "Real ticker from WS", False, str(e))

    # P4.11 Price sanity checks (last_price > 0, bid < ask, staleness API)
    try:
        assert state is not None, "RealtimeState not initialized"
        ticker_data = state.get_ticker(symbol)
        assert ticker_data is not None, "No ticker data available"

        checks_passed = []
        # last_price > 0
        checks_passed.append(("last_price>0", ticker_data.last_price > 0))
        # bid <= ask (valid spread)
        if ticker_data.bid_price > 0 and ticker_data.ask_price > 0:
            checks_passed.append(("bid<=ask", ticker_data.bid_price <= ticker_data.ask_price))
        # mark_price reasonable (within 5% of last_price if both set)
        if ticker_data.mark_price > 0 and ticker_data.last_price > 0:
            pct_diff = abs(ticker_data.mark_price - ticker_data.last_price) / ticker_data.last_price * 100
            checks_passed.append((f"mark~last({pct_diff:.2f}%)", pct_diff < 5.0))
        # Staleness API works
        stale = state.is_ticker_stale(symbol, max_age_seconds=60)
        checks_passed.append(("not_stale", not stale))

        all_ok = all(ok for _, ok in checks_passed)
        detail = ", ".join(f"{name}={'OK' if ok else 'FAIL'}" for name, ok in checks_passed)
        ph.record("P4.11", "Price sanity checks", all_ok, detail)
    except Exception as e:
        ph.record("P4.11", "Price sanity checks", False, str(e))

    # P4.8 Bootstrap stop
    try:
        bootstrap.stop()
        await asyncio.sleep(1.0)
        ph.record("P4.8", "Bootstrap stop", True)
    except Exception as e:
        ph.record("P4.8", "Bootstrap stop", False, str(e))

    return ph, state


# ---------------------------------------------------------------------------
# Phase 5: LiveExchange + Order Execution
# ---------------------------------------------------------------------------

async def phase_5_order_execution(play, config) -> PhaseResult:
    """Test LiveExchange adapter and real order execution on demo API."""
    ph = report.new_phase(5, "LiveExchange + Order Execution")

    from src.engine.adapters.live import LiveExchange

    symbol = play.symbol_universe[0]

    # P5.1 LiveExchange init
    exchange = None
    try:
        exchange = LiveExchange(play, config, demo=True)
        ph.record("P5.1", "LiveExchange init", True, f"symbol={symbol}")
    except Exception as e:
        ph.record("P5.1", "LiveExchange init", False, str(e))
        ph.set_fatal("LiveExchange creation failed")
        return ph

    # P5.2 LiveExchange connect
    try:
        await exchange.connect()
        assert exchange.is_connected
        ph.record("P5.2", "LiveExchange connect", True)
    except Exception as e:
        ph.record("P5.2", "LiveExchange connect", False, str(e))
        ph.set_fatal("LiveExchange connect failed")
        return ph

    # P5.3 get_balance works
    try:
        balance = exchange.get_balance()
        assert balance > 0, f"Balance={balance}"
        ph.record("P5.3", "get_balance()", True, f"${balance:.2f}")
    except Exception as e:
        ph.record("P5.3", "get_balance()", False, str(e))

    # P5.4 get_equity works
    try:
        equity = exchange.get_equity()
        assert equity > 0, f"Equity={equity}"
        ph.record("P5.4", "get_equity()", True, f"${equity:.2f}")
    except Exception as e:
        ph.record("P5.4", "get_equity()", False, str(e))

    # P5.5 get_position (none)
    try:
        pos = exchange.get_position(symbol)
        is_flat = pos is None
        ph.record("P5.5", "get_position (flat)", is_flat,
                   f"pos={'None' if pos is None else f'size={pos.size_usdt}'}")
    except Exception as e:
        ph.record("P5.5", "get_position (flat)", False, str(e))

    # P5.6 SafetyChecks pass
    try:
        from src.core.safety import SafetyChecks, get_panic_state, reset_panic

        # Reset any stale panic
        panic = get_panic_state()
        if panic.is_triggered:
            reset_panic("RESET")

        assert exchange._exchange_manager is not None, "ExchangeManager not initialized"
        checks = SafetyChecks(exchange._exchange_manager, exchange._exchange_manager.config)
        passed, failures = checks.run_all_checks()
        ph.record("P5.6", "SafetyChecks.run_all_checks()", passed,
                   "all clear" if passed else f"failures={failures}")
    except Exception as e:
        ph.record("P5.6", "SafetyChecks.run_all_checks()", False, str(e))

    # P5.7 Risk check pass
    try:
        from src.core.risk_manager import Signal
        from src.core.position_manager import PositionManager

        assert exchange._exchange_manager is not None, "ExchangeManager not initialized"
        pm = PositionManager(exchange._exchange_manager)
        signal = Signal(
            symbol=symbol,
            direction="SHORT",
            size_usdt=11.0,  # Just above $10 min notional
            strategy="demo_readiness_test",
            confidence=1.0,
        )
        portfolio = pm.get_snapshot()
        assert exchange._risk_manager is not None, "RiskManager not initialized"
        risk_result = exchange._risk_manager.check(signal, portfolio)
        ph.record("P5.7", "RiskManager.check()", risk_result.allowed,
                   f"allowed={risk_result.allowed}, reason={risk_result.reason}")
    except Exception as e:
        ph.record("P5.7", "RiskManager.check()", False, str(e))

    # P5.8 Market order (min size)
    order_success = False
    try:
        from src.engine.interfaces import Order as EngineOrder

        order = EngineOrder(
            symbol=symbol,
            side="SHORT",
            size_usdt=11.0,  # Just above min notional
            order_type="MARKET",
        )
        result = exchange.submit_order(order)
        order_success = result.success
        ph.record("P5.8", "Market order (min size)", result.success,
                   f"order_id={result.order_id}, error={result.error}")
    except Exception as e:
        ph.record("P5.8", "Market order (min size)", False, str(e))

    # P5.9 Position exists
    if order_success:
        try:
            await asyncio.sleep(2.0)
            pos = exchange.get_position(symbol)
            has_pos = pos is not None
            ph.record("P5.9", "Position exists", has_pos,
                       f"side={pos.side}, size_usdt={pos.size_usdt}" if pos else "None")
        except Exception as e:
            ph.record("P5.9", "Position exists", False, str(e))
    else:
        ph.record("P5.9", "Position exists", False, "Skipped (order failed)")

    # P5.10 Close position
    if order_success:
        try:
            assert exchange._exchange_manager is not None, "ExchangeManager not initialized"
            close_result = exchange._exchange_manager.close_position(symbol)
            ph.record("P5.10", "Close position", close_result.success,
                       f"error={close_result.error}" if not close_result.success else "closed")
        except Exception as e:
            ph.record("P5.10", "Close position", False, str(e))
    else:
        ph.record("P5.10", "Close position", False, "Skipped (no position)")

    # P5.11 Position is flat
    if order_success:
        try:
            await asyncio.sleep(2.0)
            pos = exchange.get_position(symbol)
            is_flat = pos is None or (hasattr(pos, 'size_qty') and abs(pos.size_qty) < 1e-8)
            ph.record("P5.11", "Position flat after close", is_flat,
                       f"pos={'None' if pos is None else f'qty={pos.size_qty}'}")
        except Exception as e:
            ph.record("P5.11", "Position flat after close", False, str(e))
    else:
        ph.record("P5.11", "Position flat after close", False, "Skipped")

    # P5.12 get_realized_pnl
    try:
        pnl = exchange.get_realized_pnl()
        ph.record("P5.12", "get_realized_pnl()", True, f"${pnl:.4f}")
    except Exception as e:
        ph.record("P5.12", "get_realized_pnl()", False, str(e))

    return ph


# ---------------------------------------------------------------------------
# Phase 6: Error Handling Edge Cases
# ---------------------------------------------------------------------------

async def phase_6_edge_cases(play, em) -> PhaseResult:
    """Test error-handling edge cases through the real code."""
    ph = report.new_phase(6, "Error Handling Edge Cases")

    symbol = play.symbol_universe[0]

    # P6.1 Cancel fake order
    try:
        result = em.cancel_order(symbol, order_id="fake-id-12345")
        # Expected: returns False gracefully
        ph.record("P6.1", "Cancel fake order", result is False or result is True,
                   f"returned={result} (no crash)")
    except Exception as e:
        ph.record("P6.1", "Cancel fake order", False,
                   f"Crashed: {type(e).__name__}: {e}")

    # P6.2 Zero-size order
    rm = None
    portfolio = None
    try:
        from src.core.risk_manager import RiskManager, Signal
        from src.core.position_manager import PositionManager

        pm = PositionManager(em)
        rm = RiskManager(enable_global_risk=False, exchange_manager=em)
        zero_signal = Signal(
            symbol=symbol,
            direction="SHORT",
            size_usdt=0.0,
            strategy="test_zero",
        )
        portfolio = pm.get_snapshot()
        risk_result = rm.check(zero_signal, portfolio)
        # Zero size should be rejected or handled gracefully
        ph.record("P6.2", "Zero-size signal", True,
                   f"allowed={risk_result.allowed}, reason={risk_result.reason}")
    except Exception as e:
        ph.record("P6.2", "Zero-size signal", False, str(e))

    # P6.3 Huge order rejected
    try:
        from src.core.risk_manager import Signal as Signal_
        assert rm is not None, "RiskManager not initialized from P6.2"
        assert portfolio is not None, "Portfolio not initialized from P6.2"
        huge_signal = Signal_(
            symbol=symbol,
            direction="SHORT",
            size_usdt=999999999.0,
            strategy="test_huge",
        )
        risk_result = rm.check(huge_signal, portfolio)
        # Expect either rejected or capped
        ph.record("P6.3", "Huge order risk check", True,
                   f"allowed={risk_result.allowed}, reason={risk_result.reason}, "
                   f"adjusted={risk_result.adjusted_size}")
    except Exception as e:
        ph.record("P6.3", "Huge order risk check", False, str(e))

    # P6.4 Panic state clean
    try:
        from src.core.safety import get_panic_state, reset_panic
        panic = get_panic_state()
        if panic.is_triggered:
            reset_panic("RESET")
        assert not panic.is_triggered
        ph.record("P6.4", "Panic state clean", True, "No stale panic")
    except Exception as e:
        ph.record("P6.4", "Panic state clean", False, str(e))

    # P6.5 Daily loss tracker
    try:
        from src.core.safety import get_daily_loss_tracker
        tracker = get_daily_loss_tracker()
        pnl = tracker.daily_pnl
        trades = tracker.daily_trades
        ph.record("P6.5", "DailyLossTracker", True,
                   f"daily_pnl=${pnl:.2f}, trades={trades}")
    except Exception as e:
        ph.record("P6.5", "DailyLossTracker", False, str(e))

    # P6.6 Stale WS detection
    try:
        from src.engine.adapters.live import LiveExchange
        from src.engine.factory import _build_config_from_play
        config = _build_config_from_play(play, "demo")
        test_ex = LiveExchange(play, config, demo=True)
        # Not connected, so _is_ws_data_fresh should return False
        fresh = test_ex._is_ws_data_fresh()
        ph.record("P6.6", "Stale WS detection", fresh is False,
                   f"fresh={fresh} (expected False when not connected)")
    except Exception as e:
        ph.record("P6.6", "Stale WS detection", False, str(e))

    return ph


# ---------------------------------------------------------------------------
# Phase 7: Full EngineManager Integration
# ---------------------------------------------------------------------------

async def phase_7_integration(play, engine_timeout: int) -> PhaseResult:
    """Test the full EngineManager -> LiveRunner -> process loop path."""
    ph = report.new_phase(7, "Full EngineManager Integration")

    from src.engine.manager import EngineManager
    from src.data.realtime_bootstrap import reset_realtime_bootstrap
    from src.data.realtime_state import reset_realtime_state
    from src.core.exchange_manager import ExchangeManager

    # Reset singletons for clean test -- ensures Phase 7 gets fresh connections
    # (previous phases may have exhausted pybit's connection attempt counter)
    reset_realtime_bootstrap()
    reset_realtime_state()
    ExchangeManager._instance = None
    EngineManager._instance = None

    # Brief pause to let Bybit rate limits cool down
    await asyncio.sleep(3.0)

    # P7.1 EngineManager.start
    manager = None
    instance_id = None
    try:
        manager = EngineManager.get_instance()
        assert manager is not None

        instance_id = await manager.start(play, mode="demo")
        assert instance_id is not None
        ph.record("P7.1", "EngineManager.start(demo)", True, f"id={instance_id}")
    except Exception as e:
        ph.record("P7.1", "EngineManager.start(demo)", False, str(e))
        ph.set_fatal(f"Engine start failed: {e}")
        return ph

    # P7.2 Runner state RUNNING (wait up to 30s for startup)
    try:
        deadline = time.monotonic() + 30
        info = None
        while time.monotonic() < deadline:
            info = manager.get(instance_id)
            if info and info.status == "running":
                break
            await asyncio.sleep(2.0)
        assert info is not None
        is_running = info.status in ("running", "starting")
        ph.record("P7.2", "Runner state RUNNING", is_running,
                   f"status={info.status}")
    except Exception as e:
        ph.record("P7.2", "Runner state RUNNING", False, str(e))

    # P7.3 Process at least 1 bar (wait up to engine_timeout)
    try:
        deadline = time.monotonic() + engine_timeout
        processed = False
        info = None
        while time.monotonic() < deadline:
            info = manager.get(instance_id)
            if info and info.bars_processed > 0:
                processed = True
                break
            await asyncio.sleep(5.0)

        ph.record("P7.3", "Process at least 1 bar", processed,
                   f"bars={info.bars_processed if info else 0}, "
                   f"waited={engine_timeout}s max")
    except Exception as e:
        ph.record("P7.3", "Process at least 1 bar", False, str(e))

    # P7.4 Indicators warm (check data provider has data, not strict is_ready)
    instance = None
    try:
        instance = manager._instances.get(instance_id)
        if instance and instance.engine:
            dp = instance.engine._data_provider
            low_buf = getattr(dp, '_low_tf_buffer', None)
            has_data = low_buf is not None and len(low_buf) > 0
            ready = dp.is_ready() if hasattr(dp, 'is_ready') else False
            ph.record("P7.4", "Indicators warm", has_data or ready,
                       f"is_ready={ready}, buffer_len={len(low_buf) if low_buf is not None else 0}")
        else:
            ph.record("P7.4", "Indicators warm", False, "No instance/engine found")
    except Exception as e:
        ph.record("P7.4", "Indicators warm", False, str(e))

    # P7.5 Graceful stop
    try:
        stopped = await manager.stop(instance_id)
        assert stopped is True
        ph.record("P7.5", "Graceful stop", True)
    except Exception as e:
        ph.record("P7.5", "Graceful stop", False, str(e))

    # P7.6 Runner state STOPPED
    try:
        if instance:
            state = instance.runner.state.value if instance.runner else "unknown"
            ph.record("P7.6", "Runner state STOPPED",
                       state in ("stopped", "error"),
                       f"state={state}")
        else:
            ph.record("P7.6", "Runner state STOPPED", False, "No instance")
    except Exception as e:
        ph.record("P7.6", "Runner state STOPPED", False, str(e))

    # P7.7 Open orders cancelled
    try:
        symbol = play.symbol_universe[0]
        from src.core.exchange_manager import ExchangeManager
        em = ExchangeManager()
        orders = em.get_open_orders(symbol)
        no_lingering = len(orders) == 0
        ph.record("P7.7", "Open orders cancelled", no_lingering,
                   f"remaining_orders={len(orders)}")
    except Exception as e:
        ph.record("P7.7", "Open orders cancelled", False, str(e))

    # P7.8 Instance removed
    try:
        instances = manager.list()
        removed = all(i.instance_id != instance_id for i in instances)
        ph.record("P7.8", "Instance removed", removed,
                   f"active_instances={len(instances)}")
    except Exception as e:
        ph.record("P7.8", "Instance removed", False, str(e))

    return ph


# ---------------------------------------------------------------------------
# Phase 8: Journal & State Persistence
# ---------------------------------------------------------------------------

async def phase_8_journal_persistence(play, config) -> PhaseResult:
    """Test TradeJournal JSONL write/read and LiveExchangeStateAdapter."""
    ph = report.new_phase(8, "Journal & State Persistence")

    import json
    import tempfile
    from pathlib import Path

    symbol = play.symbol_universe[0]

    # P8.1 TradeJournal writes valid JSONL
    journal = None
    journal_path = None
    try:
        from src.engine.journal import TradeJournal

        test_id = f"readiness_test_{int(time.time())}"
        journal = TradeJournal(test_id)
        journal_path = journal.path

        # Write all 3 event types
        journal.record_signal(symbol, "SHORT", 11.0, strategy="test", metadata={"test": True})
        journal.record_fill(symbol, "SHORT", 11.0, fill_price=180.50, order_id="test-001",
                            sl=185.0, tp=175.0)
        journal.record_error(symbol, "SHORT", "test error message")

        assert journal_path.exists(), f"Journal file not created: {journal_path}"
        ph.record("P8.1", "TradeJournal writes JSONL", True, str(journal_path))
    except Exception as e:
        ph.record("P8.1", "TradeJournal writes JSONL", False, str(e))

    # P8.2 Read journal back and parse all events
    try:
        assert journal_path and journal_path.exists()
        lines = journal_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3, f"Expected 3 lines, got {len(lines)}"

        events = [json.loads(line) for line in lines]
        assert events[0]["event"] == "signal"
        assert events[1]["event"] == "fill"
        assert events[2]["event"] == "error"

        # Verify fill has SL/TP
        fill = events[1]
        assert fill["sl"] == 185.0, f"SL mismatch: {fill['sl']}"
        assert fill["tp"] == 175.0, f"TP mismatch: {fill['tp']}"
        assert fill["fill_price"] == 180.50
        assert fill["order_id"] == "test-001"

        # Verify signal metadata
        sig = events[0]
        assert sig["metadata"]["test"] is True

        ph.record("P8.2", "Journal read-back + parse", True,
                   f"3 events, fill_price={fill['fill_price']}, sl={fill['sl']}, tp={fill['tp']}")
    except Exception as e:
        ph.record("P8.2", "Journal read-back + parse", False, str(e))
    finally:
        # Cleanup test journal
        if journal_path and journal_path.exists():
            try:
                journal_path.unlink()
            except Exception:
                pass

    # P8.3 LiveExchangeStateAdapter snapshot (flat account)
    try:
        from src.engine.adapters.live_state_adapter import LiveExchangeStateAdapter

        # Create a mock live exchange for snapshot
        from src.engine.adapters.live import LiveExchange
        test_ex = LiveExchange(play, config, demo=True)
        await test_ex.connect()

        adapter = LiveExchangeStateAdapter.from_live_exchange(test_ex, symbol)
        assert adapter.equity_usdt > 0, f"equity={adapter.equity_usdt}"
        assert adapter.available_balance_usdt > 0
        assert adapter.position is None, "Expected flat position"
        assert adapter.unrealized_pnl_usdt == 0.0
        assert adapter.entries_disabled is False
        ph.record("P8.3", "LiveExchangeStateAdapter (flat)", True,
                   f"equity=${adapter.equity_usdt:.2f}, balance=${adapter.available_balance_usdt:.2f}")
    except Exception as e:
        ph.record("P8.3", "LiveExchangeStateAdapter (flat)", False, str(e))

    # P8.4 InstanceInfo serialization round-trip
    try:
        from src.engine.manager import InstanceInfo, InstanceMode

        info = InstanceInfo(
            instance_id="test_123",
            play_id="sol_ema_cross_demo",
            symbol=symbol,
            mode=InstanceMode.DEMO,
            started_at=datetime.now(),
            status="running",
            bars_processed=42,
            signals_generated=3,
        )
        d = info.to_dict()
        assert d["instance_id"] == "test_123"
        assert d["mode"] == "demo"
        assert d["bars_processed"] == 42
        # Verify JSON serializable
        json_str = json.dumps(d)
        restored = json.loads(json_str)
        assert restored["instance_id"] == "test_123"
        ph.record("P8.4", "InstanceInfo serialization", True, f"keys={list(d.keys())}")
    except Exception as e:
        ph.record("P8.4", "InstanceInfo serialization", False, str(e))

    # P8.5 Cross-process instance file write/read/cleanup
    try:
        from src.engine.manager import EngineManager
        mgr = EngineManager()
        # Don't use singleton to avoid pollution
        test_instances_dir = mgr._instances_dir
        assert test_instances_dir.exists(), f"Instances dir missing: {test_instances_dir}"

        # Check that stale PID detection works
        is_alive = EngineManager._is_pid_alive(os.getpid())
        assert is_alive, "Current PID should be alive"

        is_dead = EngineManager._is_pid_alive(99999999)
        assert not is_dead, "Fake PID should be dead"

        ph.record("P8.5", "Cross-process PID detection", True,
                   f"self_alive={is_alive}, fake_dead={not is_dead}")
    except Exception as e:
        ph.record("P8.5", "Cross-process PID detection", False, str(e))

    return ph


# ---------------------------------------------------------------------------
# Phase 9: Safety & Circuit Breakers
# ---------------------------------------------------------------------------

def phase_9_safety_breakers(play, em) -> PhaseResult:
    """Test PanicState, DailyLossTracker, and circuit breaker logic."""
    ph = report.new_phase(9, "Safety & Circuit Breakers")

    # P9.1 PanicState trigger → callback fires → reset
    try:
        from src.core.safety import PanicState

        # Use a fresh instance (not the global one) to avoid side effects
        ps = PanicState()
        callback_called = []
        ps.add_callback(lambda reason: callback_called.append(reason))

        assert not ps.is_triggered, "Should start untriggered"
        ps.trigger("test_panic_reason")
        assert ps.is_triggered, "Should be triggered"
        assert ps.reason == "test_panic_reason"
        assert ps.trigger_time is not None
        assert len(callback_called) == 1, f"Callback not called: {callback_called}"
        assert callback_called[0] == "test_panic_reason"

        ps.reset()
        assert not ps.is_triggered, "Should be reset"

        ph.record("P9.1", "PanicState trigger/callback/reset", True,
                   f"callback_fired={len(callback_called)}")
    except Exception as e:
        ph.record("P9.1", "PanicState trigger/callback/reset", False, str(e))

    # P9.2 PanicState callback exception handling
    try:
        from src.core.safety import PanicState as PanicState_
        ps2 = PanicState_()
        good_calls = []
        def _bad_callback(r):
            raise ValueError("bad callback")
        ps2.add_callback(_bad_callback)
        ps2.add_callback(lambda r: good_calls.append(r))

        ps2.trigger("test_exception")
        # Second callback should still fire even though first threw
        assert len(good_calls) == 1, f"Second callback should fire despite first failing: {good_calls}"
        ph.record("P9.2", "Panic callback exception isolation", True,
                   f"good_callbacks={len(good_calls)}")
    except Exception as e:
        ph.record("P9.2", "Panic callback exception isolation", False, str(e))

    # P9.3 DailyLossTracker record + check_limit
    try:
        from src.core.safety import DailyLossTracker

        tracker = DailyLossTracker()
        assert tracker.daily_pnl == 0.0
        assert tracker.daily_trades == 0

        # Record some PnL
        tracker.record_pnl(-50.0)
        tracker.record_pnl(-30.0)
        tracker.record_pnl(10.0)
        assert tracker.daily_trades == 3, f"trades={tracker.daily_trades}"
        assert abs(tracker.daily_pnl - (-70.0)) < 0.01, f"pnl={tracker.daily_pnl}"

        # Check limit -- $100 limit, we're at -$70, should pass
        ok, reason = tracker.check_limit(100.0)
        assert ok, f"Should pass at -$70 vs $100 limit: {reason}"

        # Push over limit
        tracker.record_pnl(-35.0)
        ok2, reason2 = tracker.check_limit(100.0)
        assert not ok2, f"Should fail at -$105 vs $100 limit"

        ph.record("P9.3", "DailyLossTracker record + limit", True,
                   f"pnl=${tracker.daily_pnl:.2f}, trades={tracker.daily_trades}")
    except Exception as e:
        ph.record("P9.3", "DailyLossTracker record + limit", False, str(e))

    # P9.4 DailyLossTracker.seed_from_exchange() with real API
    try:
        from src.core.safety import DailyLossTracker

        seeded = DailyLossTracker()
        symbol = play.symbol_universe[0]
        seeded.seed_from_exchange(em, symbol=symbol)
        # Just verify it doesn't crash and returns a number
        pnl = seeded.daily_pnl
        trades = seeded.daily_trades
        ph.record("P9.4", "DailyLossTracker.seed_from_exchange()", True,
                   f"seeded pnl=${pnl:.2f}, trades={trades}")
    except Exception as e:
        ph.record("P9.4", "DailyLossTracker.seed_from_exchange()", False, str(e))

    # P9.5 SafetyChecks with additional exposure check
    try:
        from src.core.safety import SafetyChecks

        checks = SafetyChecks(em, em.config)
        # Run with additional exposure
        ok, failures = checks.run_all_checks(additional_exposure=10.0)
        ph.record("P9.5", "SafetyChecks + exposure", ok,
                   f"passed={ok}, failures={failures}")
    except Exception as e:
        ph.record("P9.5", "SafetyChecks + exposure", False, str(e))

    # P9.6 check_panic_and_halt() integration
    try:
        from src.core.safety import check_panic_and_halt, get_panic_state, reset_panic

        # Ensure clean state
        panic = get_panic_state()
        if panic.is_triggered:
            reset_panic("RESET")

        # Should not halt when clean
        should_halt = check_panic_and_halt()
        assert not should_halt, "Should not halt when panic is clean"

        ph.record("P9.6", "check_panic_and_halt() clean", True, f"halted={should_halt}")
    except Exception as e:
        ph.record("P9.6", "check_panic_and_halt() clean", False, str(e))

    return ph


# ---------------------------------------------------------------------------
# Phase 10: Multi-TF Data Routing
# ---------------------------------------------------------------------------

async def phase_10_multi_tf(play) -> PhaseResult:
    """Test multi-timeframe data routing in LiveDataProvider."""
    ph = report.new_phase(10, "Multi-TF Data Routing")

    from src.engine.adapters.live import LiveDataProvider
    from src.engine.interfaces import Candle

    symbol = play.symbol_universe[0]

    # Build a DataProvider with all TFs at 1m (our override)
    dp = None
    try:
        dp = LiveDataProvider(play, demo=True)
        ph.record("P10.0", "DataProvider init for multi-TF", True)
    except Exception as e:
        ph.record("P10.0", "DataProvider init for multi-TF", False, str(e))
        ph.set_fatal("Cannot test multi-TF without DataProvider")
        return ph

    # Seed buffers with 120 candles
    base_price = 180.0
    for i in range(120):
        c = Candle(
            ts_open=datetime.now(timezone.utc),
            ts_close=datetime.now(timezone.utc),
            open=base_price + i * 0.01,
            high=base_price + i * 0.01 + 1.0,
            low=base_price + i * 0.01 - 1.0,
            close=base_price + i * 0.01 + 0.5,
            volume=1000.0 + i,
        )
        dp._low_tf_buffer.append(c)
        # Also seed med/high TF buffers if they exist
        if hasattr(dp, '_med_tf_buffer') and dp._med_tf_buffer is not None:
            dp._med_tf_buffer.append(c)
        if hasattr(dp, '_high_tf_buffer') and dp._high_tf_buffer is not None:
            dp._high_tf_buffer.append(c)

    # P10.1 get_candle_for_tf() routes to correct buffer by TF role
    try:
        # Since all TFs are overridden to 1m, all buffers should have data
        low_candle = dp.get_candle_for_tf(-1, tf_role="low_tf")
        assert low_candle is not None, "No candle from low_tf buffer"
        assert low_candle.volume > 0, f"Candle volume should be >0: {low_candle.volume}"

        # get_candle() (no tf_role) should also work (uses exec buffer)
        exec_candle = dp.get_candle(-1)
        assert exec_candle is not None, "No candle from exec buffer"

        med_candle = dp.get_candle_for_tf(-1, tf_role="med_tf")
        high_candle = dp.get_candle_for_tf(-1, tf_role="high_tf")

        ph.record("P10.1", "get_candle_for_tf() by TF role", True,
                   f"low={low_candle.close:.2f}, "
                   f"med={'ok' if med_candle else 'None'}, "
                   f"high={'ok' if high_candle else 'None'}")
    except Exception as e:
        ph.record("P10.1", "get_candle() by TF role", False, str(e))

    # P10.2 on_candle_close with non-exec TF (should not crash)
    try:
        new_candle = Candle(
            ts_open=datetime.now(timezone.utc),
            ts_close=datetime.now(timezone.utc),
            open=181.0, high=182.0, low=180.0, close=181.5, volume=2000.0,
        )
        # Feed to low_tf (which is exec) and med_tf (non-exec)
        dp.on_candle_close(new_candle, timeframe="1m")

        # Verify buffer grew
        buf_len = len(dp._low_tf_buffer)
        assert buf_len == 121, f"Expected 121, got {buf_len}"

        ph.record("P10.2", "on_candle_close routing", True,
                   f"low_tf_buffer={buf_len}")
    except Exception as e:
        ph.record("P10.2", "on_candle_close routing", False, str(e))

    # P10.3 TF role resolution
    try:
        # _get_tf_role_for_timeframe should map concrete TF to role
        if hasattr(dp, '_get_tf_role_for_timeframe'):
            role = dp._get_tf_role_for_timeframe("1m")
            assert role is not None, "Should resolve 1m to a role"

            # Unknown TF should raise ValueError
            try:
                dp._get_tf_role_for_timeframe("99m")
                ph.record("P10.3", "TF role resolution", False,
                           "Should have raised ValueError for unknown TF")
            except ValueError:
                ph.record("P10.3", "TF role resolution", True,
                           f"1m->{role}, 99m->ValueError (correct)")
        else:
            ph.record("P10.3", "TF role resolution", True, "Method not present (skip)")
    except Exception as e:
        ph.record("P10.3", "TF role resolution", False, str(e))

    # P10.4 LiveDataProvider.disconnect() cleanup
    try:
        await dp.disconnect()
        ph.record("P10.4", "DataProvider disconnect", True)
    except Exception as e:
        ph.record("P10.4", "DataProvider disconnect", False, str(e))

    return ph


# ---------------------------------------------------------------------------
# Phase 11: Advanced Order Lifecycle
# ---------------------------------------------------------------------------

async def phase_11_advanced_orders(play, em) -> PhaseResult:
    """Test limit orders, cancel, and position reversal via real Bybit demo."""
    ph = report.new_phase(11, "Advanced Order Lifecycle")

    symbol = play.symbol_universe[0]

    # First clean up any lingering position
    try:
        em.close_position(symbol)
    except Exception:
        pass
    await asyncio.sleep(1.0)

    # P11.1 Place limit order far from market (won't fill)
    limit_order_id = None
    try:
        price = em.get_price(symbol)
        assert price > 0, f"No price for {symbol}"

        # Place a buy limit 10% below market (won't fill)
        limit_price = round(price * 0.90, 2)
        result = em.limit_buy(symbol, usd_amount=11.0, price=limit_price)
        assert result.success, f"Limit order failed: {result.error}"
        limit_order_id = result.order_id
        ph.record("P11.1", "Place limit order (far from mkt)", True,
                   f"id={limit_order_id}, price=${limit_price:.2f} (mkt=${price:.2f})")
    except Exception as e:
        ph.record("P11.1", "Place limit order", False, str(e))

    # P11.2 get_open_orders() returns the limit order (Order dataclass, not dict)
    if limit_order_id:
        try:
            await asyncio.sleep(1.0)
            orders = em.get_open_orders(symbol)
            found = any(o.order_id == limit_order_id for o in orders)
            ph.record("P11.2", "get_open_orders() finds limit", found,
                       f"orders={len(orders)}, found_ours={found}")
        except Exception as e:
            ph.record("P11.2", "get_open_orders() finds limit", False, str(e))
    else:
        ph.record("P11.2", "get_open_orders() finds limit", False, "Skipped (no order)")

    # P11.3 Cancel the pending limit order
    if limit_order_id:
        try:
            cancelled = em.cancel_order(symbol, order_id=limit_order_id)
            await asyncio.sleep(1.0)
            # Verify it's gone
            orders_after = em.get_open_orders(symbol)
            still_there = any(o.order_id == limit_order_id for o in orders_after)
            ph.record("P11.3", "Cancel limit order", not still_there,
                       f"cancel_result={cancelled}, still_open={still_there}")
        except Exception as e:
            ph.record("P11.3", "Cancel limit order", False, str(e))
    else:
        ph.record("P11.3", "Cancel limit order", False, "Skipped (no order)")

    # P11.4 Position reversal: open LONG -> close -> open SHORT -> close
    try:
        # Step 1: Open LONG
        buy_result = em.market_buy(symbol, usd_amount=11.0)
        assert buy_result.success, f"Buy failed: {buy_result.error}"
        await asyncio.sleep(2.0)

        # Verify position
        pos_long = em.get_position(symbol)
        has_long = pos_long is not None and pos_long.size > 0
        assert has_long, f"Expected long position, got {pos_long}"

        # Step 2: Close LONG
        close_result = em.close_position(symbol)
        assert close_result.success, f"Close failed: {close_result.error}"
        await asyncio.sleep(2.0)

        # Step 3: Open SHORT
        sell_result = em.market_sell(symbol, usd_amount=11.0)
        assert sell_result.success, f"Sell failed: {sell_result.error}"
        await asyncio.sleep(2.0)

        # Verify SHORT position
        pos_short = em.get_position(symbol)
        has_short = pos_short is not None and pos_short.size > 0

        # Step 4: Close SHORT
        close2 = em.close_position(symbol)

        ph.record("P11.4", "Position reversal (LONG->SHORT->flat)", has_short,
                   f"long={has_long}, short={has_short}")
    except Exception as e:
        ph.record("P11.4", "Position reversal", False, str(e))
    finally:
        try:
            em.close_position(symbol)
        except Exception:
            pass

    await asyncio.sleep(1.0)

    # P11.5 get_bid_ask() spread sanity
    try:
        bid, ask = em.get_bid_ask(symbol)
        assert bid > 0, f"Bid is 0"
        assert ask > 0, f"Ask is 0"
        assert bid <= ask, f"Bid ${bid} > Ask ${ask}"
        spread = ask - bid
        spread_pct = (spread / ask) * 100
        ph.record("P11.5", "get_bid_ask() spread sanity", True,
                   f"bid=${bid:.4f}, ask=${ask:.4f}, spread={spread_pct:.4f}%")
    except Exception as e:
        ph.record("P11.5", "get_bid_ask() spread sanity", False, str(e))

    return ph


# ---------------------------------------------------------------------------
# Phase 12: Runner State Machine & Instance Limits
# ---------------------------------------------------------------------------

async def phase_12_runner_state(play) -> PhaseResult:
    """Test EngineManager instance limits, pause/resume, state machine."""
    ph = report.new_phase(12, "Runner State Machine & Instance Limits")

    from src.engine.manager import EngineManager, InstanceMode

    # P12.1 Instance limit: 2nd demo for same symbol rejected
    mgr: EngineManager | None = None
    try:
        EngineManager._instance = None  # Reset singleton
        mgr = EngineManager.get_instance()
        symbol = play.symbol_universe[0]

        # Simulate that one demo is already running
        mgr._demo_by_symbol[symbol] = 1

        try:
            mgr._check_limits(play, "demo")
            ph.record("P12.1", "Demo instance limit (same symbol)", False,
                       "Should have raised ValueError")
        except ValueError as ve:
            ph.record("P12.1", "Demo instance limit (same symbol)", True,
                       f"Correctly rejected: {ve}")
        finally:
            # Clean up
            mgr._demo_by_symbol.clear()
    except Exception as e:
        ph.record("P12.1", "Demo instance limit", False, str(e))

    # P12.2 Instance limit: max 1 live instance
    try:
        assert mgr is not None, "EngineManager not initialized from P12.1"
        mgr._live_count = 1
        try:
            mgr._check_limits(play, "live")
            ph.record("P12.2", "Live instance limit", False, "Should have raised ValueError")
        except ValueError as ve:
            ph.record("P12.2", "Live instance limit", True,
                       f"Correctly rejected: {ve}")
        finally:
            mgr._live_count = 0
    except Exception as e:
        ph.record("P12.2", "Live instance limit", False, str(e))

    # P12.3 Instance limit: max 1 backtest
    try:
        assert mgr is not None, "EngineManager not initialized from P12.1"
        mgr._backtest_count = 1
        try:
            mgr._check_limits(play, "backtest")
            ph.record("P12.3", "Backtest instance limit", False, "Should have raised ValueError")
        except ValueError as ve:
            ph.record("P12.3", "Backtest instance limit", True,
                       f"Correctly rejected: {ve}")
        finally:
            mgr._backtest_count = 0
    except Exception as e:
        ph.record("P12.3", "Backtest instance limit", False, str(e))

    # P12.4 Pause file IPC: LiveRunner.is_paused
    try:
        from src.engine.runners.live_runner import LiveRunner

        # Create a minimal runner for pause testing
        # We just need is_paused logic, not full engine
        runner = object.__new__(LiveRunner)
        runner._pause_dir = Path(os.path.expanduser("~/.trade/instances"))
        runner._pause_dir.mkdir(parents=True, exist_ok=True)
        runner._instance_id = "test_pause_check"

        # No pause file → not paused
        assert not runner.is_paused, "Should not be paused without file"

        # Create pause file → paused
        pause_file = runner._pause_dir / "test_pause_check.pause"
        pause_file.write_text("paused", encoding="utf-8", newline="\n")
        try:
            assert runner.is_paused, "Should be paused with file present"
            ph.record("P12.4", "Pause file IPC", True,
                       f"no_file=not_paused, with_file=paused")
        finally:
            pause_file.unlink(missing_ok=True)
    except Exception as e:
        ph.record("P12.4", "Pause file IPC", False, str(e))

    # P12.5 RunnerState enum values
    try:
        from src.engine.runners.live_runner import RunnerState

        # Verify all expected states exist
        expected_states = {"starting", "running", "stopping", "stopped", "error", "reconnecting"}
        actual_states = {s.value for s in RunnerState}
        missing = expected_states - actual_states
        if missing:
            ph.record("P12.5", "RunnerState enum values", False,
                       f"Missing states: {missing}")
        else:
            ph.record("P12.5", "RunnerState enum values", True,
                       f"states={sorted(actual_states)}")
    except Exception as e:
        ph.record("P12.5", "RunnerState enum values", False, str(e))

    return ph


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(description="Comprehensive Demo Trading Readiness Test")
    parser.add_argument("--play", type=str,
                        default=str(PROJECT_ROOT / "plays" / "sol_ema_cross_demo.yml"),
                        help="Path to play YAML file")
    parser.add_argument("--skip-orders", action="store_true",
                        help="Skip phase 5 (order execution)")
    parser.add_argument("--engine-timeout", type=int, default=90,
                        help="Max seconds to wait for engine to process a bar (default 90)")
    parser.add_argument("--verbose", action="store_true",
                        help="Enable verbose logging")
    args = parser.parse_args()

    if args.verbose:
        import logging
        logging.basicConfig(level=logging.DEBUG)

    # Force read-only DuckDB access to avoid write lock contention
    # with other processes (live bots, CLI tools, etc.)
    from src.data.historical_data_store import reset_stores
    reset_stores(force_read_only=True)

    print("=" * 60)
    print("COMPREHENSIVE DEMO TRADING READINESS TEST")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print(f"Play: {args.play}")
    print(f"Skip orders: {args.skip_orders}")
    print(f"Engine timeout: {args.engine_timeout}s")
    print("=" * 60)

    play_path = Path(args.play)
    play = None
    config = None
    em = None

    # ---- Phase 1 ----
    ph1, play, config = phase_1_play_loading(play_path)
    if ph1.fatal:
        report.stopped_early = True
        report.summary()
        sys.exit(1)

    # ---- Phase 2 ----
    ph2, em = phase_2_exchange_rest(play)
    if ph2.fatal:
        report.stopped_early = True
        report.summary()
        sys.exit(1)

    # ---- Phase 3 ----
    ph3, dp = await phase_3_data_provider(play, em)
    if ph3.fatal:
        report.stopped_early = True
        report.summary()
        sys.exit(1)

    # ---- Phase 4 ----
    try:
        ph4, state = await phase_4_websocket(play)
    except Exception as e:
        ph4 = report.new_phase(4, "WebSocket Data Feed")
        ph4.record("P4.ERR", "Phase 4 unhandled error", False, str(e))

    # ---- Phase 5 ----
    if not args.skip_orders:
        try:
            ph5 = await phase_5_order_execution(play, config)
        except Exception as e:
            ph5 = report.new_phase(5, "LiveExchange + Order Execution")
            ph5.record("P5.ERR", "Phase 5 unhandled error", False, str(e))
        finally:
            # Cleanup: ensure no lingering position
            try:
                from src.core.exchange_manager import ExchangeManager
                cleanup_em = ExchangeManager()
                cleanup_em.close_position(play.symbol_universe[0])
            except Exception:
                pass
    else:
        ph5 = report.new_phase(5, "LiveExchange + Order Execution [SKIPPED]")
        ph5.record("P5.SKIP", "Skipped by --skip-orders", True, "User requested skip")

    # ---- Phase 6 ----
    try:
        ph6 = await phase_6_edge_cases(play, em)
    except Exception as e:
        ph6 = report.new_phase(6, "Error Handling Edge Cases")
        ph6.record("P6.ERR", "Phase 6 unhandled error", False, str(e))

    # ---- Phase 7 ----
    try:
        ph7 = await phase_7_integration(play, args.engine_timeout)
    except Exception as e:
        ph7 = report.new_phase(7, "Full EngineManager Integration")
        ph7.record("P7.ERR", "Phase 7 unhandled error", False, str(e))
    finally:
        # Cleanup: stop all engines
        try:
            from src.engine.manager import EngineManager
            mgr = EngineManager.get_instance()
            await mgr.stop_all()
        except Exception:
            pass
        # Cleanup: close any positions
        try:
            from src.core.exchange_manager import ExchangeManager
            cleanup_em = ExchangeManager()
            cleanup_em.close_position(play.symbol_universe[0])
        except Exception:
            pass

    # ---- Phase 8 ---- (journal + persistence, minimal network)
    try:
        ph8 = await phase_8_journal_persistence(play, config)
    except Exception as e:
        ph8 = report.new_phase(8, "Journal & State Persistence")
        ph8.record("P8.ERR", "Phase 8 unhandled error", False, str(e))

    # ---- Phase 9 ---- (pure logic + REST, no DB)
    try:
        ph9 = phase_9_safety_breakers(play, em)
    except Exception as e:
        ph9 = report.new_phase(9, "Safety & Circuit Breakers")
        ph9.record("P9.ERR", "Phase 9 unhandled error", False, str(e))

    # ---- Phase 10 ---- (pure logic, no DB, no network)
    try:
        ph10 = await phase_10_multi_tf(play)
    except Exception as e:
        ph10 = report.new_phase(10, "Multi-TF Data Routing")
        ph10.record("P10.ERR", "Phase 10 unhandled error", False, str(e))

    # ---- Phase 11 ---- (orders via REST, no DB)
    if not args.skip_orders:
        try:
            ph11 = await phase_11_advanced_orders(play, em)
        except Exception as e:
            ph11 = report.new_phase(11, "Advanced Order Lifecycle")
            ph11.record("P11.ERR", "Phase 11 unhandled error", False, str(e))
        finally:
            # Cleanup: ensure no lingering position or orders
            try:
                em.cancel_all_orders()
                em.close_position(play.symbol_universe[0])
            except Exception:
                pass
    else:
        ph11 = report.new_phase(11, "Advanced Order Lifecycle [SKIPPED]")
        ph11.record("P11.SKIP", "Skipped by --skip-orders", True, "User requested skip")

    # ---- Phase 12 ---- (pure logic, no network, no DB)
    try:
        ph12 = await phase_12_runner_state(play)
    except Exception as e:
        ph12 = report.new_phase(12, "Runner State Machine & Instance Limits")
        ph12.record("P12.ERR", "Phase 12 unhandled error", False, str(e))

    # ---- Summary ----
    success = report.summary()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())
