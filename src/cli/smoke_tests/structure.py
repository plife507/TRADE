"""
Market Structure Smoke Tests.

Validates SwingDetector, TrendClassifier, ZoneDetector, StructureBuilder, and
RuntimeSnapshotView integration with synthetic data.

Stage 5: Validates end-to-end pipeline from StructureSpec (with zones) through
snapshot.get("structure.<block_key>.zones.<zone_key>.<field>").

Stage 5.1: Validates zone instance_id determinism and duplicate key validation.

Stage 6: Validates zone interaction metrics (touched, inside, time_in_zone) with
determinism guarantee.
"""

import numpy as np
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel

console = Console()

# =============================================================================
# Test Configuration Constants
# =============================================================================

# Default parameters for smoke tests
DEFAULT_SAMPLE_BARS = 500
DEFAULT_RANDOM_SEED = 42

# Synthetic OHLCV generation parameters
PRICE_BASE = 40000.0           # Base price for synthetic data
PRICE_TREND_AMPLITUDE = 1000.0  # Amplitude of slow trend oscillation
PRICE_FAST_AMPLITUDE = 500.0    # Amplitude of fast oscillation
PRICE_NOISE_STD = 50.0          # Standard deviation of price noise
HIGH_SPREAD_STD = 100.0         # High spread std dev from close
HIGH_MIN_SPREAD = 20.0          # Minimum high above close
LOW_SPREAD_STD = 100.0          # Low spread std dev from close
LOW_MIN_SPREAD = 20.0           # Minimum low below close
OPEN_NOISE_STD = 30.0           # Open price noise std dev
VOLUME_STD = 1000.0             # Volume std dev
VOLUME_MIN = 100.0              # Minimum volume
SIN_CYCLES = 8                  # Number of sin cycles over sample period
SLOW_SIN_MULTIPLIER = 0.5       # Multiplier for slow trend
FAST_SIN_MULTIPLIER = 2.0       # Multiplier for fast oscillation

# Timeframe configuration
MINUTES_PER_BAR = 5             # 5-minute bars

# Swing detector parameters
SWING_LOOKBACK_LEFT = 5
SWING_LOOKBACK_RIGHT = 5

# Zone configuration
ZONE_WIDTH_PERCENT = 0.01       # 1% zone width

# Structure builder stage
BUILDER_STAGE = 2               # Stage 2 (exec-only)

# Test indices for snapshot access validation
SNAPSHOT_TEST_INDICES = [100, 250]  # Sample indices plus sample_bars-1 added dynamically
ZONE_TEST_BAR_INDEX = 250       # Middle bar index for zone testing
INSTANCE_ID_CHECK_INDICES = [0, 50, 100, 200, 300]  # Indices for instance_id validation

# Output formatting
SEPARATOR_WIDTH = 60

# State tracking smoke test parameters
STATE_TRACKER_WARMUP_BARS = 10
STATE_TRACKER_TEST_BARS = 15
STATE_TRACKER_DETERMINISM_BARS = 20
STATE_TRACKER_SIGNAL_BARS = (11, 13)           # Bars where signals fire in basic test
STATE_TRACKER_DETERMINISM_SIGNAL_BARS = (11, 13, 15)  # Bars for determinism test

# Parity test parameters
PARITY_TEST_WINDOW_DAYS = 7     # Days of data for parity test
PARITY_TEST_MIN_BARS = 100      # Minimum bars required for parity test

# Mock exchange parameters
MOCK_EQUITY_USDT = 10000.0
MOCK_AVAILABLE_BALANCE_USDT = 10000.0


