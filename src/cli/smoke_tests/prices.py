"""
Price-related smoke tests.

Contains:
- run_mark_price_smoke: Validates MarkPriceEngine and SimMarkProvider
"""

from rich.console import Console
from rich.panel import Panel

console = Console()


def run_mark_price_smoke(
    sample_bars: int = 500,
    seed: int = 42,
) -> int:
    """
    Run the Mark Price Engine smoke test.

    Validates the MarkPriceEngine and SimMarkProvider end-to-end:
    1. Generate deterministic synthetic OHLCV data
    2. Create MarkPriceEngine with SimMarkProvider
    3. Validate mark price retrieval works
    4. Validate determinism (same result on rerun)
    5. Validate healthcheck and resolution logging
    6. Validate snapshot.get("price.mark.close") integration

    Args:
        sample_bars: Number of bars to generate (default: 500)
        seed: Random seed for reproducibility (default: 42)

    Returns:
        Exit code: 0 = success, 1 = validation failure, 2 = setup failure
    """
    import numpy as np
    import pandas as pd
    from datetime import datetime, timezone, timedelta

    console.print(Panel(
        "[bold cyan]MARK PRICE ENGINE SMOKE TEST[/]\n"
        "[dim]Validates MarkPriceEngine, SimMarkProvider, and snapshot.get()[/]",
        border_style="cyan"
    ))

    console.print(f"\n[bold]Configuration:[/]")
    console.print(f"  Sample Bars: {sample_bars:,}")
    console.print(f"  Seed: {seed}")

    failures = 0

    # =========================================================================
    # STEP 1: Generate synthetic OHLCV data
    # =========================================================================
    console.print(f"\n[bold cyan]Step 1: Generate Synthetic OHLCV Data[/]")

    try:
        np.random.seed(seed)

        # Generate timestamps (15-min bars)
        tf_minutes = 15
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        timestamps = [start_time + timedelta(minutes=i * tf_minutes) for i in range(sample_bars)]

        # Convert to milliseconds for ts_close
        ts_close_array = np.array([int(ts.timestamp() * 1000) for ts in timestamps], dtype=np.int64)

        # Generate price data (random walk)
        base_price = 40000.0
        returns = np.random.randn(sample_bars) * 0.002
        close_array = base_price * np.cumprod(1 + returns)

        console.print(f"  [green]OK[/] Generated {sample_bars:,} bars")
        console.print(f"      Start: {timestamps[0]}")
        console.print(f"      End: {timestamps[-1]}")
        console.print(f"      Price range: ${close_array.min():,.2f} - ${close_array.max():,.2f}")

    except Exception as e:
        console.print(f"  [red]FAIL[/] Error generating data: {e}")
        return 2

    # =========================================================================
    # STEP 2: Create MarkPriceEngine
    # =========================================================================
    console.print(f"\n[bold cyan]Step 2: Create MarkPriceEngine[/]")

    try:
        from ...backtest.prices import (
            MarkPriceEngine,
            SimMarkProvider,
            validate_mark_price_availability,
            log_mark_resolution,
        )

        engine = MarkPriceEngine.from_feed_arrays(ts_close_array, close_array)

        console.print(f"  [green]OK[/] MarkPriceEngine created")
        console.print(f"      Provider: {engine.provider_name}")

    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error creating engine: {e}")
        traceback.print_exc()
        return 2

    # =========================================================================
    # STEP 3: Validate mark price retrieval
    # =========================================================================
    console.print(f"\n[bold cyan]Step 3: Validate Mark Price Retrieval[/]")

    try:
        # Test retrieval at various timestamps
        test_indices = [0, 100, 250, sample_bars - 1]

        for idx in test_indices:
            ts = int(ts_close_array[idx])
            expected = float(close_array[idx])
            actual = engine.get_mark_close(ts)

            if abs(actual - expected) < 1e-10:
                console.print(f"  [green]OK[/] Bar {idx}: ts={ts} -> ${actual:,.2f}")
            else:
                console.print(f"  [red]FAIL[/] Bar {idx}: expected ${expected:,.2f}, got ${actual:,.2f}")
                failures += 1

        # Test missing timestamp raises
        try:
            engine.get_mark_close(999999999999)
            console.print(f"  [red]FAIL[/] Missing timestamp should raise ValueError")
            failures += 1
        except ValueError:
            console.print(f"  [green]OK[/] Missing timestamp correctly raises ValueError")

    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error during retrieval test: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # STEP 4: Validate determinism
    # =========================================================================
    console.print(f"\n[bold cyan]Step 4: Validate Determinism[/]")

    try:
        # Create second engine with same data
        engine2 = MarkPriceEngine.from_feed_arrays(ts_close_array, close_array)

        # Check all values match
        mismatches = 0
        for i in range(sample_bars):
            ts = int(ts_close_array[i])
            v1 = engine.get_mark_close(ts)
            v2 = engine2.get_mark_close(ts)
            if abs(v1 - v2) > 1e-10:
                mismatches += 1

        if mismatches == 0:
            console.print(f"  [green]OK[/] All {sample_bars} values match between engine instances")
        else:
            console.print(f"  [red]FAIL[/] {mismatches} mismatches found")
            failures += 1

    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error during determinism test: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # STEP 5: Validate healthcheck and validation
    # =========================================================================
    console.print(f"\n[bold cyan]Step 5: Validate Healthcheck & Validation[/]")

    try:
        # Healthcheck
        health = engine.healthcheck()
        if health.ok:
            console.print(f"  [green]OK[/] Healthcheck passed: {health.message}")
            console.print(f"      Details: {health.details}")
        else:
            console.print(f"  [red]FAIL[/] Healthcheck failed: {health.message}")
            failures += 1

        # Validation helper
        result = validate_mark_price_availability(engine)
        if result.ok:
            console.print(f"  [green]OK[/] Validation passed: {result.message}")
        else:
            console.print(f"  [red]FAIL[/] Validation failed: {result.message}")
            failures += 1

        # Log resolution (should only log once)
        engine.log_resolution()
        engine.log_resolution()  # Second call should be no-op
        console.print(f"  [green]OK[/] log_resolution() called (idempotent)")

    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error during healthcheck test: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # STEP 6: Validate snapshot.get() integration
    # =========================================================================
    console.print(f"\n[bold cyan]Step 6: Validate snapshot.get() Integration[/]")

    try:
        from ...backtest.runtime.snapshot_view import RuntimeSnapshotView
        from ...backtest.runtime.feed_store import FeedStore, MultiTFFeedStore

        # Build a minimal FeedStore from synthetic data
        df = pd.DataFrame({
            'timestamp': [datetime.fromtimestamp(ts/1000, tz=timezone.utc) for ts in ts_close_array],
            'open': close_array * 0.999,
            'high': close_array * 1.001,
            'low': close_array * 0.998,
            'close': close_array,
            'volume': np.ones(sample_bars) * 1000000,
        })

        feed_store = FeedStore.from_dataframe(
            df=df,
            tf="15m",
            symbol="BTCUSDT",
        )

        # Create MultiTFFeedStore (exec-only for this test)
        multi_feed = MultiTFFeedStore(
            exec_feed=feed_store,
            htf_feed=None,
            mtf_feed=None,
            tf_mapping={"exec": "15m"},
        )

        # Create snapshot at test index
        test_idx = 100
        test_ts = int(ts_close_array[test_idx])
        expected_mark = float(close_array[test_idx])

        # Get mark price from engine for snapshot
        mark_price, mark_source = engine.get_mark_for_snapshot(test_ts)

        # Create RuntimeSnapshotView
        snapshot = RuntimeSnapshotView(
            feeds=multi_feed,
            exec_idx=test_idx,
            htf_idx=None,
            mtf_idx=None,
            exchange=None,
            mark_price=mark_price,
            mark_price_source=mark_source,
        )

        # Test snapshot.get("price.mark.close")
        result = snapshot.get("price.mark.close")

        if result is not None and abs(result - expected_mark) < 1e-10:
            console.print(f"  [green]OK[/] snapshot.get('price.mark.close') = ${result:,.2f}")
        else:
            console.print(f"  [red]FAIL[/] Expected ${expected_mark:,.2f}, got {result}")
            failures += 1

        # Verify mark_price_source
        if snapshot.mark_price_source == "backtest_exec_close":
            console.print(f"  [green]OK[/] mark_price_source = '{snapshot.mark_price_source}'")
        else:
            console.print(f"  [red]FAIL[/] Expected 'backtest_exec_close', got '{snapshot.mark_price_source}'")
            failures += 1

    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error during snapshot integration test: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # SUMMARY
    # =========================================================================
    console.print(f"\n[bold cyan]{'='*60}[/]")
    console.print(f"[bold cyan]MARK PRICE ENGINE SMOKE TEST COMPLETE[/]")
    console.print(f"[bold cyan]{'='*60}[/]")

    console.print(f"\n[bold]Summary:[/]")
    console.print(f"  Bars tested: {sample_bars:,}")
    console.print(f"  Provider: {engine.provider_name}")
    console.print(f"  Failures: {failures}")

    if failures == 0:
        console.print(f"\n[bold green]OK MARK PRICE ENGINE VERIFIED[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {failures} VALIDATION(S) FAILED[/]")
        return 1
