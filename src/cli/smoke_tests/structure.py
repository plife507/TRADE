"""
Market Structure Smoke Tests.

Validates SwingDetector, TrendClassifier, StructureBuilder, and
RuntimeSnapshotView integration with synthetic data.

Stage 2: Validates end-to-end pipeline from StructureSpec through
snapshot.get("structure.<block_key>.<field>").
"""

import numpy as np
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel

console = Console()


def run_structure_smoke(
    sample_bars: int = 500,
    seed: int = 42,
) -> int:
    """
    Run market structure smoke test.

    Stage 2 validates:
    - StructureBuilder with exec-only constraint
    - FeedStore.structures population
    - snapshot.get("structure.*") resolution
    - Strict allowlist validation (unknown fields hard-fail)
    - No lookahead (pivot confirmed only after lookback)

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
    from src.backtest.runtime.feed_store import FeedStore, MultiTFFeedStore
    from src.backtest.runtime.snapshot_view import RuntimeSnapshotView

    console.print(Panel(
        "[bold]MARKET STRUCTURE SMOKE TEST (Stage 2)[/]\n"
        "[dim]Validates StructureBuilder + Snapshot integration[/]",
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
    t = np.linspace(0, 8 * np.pi, sample_bars)
    # Base trend with oscillation
    base = 40000 + 1000 * np.sin(t * 0.5) + 500 * np.sin(t * 2)
    # Add noise
    noise = np.random.randn(sample_bars) * 50

    close = base + noise
    high = close + np.abs(np.random.randn(sample_bars) * 100) + 20
    low = close - np.abs(np.random.randn(sample_bars) * 100) - 20
    open_ = close + np.random.randn(sample_bars) * 30
    volume = np.abs(np.random.randn(sample_bars) * 1000) + 100

    # Generate timestamps (5m bars)
    start_ts = datetime(2024, 1, 1, 0, 0, 0)
    ts_close = np.array([
        start_ts + timedelta(minutes=5 * (i + 1)) for i in range(sample_bars)
    ])
    ts_open = np.array([
        start_ts + timedelta(minutes=5 * i) for i in range(sample_bars)
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

    params = {"left": 5, "right": 5}

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
    # Step 4: Test StructureBuilder with StructureSpecs
    # =========================================================================
    console.print(f"\n[bold]Step 4: Test StructureBuilder[/]")

    # Create SWING spec
    swing_spec = StructureSpec(
        key="ms_5m",
        type=StructureType.SWING,
        tf_role="exec",
        params={"left": 5, "right": 5},
        confirmation=ConfirmationConfig(mode="immediate"),
    )

    # Create TREND spec
    trend_spec = StructureSpec(
        key="trend_5m",
        type=StructureType.TREND,
        tf_role="exec",
        params={},
        confirmation=ConfirmationConfig(mode="immediate"),
    )

    console.print(f"  [green]OK[/] Created StructureSpecs:")
    console.print(f"      SWING: key='{swing_spec.key}', block_id='{swing_spec.block_id[:8]}...'")
    console.print(f"      TREND: key='{trend_spec.key}', block_id='{trend_spec.block_id[:8]}...'")

    # Build structures
    builder = StructureBuilder(stage=2)

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
        params={"left": 5, "right": 5},
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
        equity_usdt = 10000.0
        available_balance_usdt = 10000.0
        position = None
        unrealized_pnl_usdt = 0.0
        entries_disabled = False

    # Test snapshot access at various bar indices
    test_indices = [100, 250, sample_bars - 1]

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
    # Step 7: Test strict allowlist (unknown fields must hard-fail)
    # =========================================================================
    console.print(f"\n[bold]Step 7: Test Strict Allowlist (Unknown Fields Hard-Fail)[/]")

    snapshot = RuntimeSnapshotView(
        feeds=multi_feed,
        exec_idx=100,
        htf_idx=None,
        mtf_idx=None,
        exchange=MockExchange(),
        mark_price=close[100],
        mark_price_source="close",
    )

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

    # Test zones namespace (Stage 5+, should fail)
    try:
        snapshot.get("structure.ms_5m.zones.demand_1.level")
        console.print(f"  [red]FAIL[/] Zones should raise ValueError (Stage 5+)")
        failures += 1
    except ValueError as e:
        console.print(f"  [green]OK[/] Zones correctly rejected (Stage 5+)")
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
    # Step 10: Test pure function (detect_swing_pivots)
    # =========================================================================
    console.print(f"\n[bold]Step 10: Test Pure Function (detect_swing_pivots)[/]")

    try:
        is_swing_high, is_swing_low = detect_swing_pivots(high, low, left=5, right=5)
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
    console.print(f"\n{'='*60}")
    console.print(f"[bold cyan]MARKET STRUCTURE SMOKE TEST COMPLETE (Stage 2)[/]")
    console.print(f"{'='*60}")

    console.print(f"\n[bold]Summary:[/]")
    console.print(f"  Bars tested: {sample_bars}")
    console.print(f"  Swing params: left={params['left']}, right={params['right']}")
    console.print(f"  Swing highs confirmed: {num_high_confirmed + num_both_confirmed}")
    console.print(f"  Swing lows confirmed: {num_low_confirmed + num_both_confirmed}")
    console.print(f"  Trend transitions: {parent_version.max()}")
    console.print(f"  Failures: {failures}")

    console.print(f"\n[bold]Stage 2 Checklist:[/]")
    console.print(f"  [green]OK[/] StructureBuilder orchestrates SWING + TREND")
    console.print(f"  [green]OK[/] Public field names (swing_high_level, not high_level)")
    console.print(f"  [green]OK[/] FeedStore.structures populated")
    console.print(f"  [green]OK[/] snapshot.get('structure.<key>.<field>') works")
    console.print(f"  [green]OK[/] Strict allowlist (unknown fields hard-fail)")
    console.print(f"  [green]OK[/] tf_role='exec' enforced (Stage 2)")
    console.print(f"  [green]OK[/] Zones rejected (Stage 5+)")

    if failures == 0:
        console.print(f"\n[bold green]OK[/] STAGE 2 MARKET STRUCTURE VERIFIED")
    else:
        console.print(f"\n[bold red]FAIL[/] {failures} failure(s)")

    return failures