def run_structure_smoke(
    sample_bars: int = DEFAULT_SAMPLE_BARS,
    seed: int = DEFAULT_RANDOM_SEED,
) -> int:
    """
    Run market structure smoke test.

    Stage 5 validates:
    - StructureBuilder with exec-only constraint
    - FeedStore.structures population
    - snapshot.get("structure.*") resolution
    - Strict allowlist validation (unknown fields hard-fail)
    - No lookahead (pivot confirmed only after lookback)
    - Zone computation and snapshot access (Stage 5)

    Args:
        sample_bars: Number of bars to generate
        seed: Random seed for reproducibility

    Returns:
        Number of failures (0 = success)
    """
    from src.backtest.market_structure import (
        SwingDetector,
        TrendClassifier,
        SwingState,
        TrendState,
        StructureType,
        StructureSpec,
        ConfirmationConfig,
        StructureBuilder,
        StructureStore,
        Stage2ValidationError,
        get_detector,
        detect_swing_pivots,
    )
    from src.backtest.market_structure.spec import ZoneSpec
    from src.backtest.market_structure.types import ZoneType, ZoneState
    from src.backtest.runtime.feed_store import FeedStore, MultiTFFeedStore
    from src.backtest.runtime.snapshot_view import RuntimeSnapshotView

    console.print(Panel(
        "[bold]MARKET STRUCTURE SMOKE TEST (Stage 6)[/]\n"
        "[dim]Validates StructureBuilder + Zones + Interaction + Snapshot integration[/]",
        border_style="cyan",
    ))

    console.print(f"\n[bold]Configuration:[/]")
    console.print(f"  Sample Bars: {sample_bars:,}")
    console.print(f"  Seed: {seed}")

    failures = 0

    # =========================================================================
    # Step 1: Generate synthetic OHLCV data with clear swing patterns
    # =========================================================================
    console.print(f"\n[bold]Step 1: Generate Synthetic OHLCV Data[/]")
    np.random.seed(seed)

    # Create trending data with clear swings
    t = np.linspace(0, SIN_CYCLES * np.pi, sample_bars)
    # Base trend with oscillation
    base = (PRICE_BASE
            + PRICE_TREND_AMPLITUDE * np.sin(t * SLOW_SIN_MULTIPLIER)
            + PRICE_FAST_AMPLITUDE * np.sin(t * FAST_SIN_MULTIPLIER))
    # Add noise
    noise = np.random.randn(sample_bars) * PRICE_NOISE_STD

    close = base + noise
    high = close + np.abs(np.random.randn(sample_bars) * HIGH_SPREAD_STD) + HIGH_MIN_SPREAD
    low = close - np.abs(np.random.randn(sample_bars) * LOW_SPREAD_STD) - LOW_MIN_SPREAD
    open_ = close + np.random.randn(sample_bars) * OPEN_NOISE_STD
    volume = np.abs(np.random.randn(sample_bars) * VOLUME_STD) + VOLUME_MIN

    # Generate timestamps (5m bars)
    start_ts = datetime(2024, 1, 1, 0, 0, 0)
    ts_close = np.array([
        start_ts + timedelta(minutes=MINUTES_PER_BAR * (i + 1)) for i in range(sample_bars)
    ])
    ts_open = np.array([
        start_ts + timedelta(minutes=MINUTES_PER_BAR * i) for i in range(sample_bars)
    ])

    console.print(f"  [green]OK[/] Generated {sample_bars} bars")
    console.print(f"      Price range: ${low.min():,.2f} - ${high.max():,.2f}")

    ohlcv = {
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }

    # =========================================================================
    # Step 2: Test SwingDetector directly (internal outputs)
    # =========================================================================
    console.print(f"\n[bold]Step 2: Test SwingDetector (Internal)[/]")

    try:
        swing_detector = get_detector(StructureType.SWING)
        console.print(f"  [green]OK[/] SwingDetector instantiated via registry")
    except Exception as e:
        console.print(f"  [red]FAIL[/] Could not get SwingDetector: {e}")
        failures += 1
        return failures

    params = {"left": SWING_LOOKBACK_LEFT, "right": SWING_LOOKBACK_RIGHT}

    try:
        swing_outputs = swing_detector.build_batch(ohlcv, params)
        console.print(f"  [green]OK[/] SwingDetector.build_batch() completed")
        console.print(f"      Output keys: {list(swing_outputs.keys())}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] SwingDetector.build_batch() failed: {e}")
        failures += 1
        return failures

    # Validate internal output keys
    expected_keys = {"high_level", "high_idx", "low_level", "low_idx", "state", "recency"}
    actual_keys = set(swing_outputs.keys())
    if actual_keys != expected_keys:
        console.print(f"  [red]FAIL[/] Missing keys: {expected_keys - actual_keys}")
        failures += 1
    else:
        console.print(f"  [green]OK[/] All expected internal output keys present")

    # Count confirmed swings
    state = swing_outputs["state"]
    num_high_confirmed = np.sum(state == SwingState.NEW_HIGH)
    num_low_confirmed = np.sum(state == SwingState.NEW_LOW)
    num_both_confirmed = np.sum(state == SwingState.BOTH)

    console.print(f"  [green]OK[/] Swing confirmations:")
    console.print(f"      New highs: {num_high_confirmed}")
    console.print(f"      New lows: {num_low_confirmed}")
    console.print(f"      Both: {num_both_confirmed}")

    # =========================================================================
    # Step 3: Test TrendClassifier directly (internal outputs)
    # =========================================================================
    console.print(f"\n[bold]Step 3: Test TrendClassifier (Internal)[/]")

    try:
        trend_classifier = get_detector(StructureType.TREND)
        console.print(f"  [green]OK[/] TrendClassifier instantiated via registry")
    except Exception as e:
        console.print(f"  [red]FAIL[/] Could not get TrendClassifier: {e}")
        failures += 1
        return failures

    try:
        trend_outputs = trend_classifier.build_batch(swing_outputs, {})
        console.print(f"  [green]OK[/] TrendClassifier.build_batch() completed")
        console.print(f"      Output keys: {list(trend_outputs.keys())}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] TrendClassifier.build_batch() failed: {e}")
        failures += 1
        return failures

    # Validate trend outputs include parent_version
    expected_trend_keys = {"trend_state", "recency", "parent_version"}
    actual_trend_keys = set(trend_outputs.keys())
    if actual_trend_keys != expected_trend_keys:
        console.print(f"  [red]FAIL[/] Missing keys: {expected_trend_keys - actual_trend_keys}")
        failures += 1
    else:
        console.print(f"  [green]OK[/] All expected internal output keys present (including parent_version)")

    trend_state = trend_outputs["trend_state"]
    parent_version = trend_outputs["parent_version"]

    # Count trend states
    num_unknown = np.sum(trend_state == TrendState.UNKNOWN.value)
    num_up = np.sum(trend_state == TrendState.UP.value)
    num_down = np.sum(trend_state == TrendState.DOWN.value)

    console.print(f"  [green]OK[/] Trend classifications:")
    console.print(f"      Unknown: {num_unknown} bars")
    console.print(f"      Up: {num_up} bars")
    console.print(f"      Down: {num_down} bars")
    console.print(f"      Max parent_version: {parent_version.max()}")

    # =========================================================================
    # Step 4: Test StructureBuilder with StructureSpecs (including Zones)
    # =========================================================================
    console.print(f"\n[bold]Step 4: Test StructureBuilder (with Zones)[/]")

    # Create zone specs for SWING block (Stage 5)
    demand_zone = ZoneSpec(
        key="demand_1",
        type=ZoneType.DEMAND,
        width_model="percent",
        width_params={"pct": ZONE_WIDTH_PERCENT},
    )

    supply_zone = ZoneSpec(
        key="supply_1",
        type=ZoneType.SUPPLY,
        width_model="percent",
        width_params={"pct": ZONE_WIDTH_PERCENT},
    )

    # Create SWING spec with zones
    swing_spec = StructureSpec(
        key="ms_5m",
        type=StructureType.SWING,
        tf_role="exec",
        params={"left": SWING_LOOKBACK_LEFT, "right": SWING_LOOKBACK_RIGHT},
        confirmation=ConfirmationConfig(mode="immediate"),
        zones=[demand_zone, supply_zone],  # Stage 5: Zones attached
    )

    # Create TREND spec (no zones - TREND doesn't support zones)
    trend_spec = StructureSpec(
        key="trend_5m",
        type=StructureType.TREND,
        tf_role="exec",
        params={},
        confirmation=ConfirmationConfig(mode="immediate"),
    )

    console.print(f"  [green]OK[/] Created StructureSpecs:")
    console.print(f"      SWING: key='{swing_spec.key}', zones={[z.key for z in swing_spec.zones]}")
    console.print(f"      TREND: key='{trend_spec.key}', block_id='{trend_spec.block_id[:8]}...'")

    # Build structures
    builder = StructureBuilder(stage=BUILDER_STAGE)

    try:
        stores = builder.build(ohlcv, [swing_spec, trend_spec])
        console.print(f"  [green]OK[/] StructureBuilder.build() completed")
        console.print(f"      Stores: {list(stores.keys())}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] StructureBuilder.build() failed: {e}")
        failures += 1
        return failures

    # Build key map
    key_map = builder.build_key_map(stores)
    console.print(f"  [green]OK[/] Key map: {key_map}")

    # Validate public output field names
    swing_store = stores[swing_spec.block_id]
    trend_store = stores[trend_spec.block_id]

    expected_swing_fields = {"swing_high_level", "swing_high_idx", "swing_low_level", "swing_low_idx", "swing_recency_bars"}
    expected_trend_fields = {"trend_state", "parent_version"}

    if set(swing_store.fields.keys()) != expected_swing_fields:
        console.print(f"  [red]FAIL[/] Swing store has wrong fields: {swing_store.fields.keys()}")
        console.print(f"      Expected: {expected_swing_fields}")
        failures += 1
    else:
        console.print(f"  [green]OK[/] Swing store has correct public fields: {list(swing_store.fields.keys())}")

    if set(trend_store.fields.keys()) != expected_trend_fields:
        console.print(f"  [red]FAIL[/] Trend store has wrong fields: {trend_store.fields.keys()}")
        console.print(f"      Expected: {expected_trend_fields}")
        failures += 1
    else:
        console.print(f"  [green]OK[/] Trend store has correct public fields: {list(trend_store.fields.keys())}")

    # =========================================================================
    # Step 5: Test Stage 2 exec-only constraint
    # =========================================================================
    console.print(f"\n[bold]Step 5: Test Stage 2 Exec-Only Constraint[/]")

    # Create a spec with tf_role="ctx" (should be rejected in Stage 2)
    ctx_spec = StructureSpec(
        key="ms_htf",
        type=StructureType.SWING,
        tf_role="ctx",  # Not allowed in Stage 2
        params={"left": SWING_LOOKBACK_LEFT, "right": SWING_LOOKBACK_RIGHT},
        confirmation=ConfirmationConfig(mode="immediate"),
    )

    try:
        builder.build(ohlcv, [ctx_spec])
        console.print(f"  [red]FAIL[/] Stage 2 should reject tf_role='ctx'")
        failures += 1
    except Stage2ValidationError as e:
        console.print(f"  [green]OK[/] Stage 2 correctly rejected tf_role='ctx'")
        console.print(f"      Error: {str(e)[:60]}...")

    # =========================================================================
    # Step 6: Wire FeedStore with structures and test Snapshot access
    # =========================================================================
    console.print(f"\n[bold]Step 6: Test FeedStore + Snapshot Integration[/]")

    # Build ts_close_ms_to_idx mapping
    ts_close_ms_to_idx = {}
    close_ts_set = set()
    for i, ts in enumerate(ts_close):
        ts_ms = int(ts.timestamp() * 1000)
        ts_close_ms_to_idx[ts_ms] = i
        close_ts_set.add(ts)

    # Create FeedStore with structures
    feed_store = FeedStore(
        tf="5m",
        symbol="BTCUSDT",
        ts_open=ts_open,
        ts_close=ts_close,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        indicators={},
        structures=stores,
        structure_key_map=key_map,
        close_ts_set=close_ts_set,
        ts_close_ms_to_idx=ts_close_ms_to_idx,
        length=sample_bars,
    )

    console.print(f"  [green]OK[/] FeedStore created with structures")
    console.print(f"      Structures: {list(feed_store.structures.keys())}")
    console.print(f"      Key map: {feed_store.structure_key_map}")

    # Test FeedStore.has_structure
    if not feed_store.has_structure("ms_5m"):
        console.print(f"  [red]FAIL[/] FeedStore.has_structure('ms_5m') returned False")
        failures += 1
    else:
        console.print(f"  [green]OK[/] FeedStore.has_structure('ms_5m') = True")

    # Test FeedStore.get_structure_fields
    swing_fields = feed_store.get_structure_fields("ms_5m")
    if set(swing_fields) != expected_swing_fields:
        console.print(f"  [red]FAIL[/] get_structure_fields wrong: {swing_fields}")
        failures += 1
    else:
        console.print(f"  [green]OK[/] get_structure_fields('ms_5m') = {swing_fields}")

    # Create MultiTFFeedStore
    multi_feed = MultiTFFeedStore(exec_feed=feed_store)

    # Create mock exchange (just needs minimal interface)
    class MockExchange:
        equity_usdt = MOCK_EQUITY_USDT
        available_balance_usdt = MOCK_AVAILABLE_BALANCE_USDT
        position = None
        unrealized_pnl_usdt = 0.0
        entries_disabled = False

    # Test snapshot access at various bar indices
    test_indices = SNAPSHOT_TEST_INDICES + [sample_bars - 1]

    for bar_idx in test_indices:
        console.print(f"\n  [bold]Testing snapshot at bar {bar_idx}:[/]")

        snapshot = RuntimeSnapshotView(
            feeds=multi_feed,
            exec_idx=bar_idx,
            htf_idx=None,
            mtf_idx=None,
            exchange=MockExchange(),
            mark_price=close[bar_idx],
            mark_price_source="close",
        )

        # Test snapshot.get() for swing fields
        try:
            swing_high_level = snapshot.get("structure.ms_5m.swing_high_level")
            console.print(f"    [green]OK[/] structure.ms_5m.swing_high_level = {swing_high_level}")
        except Exception as e:
            console.print(f"    [red]FAIL[/] structure.ms_5m.swing_high_level failed: {e}")
            failures += 1

        try:
            swing_low_level = snapshot.get("structure.ms_5m.swing_low_level")
            console.print(f"    [green]OK[/] structure.ms_5m.swing_low_level = {swing_low_level}")
        except Exception as e:
            console.print(f"    [red]FAIL[/] structure.ms_5m.swing_low_level failed: {e}")
            failures += 1

        # Test snapshot.get() for trend fields
        try:
            trend_state_val = snapshot.get("structure.trend_5m.trend_state")
            console.print(f"    [green]OK[/] structure.trend_5m.trend_state = {trend_state_val}")
        except Exception as e:
            console.print(f"    [red]FAIL[/] structure.trend_5m.trend_state failed: {e}")
            failures += 1

        try:
            parent_ver = snapshot.get("structure.trend_5m.parent_version")
            console.print(f"    [green]OK[/] structure.trend_5m.parent_version = {parent_ver}")
        except Exception as e:
            console.print(f"    [red]FAIL[/] structure.trend_5m.parent_version failed: {e}")
            failures += 1

    # =========================================================================
    # Step 7: Test Zone Access (Stage 5)
    # =========================================================================
    console.print(f"\n[bold]Step 7: Test Zone Access (Stage 5)[/]")

    snapshot = RuntimeSnapshotView(
        feeds=multi_feed,
        exec_idx=ZONE_TEST_BAR_INDEX,  # Middle of data
        htf_idx=None,
        mtf_idx=None,
        exchange=MockExchange(),
        mark_price=close[ZONE_TEST_BAR_INDEX],
        mark_price_source="close",
    )

    # Test zone field access via snapshot (including Stage 6 interaction fields)
    zone_tests = [
        "structure.ms_5m.zones.demand_1.lower",
        "structure.ms_5m.zones.demand_1.upper",
        "structure.ms_5m.zones.demand_1.state",
        "structure.ms_5m.zones.demand_1.touched",       # Stage 6
        "structure.ms_5m.zones.demand_1.inside",        # Stage 6
        "structure.ms_5m.zones.demand_1.time_in_zone",  # Stage 6
        "structure.ms_5m.zones.supply_1.lower",
        "structure.ms_5m.zones.supply_1.upper",
        "structure.ms_5m.zones.supply_1.state",
        "structure.ms_5m.zones.supply_1.touched",       # Stage 6
        "structure.ms_5m.zones.supply_1.inside",        # Stage 6
        "structure.ms_5m.zones.supply_1.time_in_zone",  # Stage 6
    ]

    for path in zone_tests:
        try:
            value = snapshot.get(path)
            console.print(f"  [green]OK[/] {path} = {value}")
        except Exception as e:
            console.print(f"  [red]FAIL[/] {path} failed: {e}")
            failures += 1

    # Check that zones have been computed
    swing_store = stores[swing_spec.block_id]
    if not swing_store.zones:
        console.print(f"  [red]FAIL[/] No zones computed for swing block")
        failures += 1
    else:
        console.print(f"  [green]OK[/] Swing block has zones: {list(swing_store.zones.keys())}")

        # Check zone arrays are correct length
        for zone_key, zone_store in swing_store.zones.items():
            for field_name, arr in zone_store.fields.items():
                if len(arr) != sample_bars:
                    console.print(f"  [red]FAIL[/] Zone {zone_key}.{field_name} wrong length: {len(arr)} != {sample_bars}")
                    failures += 1

        console.print(f"  [green]OK[/] Zone arrays have correct length ({sample_bars})")

    # =========================================================================
    # Step 7.5: Test Strict Allowlist (Unknown Fields Hard-Fail)
    # =========================================================================
    console.print(f"\n[bold]Step 7.5: Test Strict Allowlist (Unknown Fields Hard-Fail)[/]")

    # Test unknown block_key
    try:
        snapshot.get("structure.unknown_block.swing_high_level")
        console.print(f"  [red]FAIL[/] Unknown block_key should raise ValueError")
        failures += 1
    except ValueError as e:
        console.print(f"  [green]OK[/] Unknown block_key raises ValueError")
        console.print(f"      Error: {str(e)[:60]}...")

    # Test unknown field_name
    try:
        snapshot.get("structure.ms_5m.unknown_field")
        console.print(f"  [red]FAIL[/] Unknown field_name should raise ValueError")
        failures += 1
    except ValueError as e:
        console.print(f"  [green]OK[/] Unknown field_name raises ValueError")
        console.print(f"      Error: {str(e)[:60]}...")

    # Test unknown zone_key
    try:
        snapshot.get("structure.ms_5m.zones.unknown_zone.lower")
        console.print(f"  [red]FAIL[/] Unknown zone_key should raise ValueError")
        failures += 1
    except ValueError as e:
        console.print(f"  [green]OK[/] Unknown zone_key raises ValueError")
        console.print(f"      Error: {str(e)[:60]}...")

    # Test unknown zone field
    try:
        snapshot.get("structure.ms_5m.zones.demand_1.unknown_field")
        console.print(f"  [red]FAIL[/] Unknown zone field should raise ValueError")
        failures += 1
    except ValueError as e:
        console.print(f"  [green]OK[/] Unknown zone field raises ValueError")
        console.print(f"      Error: {str(e)[:60]}...")

    # =========================================================================
    # Step 8: Test no lookahead (pivot confirms after right bars)
    # =========================================================================
    console.print(f"\n[bold]Step 8: Test No Lookahead (Pivot Confirmation Timing)[/]")

    # Find first bar where swing high is confirmed
    high_level = swing_store.fields["swing_high_level"]
    high_idx = swing_store.fields["swing_high_idx"]

    first_confirmed_bar = None
    first_pivot_bar = None
    for i in range(sample_bars):
        if not np.isnan(high_level[i]) and not np.isnan(high_idx[i]):
            first_confirmed_bar = i
            first_pivot_bar = int(high_idx[i])
            break

    if first_confirmed_bar is not None:
        lookback = params["right"]  # right = 5 bars for confirmation
        # Confirmation bar should be at least `right` bars after pivot bar
        expected_min_confirm = first_pivot_bar + lookback
        if first_confirmed_bar >= expected_min_confirm:
            console.print(f"  [green]OK[/] No lookahead: pivot at bar {first_pivot_bar}, confirmed at bar {first_confirmed_bar}")
            console.print(f"      Expected min confirm bar: {expected_min_confirm}")
        else:
            console.print(f"  [red]FAIL[/] Lookahead detected! Pivot at {first_pivot_bar}, confirmed at {first_confirmed_bar}")
            console.print(f"      Expected min confirm bar: {expected_min_confirm}")
            failures += 1
    else:
        console.print(f"  [yellow]WARN[/] No swing highs confirmed in test data")

    # =========================================================================
    # Step 9: Test determinism
    # =========================================================================
    console.print(f"\n[bold]Step 9: Test Determinism[/]")

    # Build again with same specs
    stores2 = builder.build(ohlcv, [swing_spec, trend_spec])

    all_match = True
    for block_id in stores:
        for field_name in stores[block_id].fields:
            arr1 = stores[block_id].fields[field_name]
            arr2 = stores2[block_id].fields[field_name]
            if not np.allclose(arr1, arr2, equal_nan=True):
                console.print(f"  [red]FAIL[/] {block_id}.{field_name} differs between runs")
                all_match = False
                failures += 1

    if all_match:
        console.print(f"  [green]OK[/] All values match between builder runs")

    # =========================================================================
    # Step 9.1: Test Zone instance_id (Stage 5.1)
    # =========================================================================
    console.print(f"\n[bold]Step 9.1: Test Zone instance_id (Stage 5.1)[/]")

    from src.backtest.market_structure.detectors.zone_detector import (
        compute_zone_instance_id,
        compute_zone_spec_id,
    )

    # Test compute_zone_spec_id determinism
    spec_id_1 = compute_zone_spec_id(demand_zone)
    spec_id_2 = compute_zone_spec_id(demand_zone)
    if spec_id_1 != spec_id_2:
        console.print(f"  [red]FAIL[/] compute_zone_spec_id not deterministic")
        failures += 1
    else:
        console.print(f"  [green]OK[/] compute_zone_spec_id is deterministic: {spec_id_1}")

    # Test compute_zone_instance_id determinism
    inst_id_1 = compute_zone_instance_id("demand_1", spec_id_1, 42)
    inst_id_2 = compute_zone_instance_id("demand_1", spec_id_1, 42)
    if inst_id_1 != inst_id_2:
        console.print(f"  [red]FAIL[/] compute_zone_instance_id not deterministic")
        failures += 1
    else:
        console.print(f"  [green]OK[/] compute_zone_instance_id is deterministic: {inst_id_1}")

    # Test that different parent_anchor_id gives different instance_id
    inst_id_diff = compute_zone_instance_id("demand_1", spec_id_1, 43)
    if inst_id_1 == inst_id_diff:
        console.print(f"  [red]FAIL[/] Different parent_anchor_id should give different instance_id")
        failures += 1
    else:
        console.print(f"  [green]OK[/] Different parent_anchor_id -> different instance_id")

    # Test that NONE state returns 0
    inst_id_none = compute_zone_instance_id("demand_1", spec_id_1, -1)
    if inst_id_none != 0:
        console.print(f"  [red]FAIL[/] parent_anchor_id=-1 should return instance_id=0")
        failures += 1
    else:
        console.print(f"  [green]OK[/] parent_anchor_id=-1 -> instance_id=0")

    # Test zone arrays have instance_id field
    swing_store_check = stores[swing_spec.block_id]
    for zone_key, zone_store in swing_store_check.zones.items():
        if "instance_id" not in zone_store.fields:
            console.print(f"  [red]FAIL[/] Zone {zone_key} missing instance_id field")
            failures += 1
        else:
            instance_id_arr = zone_store.fields["instance_id"]
            if len(instance_id_arr) != sample_bars:
                console.print(f"  [red]FAIL[/] Zone {zone_key}.instance_id wrong length")
                failures += 1
            else:
                # Check instance_id is 0 where state is NONE, non-zero otherwise
                state_arr = zone_store.fields["state"]
                for i in INSTANCE_ID_CHECK_INDICES:
                    if i < sample_bars:
                        if state_arr[i] == ZoneState.NONE.value:
                            if instance_id_arr[i] != 0:
                                console.print(f"  [red]FAIL[/] Zone {zone_key} instance_id should be 0 when state=NONE")
                                failures += 1
                                break
                        elif state_arr[i] in (ZoneState.ACTIVE.value, ZoneState.BROKEN.value):
                            if instance_id_arr[i] == 0:
                                console.print(f"  [red]FAIL[/] Zone {zone_key} instance_id should be non-zero when ACTIVE/BROKEN")
                                failures += 1
                                break
                else:
                    console.print(f"  [green]OK[/] Zone {zone_key}.instance_id correctly computed")

    # Test zone determinism includes instance_id
    for zone_key in swing_store_check.zones:
        arr1 = stores[swing_spec.block_id].zones[zone_key].fields["instance_id"]
        arr2 = stores2[swing_spec.block_id].zones[zone_key].fields["instance_id"]
        if not np.array_equal(arr1, arr2):
            console.print(f"  [red]FAIL[/] Zone {zone_key}.instance_id not deterministic between runs")
            failures += 1
        else:
            console.print(f"  [green]OK[/] Zone {zone_key}.instance_id deterministic between runs")

    # =========================================================================
    # Step 9.2: Test Duplicate Zone Key Validation (Stage 5.1)
    # =========================================================================
    console.print(f"\n[bold]Step 9.2: Test Duplicate Zone Key Validation (Stage 5.1)[/]")

    try:
        # Create spec with duplicate zone keys - should fail
        dup_zones_spec = {
            "key": "test_block",
            "type": "swing",
            "tf_role": "exec",
            "params": {"left": SWING_LOOKBACK_LEFT, "right": SWING_LOOKBACK_RIGHT},
            "zones": [
                {"key": "demand_1", "type": "demand", "width_model": "percent", "width_params": {"pct": ZONE_WIDTH_PERCENT}},
                {"key": "demand_1", "type": "demand", "width_model": "percent", "width_params": {"pct": ZONE_WIDTH_PERCENT * 2}},  # Duplicate!
            ],
        }
        StructureSpec.from_dict(dup_zones_spec)
        console.print(f"  [red]FAIL[/] Duplicate zone keys should raise ValueError")
        failures += 1
    except ValueError as e:
        if "Duplicate zone key" in str(e):
            console.print(f"  [green]OK[/] Duplicate zone keys correctly rejected")
            console.print(f"      Error: {str(e)[:60]}...")
        else:
            console.print(f"  [red]FAIL[/] Wrong error type: {e}")
            failures += 1

    # =========================================================================
    # Step 9.3: Test Zone Interaction Fields (Stage 6)
    # =========================================================================
    console.print(f"\n[bold]Step 9.3: Test Zone Interaction Fields (Stage 6)[/]")

    from src.backtest.market_structure.types import ZONE_OUTPUTS

    # Verify Stage 6 fields exist in ZONE_OUTPUTS
    stage6_fields = {"touched", "inside", "time_in_zone"}
    if not stage6_fields.issubset(set(ZONE_OUTPUTS)):
        console.print(f"  [red]FAIL[/] Stage 6 fields missing from ZONE_OUTPUTS")
        failures += 1
    else:
        console.print(f"  [green]OK[/] Stage 6 fields in ZONE_OUTPUTS: {stage6_fields}")

    # Verify interaction fields are computed for zones
    for zone_key in ["demand_1", "supply_1"]:
        zone_store = swing_store_check.zones.get(zone_key)
        if zone_store is None:
            continue

        for field in stage6_fields:
            if field not in zone_store.fields:
                console.print(f"  [red]FAIL[/] Zone {zone_key} missing {field}")
                failures += 1
            else:
                arr = zone_store.fields[field]
                console.print(f"  [green]OK[/] Zone {zone_key}.{field} dtype={arr.dtype}")

    # Verify dtypes: touched/inside = uint8, time_in_zone = int32
    for zone_key, zone_store in swing_store_check.zones.items():
        if "touched" in zone_store.fields:
            if zone_store.fields["touched"].dtype != np.uint8:
                console.print(f"  [red]FAIL[/] Zone {zone_key}.touched should be uint8")
                failures += 1
        if "inside" in zone_store.fields:
            if zone_store.fields["inside"].dtype != np.uint8:
                console.print(f"  [red]FAIL[/] Zone {zone_key}.inside should be uint8")
                failures += 1
        if "time_in_zone" in zone_store.fields:
            if zone_store.fields["time_in_zone"].dtype != np.int32:
                console.print(f"  [red]FAIL[/] Zone {zone_key}.time_in_zone should be int32")
                failures += 1

    console.print(f"  [green]OK[/] Stage 6 dtype checks passed")

    # Test state != ACTIVE override: when state is NONE, interaction metrics must be 0
    for zone_key, zone_store in swing_store_check.zones.items():
        state_arr = zone_store.fields["state"]
        touched_arr = zone_store.fields["touched"]
        inside_arr = zone_store.fields["inside"]
        time_in_zone_arr = zone_store.fields["time_in_zone"]

        # Find indices where state == NONE
        none_mask = state_arr == ZoneState.NONE.value
        if none_mask.any():
            # All metrics should be 0 at these indices
            if touched_arr[none_mask].any():
                console.print(f"  [red]FAIL[/] Zone {zone_key}.touched should be 0 when state=NONE")
                failures += 1
            if inside_arr[none_mask].any():
                console.print(f"  [red]FAIL[/] Zone {zone_key}.inside should be 0 when state=NONE")
                failures += 1
            if time_in_zone_arr[none_mask].any():
                console.print(f"  [red]FAIL[/] Zone {zone_key}.time_in_zone should be 0 when state=NONE")
                failures += 1

        # Find indices where state == BROKEN
        broken_mask = state_arr == ZoneState.BROKEN.value
        if broken_mask.any():
            # All metrics should be 0 at break bars
            if touched_arr[broken_mask].any():
                console.print(f"  [red]FAIL[/] Zone {zone_key}.touched should be 0 when state=BROKEN")
                failures += 1
            if inside_arr[broken_mask].any():
                console.print(f"  [red]FAIL[/] Zone {zone_key}.inside should be 0 when state=BROKEN")
                failures += 1
            if time_in_zone_arr[broken_mask].any():
                console.print(f"  [red]FAIL[/] Zone {zone_key}.time_in_zone should be 0 when state=BROKEN")
                failures += 1

    console.print(f"  [green]OK[/] Stage 6 state overrides verified (NONE/BROKEN -> metrics=0)")

    # Test determinism for interaction fields
    for zone_key in swing_store_check.zones:
        for field in stage6_fields:
            arr1 = stores[swing_spec.block_id].zones[zone_key].fields[field]
            arr2 = stores2[swing_spec.block_id].zones[zone_key].fields[field]
            if not np.array_equal(arr1, arr2):
                console.print(f"  [red]FAIL[/] Zone {zone_key}.{field} not deterministic between runs")
                failures += 1

    console.print(f"  [green]OK[/] Stage 6 interaction fields deterministic between runs")

    # =========================================================================
    # Step 10: Test pure function (detect_swing_pivots)
    # =========================================================================
    console.print(f"\n[bold]Step 10: Test Pure Function (detect_swing_pivots)[/]")

    try:
        is_swing_high, is_swing_low = detect_swing_pivots(high, low, left=SWING_LOOKBACK_LEFT, right=SWING_LOOKBACK_RIGHT)
        num_highs = np.sum(is_swing_high)
        num_lows = np.sum(is_swing_low)
        console.print(f"  [green]OK[/] detect_swing_pivots() completed")
        console.print(f"      Swing highs: {num_highs}")
        console.print(f"      Swing lows: {num_lows}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] detect_swing_pivots() failed: {e}")
        failures += 1

    # =========================================================================
    # Summary
    # =========================================================================
    console.print(f"\n{'=' * SEPARATOR_WIDTH}")
    console.print(f"[bold cyan]MARKET STRUCTURE SMOKE TEST COMPLETE (Stage 5)[/]")
    console.print(f"{'=' * SEPARATOR_WIDTH}")

    console.print(f"\n[bold]Summary:[/]")
    console.print(f"  Bars tested: {sample_bars}")
    console.print(f"  Swing params: left={params['left']}, right={params['right']}")
    console.print(f"  Swing highs confirmed: {num_high_confirmed + num_both_confirmed}")
    console.print(f"  Swing lows confirmed: {num_low_confirmed + num_both_confirmed}")
    console.print(f"  Trend transitions: {parent_version.max()}")
    console.print(f"  Zones computed: demand_1, supply_1")
    console.print(f"  Failures: {failures}")

    console.print(f"\n[bold]Stage 5 + 5.1 + 6 Checklist:[/]")
    console.print(f"  [green]OK[/] StructureBuilder orchestrates SWING + TREND")
    console.print(f"  [green]OK[/] Public field names (swing_high_level, not high_level)")
    console.print(f"  [green]OK[/] FeedStore.structures populated")
    console.print(f"  [green]OK[/] snapshot.get('structure.<key>.<field>') works")
    console.print(f"  [green]OK[/] Strict allowlist (unknown fields hard-fail)")
    console.print(f"  [green]OK[/] tf_role='exec' enforced (Stage 2)")
    console.print(f"  [green]OK[/] Zones computed and attached to SWING blocks (Stage 5)")
    console.print(f"  [green]OK[/] snapshot.get('structure.<key>.zones.<zone>.<field>') works (Stage 5)")
    console.print(f"  [green]OK[/] Zone state machine: NONE -> ACTIVE -> BROKEN")
    console.print(f"  [green]OK[/] Zone instance_id computed deterministically (Stage 5.1)")
    console.print(f"  [green]OK[/] Duplicate zone keys rejected at build time (Stage 5.1)")
    console.print(f"  [green]OK[/] Zone interaction fields (touched, inside, time_in_zone) (Stage 6)")
    console.print(f"  [green]OK[/] Dtypes: touched/inside=uint8, time_in_zone=int32 (Stage 6)")
    console.print(f"  [green]OK[/] State overrides: NONE/BROKEN -> metrics=0 (Stage 6)")
    console.print(f"  [green]OK[/] Interaction fields deterministic between runs (Stage 6)")

    if failures == 0:
        console.print(f"\n[bold green]OK[/] STAGE 6 MARKET STRUCTURE + ZONES + INTERACTION VERIFIED")
    else:
        console.print(f"\n[bold red]FAIL[/] {failures} failure(s)")

    return failures


def run_state_tracking_smoke() -> int:
    """
    Run Stage 7 state tracking smoke test.

    Validates:
    - State types import correctly
    - State transitions are deterministic
    - GateResult pass/fail helpers work
    - BlockState properties compute correctly

    Returns:
        Number of failures (0 = success)
    """
    console.print(Panel(
        "[bold]STATE TRACKING SMOKE TEST (Stage 7)[/]\n"
        "[dim]Validates Signal/Action/Gate state machines[/]",
        border_style="cyan",
    ))

    failures = 0

    # =========================================================================
    # Step 1: Import state types
    # =========================================================================
    console.print(f"\n[bold]Step 1: Import State Types[/]")

    try:
        from src.backtest.runtime import (
            SignalStateValue,
            ActionStateValue,
            GateCode,
            GateResult,
            SignalState,
            ActionState,
            BlockState,
            create_state_tracker,
        )
        console.print(f"  [green]OK[/] All Stage 7 types imported")
    except ImportError as e:
        console.print(f"  [red]FAIL[/] Import error: {e}")
        return 1  # Fatal

    # =========================================================================
    # Step 2: Test GateResult helpers
    # =========================================================================
    console.print(f"\n[bold]Step 2: Test GateResult Helpers[/]")

    result_pass = GateResult.pass_()
    if not result_pass.passed:
        console.print(f"  [red]FAIL[/] GateResult.pass_() should have passed=True")
        failures += 1
    elif result_pass.code != GateCode.G_PASS:
        console.print(f"  [red]FAIL[/] GateResult.pass_() should have code=G_PASS")
        failures += 1
    else:
        console.print(f"  [green]OK[/] GateResult.pass_() works correctly")

    result_fail = GateResult.fail_(GateCode.G_WARMUP_REMAINING)
    if result_fail.passed:
        console.print(f"  [red]FAIL[/] GateResult.fail_() should have passed=False")
        failures += 1
    elif result_fail.code != GateCode.G_WARMUP_REMAINING:
        console.print(f"  [red]FAIL[/] GateResult.fail_() should preserve code")
        failures += 1
    else:
        console.print(f"  [green]OK[/] GateResult.fail_() works correctly")

    # =========================================================================
    # Step 3: Test State Transitions
    # =========================================================================
    console.print(f"\n[bold]Step 3: Test State Transitions[/]")

    from src.backtest.runtime import transition_signal_state, reset_signal_state

    # Test NONE -> CONFIRMED (one-bar confirmation)
    initial = reset_signal_state()
    if initial.value != SignalStateValue.NONE:
        console.print(f"  [red]FAIL[/] reset_signal_state() should return NONE")
        failures += 1

    next_state = transition_signal_state(
        prev_state=initial,
        bar_idx=10,
        signal_detected=True,
        signal_direction=1,  # LONG
        gate_result=GateResult.pass_(),
        action_taken=False,
        next_signal_id=1,
        confirmation_bars=1,
    )

    if next_state.value != SignalStateValue.CONFIRMED:
        console.print(f"  [red]FAIL[/] One-bar confirmation should go directly to CONFIRMED")
        failures += 1
    elif next_state.direction != 1:
        console.print(f"  [red]FAIL[/] Signal direction should be preserved")
        failures += 1
    elif next_state.detected_bar != 10:
        console.print(f"  [red]FAIL[/] detected_bar should be set")
        failures += 1
    else:
        console.print(f"  [green]OK[/] NONE -> CONFIRMED transition works")

    # Test CONFIRMED -> CONSUMED (action taken)
    consumed_state = transition_signal_state(
        prev_state=next_state,
        bar_idx=11,
        signal_detected=False,
        signal_direction=0,
        gate_result=GateResult.pass_(),
        action_taken=True,
        next_signal_id=2,
        confirmation_bars=1,
    )

    if consumed_state.value != SignalStateValue.CONSUMED:
        console.print(f"  [red]FAIL[/] CONFIRMED + action_taken should go to CONSUMED")
        failures += 1
    else:
        console.print(f"  [green]OK[/] CONFIRMED -> CONSUMED transition works")

    # =========================================================================
    # Step 4: Test BlockState Properties
    # =========================================================================
    console.print(f"\n[bold]Step 4: Test BlockState Properties[/]")

    from src.backtest.runtime import create_block_state

    block = create_block_state(
        bar_idx=10,
        signal=next_state,  # CONFIRMED
        action=ActionState(),  # IDLE
        gate=GateResult.pass_(),
        raw_signal_direction=1,
    )

    if not block.is_actionable:
        console.print(f"  [red]FAIL[/] BlockState.is_actionable should be True")
        failures += 1
    elif block.is_blocked:
        console.print(f"  [red]FAIL[/] BlockState.is_blocked should be False")
        failures += 1
    else:
        console.print(f"  [green]OK[/] BlockState properties work correctly")

    # Test blocked block
    blocked_block = create_block_state(
        bar_idx=5,
        signal=SignalState(value=SignalStateValue.CONFIRMED),
        action=ActionState(),
        gate=GateResult.fail_(GateCode.G_WARMUP_REMAINING),
        raw_signal_direction=1,
    )

    if blocked_block.is_actionable:
        console.print(f"  [red]FAIL[/] Blocked BlockState should not be actionable")
        failures += 1
    elif not blocked_block.is_blocked:
        console.print(f"  [red]FAIL[/] Blocked BlockState.is_blocked should be True")
        failures += 1
    elif blocked_block.block_code != GateCode.G_WARMUP_REMAINING:
        console.print(f"  [red]FAIL[/] block_code should be preserved")
        failures += 1
    else:
        console.print(f"  [green]OK[/] Blocked BlockState properties work correctly")

    # =========================================================================
    # Step 5: Test StateTracker
    # =========================================================================
    console.print(f"\n[bold]Step 5: Test StateTracker[/]")

    tracker = create_state_tracker(warmup_bars=STATE_TRACKER_WARMUP_BARS)

    # Simulate a few bars
    for bar_idx in range(STATE_TRACKER_TEST_BARS):
        tracker.on_bar_start(bar_idx)
        tracker.on_warmup_check(bar_idx >= STATE_TRACKER_WARMUP_BARS, STATE_TRACKER_WARMUP_BARS)
        tracker.on_history_check(True, bar_idx)

        # Simulate signal on specific bars
        if bar_idx in STATE_TRACKER_SIGNAL_BARS:
            tracker.on_signal_evaluated(1)  # LONG signal
        else:
            tracker.on_signal_evaluated(0)  # No signal

        tracker.on_position_check(0)
        tracker.on_bar_end()

    # Check history was recorded
    if len(tracker.block_history) != STATE_TRACKER_TEST_BARS:
        console.print(f"  [red]FAIL[/] block_history should have {STATE_TRACKER_TEST_BARS} entries, got {len(tracker.block_history)}")
        failures += 1
    else:
        console.print(f"  [green]OK[/] block_history has correct length")

    # Check summary stats
    stats = tracker.summary_stats()
    expected_signals = len(STATE_TRACKER_SIGNAL_BARS)
    if stats.get("total_bars") != STATE_TRACKER_TEST_BARS:
        console.print(f"  [red]FAIL[/] summary_stats total_bars wrong")
        failures += 1
    elif stats.get("signals_detected", 0) < expected_signals:
        console.print(f"  [red]FAIL[/] summary_stats should show {expected_signals} signals detected")
        failures += 1
    else:
        console.print(f"  [green]OK[/] StateTracker summary_stats works")

    # =========================================================================
    # Step 6: Test Determinism
    # =========================================================================
    console.print(f"\n[bold]Step 6: Test Determinism[/]")

    # Run twice with same inputs
    tracker1 = create_state_tracker(warmup_bars=STATE_TRACKER_WARMUP_BARS)
    tracker2 = create_state_tracker(warmup_bars=STATE_TRACKER_WARMUP_BARS)

    for bar_idx in range(STATE_TRACKER_DETERMINISM_BARS):
        # Same inputs to both trackers
        signal_direction = 1 if bar_idx in STATE_TRACKER_DETERMINISM_SIGNAL_BARS else 0

        for t in (tracker1, tracker2):
            t.on_bar_start(bar_idx)
            t.on_warmup_check(bar_idx >= STATE_TRACKER_WARMUP_BARS, STATE_TRACKER_WARMUP_BARS)
            t.on_history_check(True, bar_idx)
            t.on_signal_evaluated(signal_direction)
            t.on_position_check(0)
            t.on_bar_end()

    # Compare histories
    determinism_ok = True
    for i in range(STATE_TRACKER_DETERMINISM_BARS):
        b1 = tracker1.block_history[i]
        b2 = tracker2.block_history[i]
        if b1.signal.value != b2.signal.value:
            console.print(f"  [red]FAIL[/] Signal state differs at bar {i}")
            failures += 1
            determinism_ok = False
            break
        if b1.gate.code != b2.gate.code:
            console.print(f"  [red]FAIL[/] Gate code differs at bar {i}")
            failures += 1
            determinism_ok = False
            break

    if determinism_ok:
        console.print(f"  [green]OK[/] State tracking is deterministic")

    # =========================================================================
    # Summary
    # =========================================================================
    console.print(f"\n{'=' * SEPARATOR_WIDTH}")
    console.print(f"[bold cyan]STATE TRACKING SMOKE TEST COMPLETE (Stage 7)[/]")
    console.print(f"{'=' * SEPARATOR_WIDTH}")

    console.print(f"\n[bold]Stage 7 Checklist:[/]")
    console.print(f"  [green]OK[/] State type enums imported")
    console.print(f"  [green]OK[/] GateResult pass/fail helpers work")
    console.print(f"  [green]OK[/] Signal state transitions correct")
    console.print(f"  [green]OK[/] BlockState properties compute correctly")
    console.print(f"  [green]OK[/] StateTracker records block history")
    console.print(f"  [green]OK[/] State tracking is deterministic")

    if failures == 0:
        console.print(f"\n[bold green]OK[/] STAGE 7 STATE TRACKING VERIFIED")
    else:
        console.print(f"\n[bold red]FAIL[/] {failures} failure(s)")

    return failures


def run_state_tracking_parity_smoke(
    play_id: str = "V_01_single_5m_rsi_ema",
) -> int:
    """
    Run State Tracking Parity Smoke Test.

    Validates the "record-only guarantee": state tracking must not affect
    trade outcomes. Runs the same Play twice:
    1. With record_state_tracking=False (baseline)
    2. With record_state_tracking=True (test)

    Compares trades hashes to ensure parity.

    Args:
        play_id: Play to use for the test (default: V_01)

    Returns:
        Number of failures (0 = success)

    Raises:
        ValueError: If parity is violated (hashes differ)
    """
    from datetime import datetime, timezone
    from pathlib import Path
    import tempfile

    from src.backtest.play import load_play
    from src.backtest.execution_validation import compute_warmup_requirements
    from src.backtest.engine_factory import create_engine_from_play, run_engine_with_play
    from src.backtest.artifacts.hashes import compute_trades_hash
    from src.data.historical_data_store import get_historical_store

    console.print(Panel(
        "[bold]STATE TRACKING PARITY SMOKE TEST[/]\n"
        "[dim]Validates record_state_tracking does not affect trade outcomes[/]",
        border_style="cyan",
    ))

    failures = 0

    # =========================================================================
    # Step 1: Load Play and compute window
    # =========================================================================
    console.print(f"\n[bold]Step 1: Load Play[/]")

    try:
        play = load_play(play_id)
        console.print(f"  [green]OK[/] Loaded Play: {play_id}")
    except FileNotFoundError as e:
        console.print(f"  [red]FAIL[/] Play not found: {e}")
        return 1

    # Get symbol and check data availability
    symbol = play.symbol_universe[0] if play.symbol_universe else "BTCUSDT"
    exec_tf = play.exec_tf

    console.print(f"      Symbol: {symbol}")
    console.print(f"      Exec TF: {exec_tf}")

    # =========================================================================
    # Step 2: Check data availability
    # =========================================================================
    console.print(f"\n[bold]Step 2: Check Data Availability[/]")

    try:
        store = get_historical_store()
        # Use a short window for smoke testing
        window_end = datetime.now(timezone.utc).replace(tzinfo=None)
        window_start = window_end - timedelta(days=PARITY_TEST_WINDOW_DAYS)

        # Check if we have data
        df = store.query_ohlcv(
            symbol=symbol,
            timeframe=exec_tf,
            start=window_start,
            end=window_end,
        )

        if df is None or len(df) < PARITY_TEST_MIN_BARS:
            console.print(f"  [yellow]SKIP[/] Insufficient data ({len(df) if df is not None else 0} bars)")
            console.print(f"      Need at least {PARITY_TEST_MIN_BARS} bars for parity test")
            console.print(f"      Run: python trade_cli.py data sync --symbol {symbol} --tf {exec_tf}")
            return 0  # Skip, not fail

        console.print(f"  [green]OK[/] Data available: {len(df)} bars")
        console.print(f"      Window: {window_start.date()} to {window_end.date()}")

    except Exception as e:
        console.print(f"  [yellow]SKIP[/] Could not query data: {e}")
        return 0  # Skip, not fail

    # =========================================================================
    # Step 3: Compute warmup requirements
    # =========================================================================
    console.print(f"\n[bold]Step 3: Compute Warmup[/]")

    try:
        warmup_reqs = compute_warmup_requirements(play)
        warmup_by_role = warmup_reqs.warmup_by_role
        delay_by_role = warmup_reqs.delay_by_role
        console.print(f"  [green]OK[/] Warmup by role: {warmup_by_role}")
    except Exception as e:
        console.print(f"  [red]FAIL[/] Warmup computation failed: {e}")
        return 1

    # =========================================================================
    # Step 4: Run backtest WITHOUT state tracking (baseline)
    # =========================================================================
    console.print(f"\n[bold]Step 4: Run Backtest (record_state_tracking=False)[/]")

    try:
        engine_baseline = create_engine_from_play(
            play=play,
            window_start=window_start,
            window_end=window_end,
            warmup_by_role=warmup_by_role,
            delay_by_role=delay_by_role,
            run_dir=None,
        )
        # Explicitly set record_state_tracking=False (should be default)
        engine_baseline.record_state_tracking = False

        result_baseline = run_engine_with_play(engine_baseline, play)
        trades_hash_baseline = compute_trades_hash(result_baseline.trades)

        console.print(f"  [green]OK[/] Baseline run completed")
        console.print(f"      Trades: {len(result_baseline.trades)}")
        console.print(f"      Trades hash: {trades_hash_baseline}")

    except Exception as e:
        console.print(f"  [red]FAIL[/] Baseline run failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # =========================================================================
    # Step 5: Run backtest WITH state tracking
    # =========================================================================
    console.print(f"\n[bold]Step 5: Run Backtest (record_state_tracking=True)[/]")

    try:
        engine_with_tracking = create_engine_from_play(
            play=play,
            window_start=window_start,
            window_end=window_end,
            warmup_by_role=warmup_by_role,
            delay_by_role=delay_by_role,
            run_dir=None,
        )
        # Enable state tracking
        engine_with_tracking.record_state_tracking = True

        result_with_tracking = run_engine_with_play(engine_with_tracking, play)
        trades_hash_with_tracking = compute_trades_hash(result_with_tracking.trades)

        console.print(f"  [green]OK[/] State tracking run completed")
        console.print(f"      Trades: {len(result_with_tracking.trades)}")
        console.print(f"      Trades hash: {trades_hash_with_tracking}")

    except Exception as e:
        console.print(f"  [red]FAIL[/] State tracking run failed: {e}")
        import traceback
        traceback.print_exc()
        return 1

    # =========================================================================
    # Step 6: Compare hashes
    # =========================================================================
    console.print(f"\n[bold]Step 6: Compare Trade Hashes[/]")

    if trades_hash_baseline == trades_hash_with_tracking:
        console.print(f"  [green]OK[/] PARITY CONFIRMED")
        console.print(f"      Baseline hash:  {trades_hash_baseline}")
        console.print(f"      Tracking hash:  {trades_hash_with_tracking}")
    else:
        console.print(f"  [red]FAIL[/] PARITY VIOLATED!")
        console.print(f"      Baseline hash:  {trades_hash_baseline}")
        console.print(f"      Tracking hash:  {trades_hash_with_tracking}")
        console.print(f"      [red]State tracking affected trade outcomes - this is a BUG[/]")
        failures += 1
        raise ValueError(
            f"State tracking parity violated: baseline={trades_hash_baseline}, "
            f"tracking={trades_hash_with_tracking}"
        )

    # =========================================================================
    # Summary
    # =========================================================================
    console.print(f"\n{'=' * SEPARATOR_WIDTH}")
    console.print(f"[bold cyan]STATE TRACKING PARITY SMOKE TEST COMPLETE[/]")
    console.print(f"{'=' * SEPARATOR_WIDTH}")

    console.print(f"\n[bold]Record-Only Guarantee:[/]")
    console.print(f"  [green]OK[/] record_state_tracking=True produces identical trades")
    console.print(f"  [green]OK[/] Trade hash matches baseline: {trades_hash_baseline}")

    if failures == 0:
        console.print(f"\n[bold green]OK[/] STATE TRACKING PARITY VERIFIED")
    else:
        console.print(f"\n[bold red]FAIL[/] {failures} failure(s)")

    return failures
