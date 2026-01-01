# =============================================================================
# INDICATOR METADATA SMOKE TEST
# =============================================================================
"""
Indicator Metadata v1 smoke test module.

Validates the metadata system end-to-end using synthetic data:
1. Generate deterministic synthetic OHLCV data
2. Build FeatureArrays with FeatureFrameBuilder
3. Build FeedStore with metadata
4. Run validations (coverage, key match, ID consistency)
5. Export metadata to chosen format
"""

from rich.console import Console
from rich.panel import Panel

console = Console()


def _parse_tf_to_minutes(tf: str) -> int:
    """Parse timeframe string to minutes."""
    tf = tf.lower().strip()

    if tf.endswith('m'):
        return int(tf[:-1])
    elif tf.endswith('h'):
        return int(tf[:-1]) * 60
    elif tf.endswith('d'):
        return int(tf[:-1]) * 1440
    elif tf.isdigit():
        return int(tf)  # Assume minutes
    else:
        return 15  # Default to 15 minutes


def run_metadata_smoke(
    symbol: str = "BTCUSDT",
    tf: str = "15",
    sample_bars: int = 2000,
    seed: int = 1337,
    export_path: str = "artifacts/indicator_metadata.jsonl",
    export_format: str = "jsonl",
) -> int:
    """
    Run the Indicator Metadata v1 smoke test.

    Validates the metadata system end-to-end using synthetic data:
    1. Generate deterministic synthetic OHLCV data
    2. Build FeatureArrays with FeatureFrameBuilder
    3. Build FeedStore with metadata
    4. Run validations (coverage, key match, ID consistency)
    5. Export metadata to chosen format

    Args:
        symbol: Symbol for synthetic data (default: BTCUSDT)
        tf: Timeframe string (default: 15)
        sample_bars: Number of bars to generate (default: 2000)
        seed: Random seed for reproducibility (default: 1337)
        export_path: Path for metadata export (default: artifacts/indicator_metadata.jsonl)
        export_format: Export format - jsonl, json, or csv (default: jsonl)

    Returns:
        Exit code: 0 = success, 1 = validation failure, 2 = export failure
    """
    import numpy as np
    import pandas as pd
    from pathlib import Path
    from datetime import datetime, timezone, timedelta

    console.print(Panel(
        "[bold cyan]INDICATOR METADATA v1 SMOKE TEST[/]\n"
        "[dim]Validates metadata capture, invariants, and export[/]",
        border_style="cyan"
    ))

    console.print(f"\n[bold]Configuration:[/]")
    console.print(f"  Symbol: {symbol}")
    console.print(f"  Timeframe: {tf}")
    console.print(f"  Sample Bars: {sample_bars:,}")
    console.print(f"  Seed: {seed}")
    console.print(f"  Export Path: {export_path}")
    console.print(f"  Export Format: {export_format}")

    failures = 0

    # =========================================================================
    # STEP 1: Generate synthetic OHLCV data
    # =========================================================================
    console.print(f"\n[bold cyan]Step 1: Generate Synthetic OHLCV Data[/]")

    try:
        np.random.seed(seed)

        # Generate timestamps (15-min bars by default)
        tf_minutes = _parse_tf_to_minutes(tf)
        start_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        timestamps = [start_time + timedelta(minutes=i * tf_minutes) for i in range(sample_bars)]

        # Generate price data (random walk)
        base_price = 40000.0  # Starting price
        returns = np.random.randn(sample_bars) * 0.002  # 0.2% std per bar
        prices = base_price * np.cumprod(1 + returns)

        # Generate OHLCV
        high_noise = np.abs(np.random.randn(sample_bars)) * 0.001
        low_noise = np.abs(np.random.randn(sample_bars)) * 0.001

        df = pd.DataFrame({
            'timestamp': timestamps,
            'open': prices * (1 - np.random.rand(sample_bars) * 0.001),
            'high': prices * (1 + high_noise),
            'low': prices * (1 - low_noise),
            'close': prices,
            'volume': np.abs(np.random.randn(sample_bars)) * 1000000 + 500000,
        })

        # Ensure high >= max(open, close) and low <= min(open, close)
        df['high'] = df[['open', 'close', 'high']].max(axis=1)
        df['low'] = df[['open', 'close', 'low']].min(axis=1)

        console.print(f"  [green]OK[/] Generated {len(df):,} bars")
        console.print(f"      Start: {df['timestamp'].iloc[0]}")
        console.print(f"      End: {df['timestamp'].iloc[-1]}")
        console.print(f"      Price range: ${df['close'].min():,.2f} - ${df['close'].max():,.2f}")

    except Exception as e:
        console.print(f"  [red]FAIL[/] Error generating data: {e}")
        return 2

    # =========================================================================
    # STEP 2: Build FeatureArrays with FeatureFrameBuilder
    # =========================================================================
    console.print(f"\n[bold cyan]Step 2: Build Features with Metadata[/]")

    try:
        from ...backtest.features.feature_spec import (
            FeatureSpec,
            FeatureSpecSet,
            InputSource,
        )
        from ...backtest.features.feature_frame_builder import FeatureFrameBuilder

        # Create a diverse set of FeatureSpecs (single + multi-output)
        # Using string indicator types (registry-based, as of Phase 2)
        specs = [
            # Single-output indicators
            FeatureSpec(
                indicator_type="ema",
                output_key='ema_20',
                params={'length': 20},
                input_source=InputSource.CLOSE,
            ),
            FeatureSpec(
                indicator_type="ema",
                output_key='ema_50',
                params={'length': 50},
                input_source=InputSource.CLOSE,
            ),
            FeatureSpec(
                indicator_type="rsi",
                output_key='rsi_14',
                params={'length': 14},
                input_source=InputSource.CLOSE,
            ),
            FeatureSpec(
                indicator_type="atr",
                output_key='atr_14',
                params={'length': 14},
            ),
            # Multi-output indicators
            FeatureSpec(
                indicator_type="macd",
                output_key='macd',
                params={'fast': 12, 'slow': 26, 'signal': 9},
                input_source=InputSource.CLOSE,
            ),
            FeatureSpec(
                indicator_type="bbands",
                output_key='bb',
                params={'length': 20, 'std': 2.0},
                input_source=InputSource.CLOSE,
            ),
        ]

        spec_set = FeatureSpecSet(symbol=symbol, tf=tf, specs=specs)

        # Build features with metadata
        builder = FeatureFrameBuilder()
        arrays = builder.build(df, spec_set, tf_role='exec')

        console.print(f"  [green]OK[/] Built {len(arrays.arrays)} indicator arrays")
        console.print(f"      Keys: {list(arrays.arrays.keys())}")
        console.print(f"      Metadata keys: {list(arrays.metadata.keys())}")

    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error building features: {e}")
        traceback.print_exc()
        return 2

    # =========================================================================
    # STEP 3: Build FeedStore with metadata
    # =========================================================================
    console.print(f"\n[bold cyan]Step 3: Build FeedStore[/]")

    try:
        from ...backtest.runtime.feed_store import FeedStore

        feed_store = FeedStore.from_dataframe_with_features(
            df=df,
            tf=tf,
            symbol=symbol,
            feature_arrays=arrays,
        )

        console.print(f"  [green]OK[/] FeedStore built")
        console.print(f"      Length: {feed_store.length:,} bars")
        console.print(f"      Indicators: {len(feed_store.indicators)}")
        console.print(f"      Metadata entries: {len(feed_store.indicator_metadata)}")

    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error building FeedStore: {e}")
        traceback.print_exc()
        return 2

    # =========================================================================
    # STEP 4: Validate metadata invariants
    # =========================================================================
    console.print(f"\n[bold cyan]Step 4: Validate Metadata Invariants[/]")

    try:
        from ...backtest.runtime.indicator_metadata import (
            validate_metadata_coverage,
            validate_feature_spec_ids,
        )

        # 4.1: Coverage check
        console.print(f"\n  [bold]4.1: Coverage Check[/]")
        coverage_ok = validate_metadata_coverage(feed_store)
        if coverage_ok:
            console.print(f"      [green]OK[/] indicator_keys == metadata_keys")
        else:
            console.print(f"      [red]FAIL[/] Coverage mismatch")
            indicator_keys = set(feed_store.indicators.keys())
            metadata_keys = set(feed_store.indicator_metadata.keys())
            console.print(f"          Missing metadata: {indicator_keys - metadata_keys}")
            console.print(f"          Extra metadata: {metadata_keys - indicator_keys}")
            failures += 1

        # 4.2: Full validation (coverage + key match + ID consistency)
        console.print(f"\n  [bold]4.2: Full Validation[/]")
        validation_result = validate_feature_spec_ids(feed_store)

        if validation_result.is_valid:
            console.print(f"      [green]OK[/] All invariants pass")
        else:
            if not validation_result.coverage_ok:
                console.print(f"      [red]FAIL[/] Coverage: missing={validation_result.missing_metadata}, extra={validation_result.extra_metadata}")
                failures += 1
            if not validation_result.ids_consistent:
                console.print(f"      [red]FAIL[/] ID consistency issues:")
                for mismatch in validation_result.id_mismatches:
                    console.print(f"          {mismatch['indicator_key']}: stored={mismatch['stored_id']} != recomputed={mismatch['recomputed_id']}")
                for key_mismatch in validation_result.key_mismatches:
                    console.print(f"          Key mismatch: {key_mismatch}")
                failures += 1

        # 4.3: Sample metadata display
        console.print(f"\n  [bold]4.3: Sample Metadata[/]")
        sample_keys = list(feed_store.indicator_metadata.keys())[:3]
        for key in sample_keys:
            meta = feed_store.indicator_metadata[key]
            console.print(f"      {key}:")
            console.print(f"        feature_spec_id: {meta.feature_spec_id}")
            console.print(f"        indicator_type: {meta.indicator_type}")
            console.print(f"        params: {meta.params}")
            console.print(f"        first_valid_idx: {meta.first_valid_idx_observed}")
            console.print(f"        pandas_ta_version: {meta.pandas_ta_version}")

        # 4.4: Multi-output shared ID check
        console.print(f"\n  [bold]4.4: Multi-Output Shared ID Check[/]")
        macd_keys = [k for k in feed_store.indicator_metadata.keys() if k.startswith('macd_')]
        if macd_keys:
            macd_ids = [feed_store.indicator_metadata[k].feature_spec_id for k in macd_keys]
            if len(set(macd_ids)) == 1:
                console.print(f"      [green]OK[/] MACD outputs share ID: {macd_ids[0]}")
            else:
                console.print(f"      [red]FAIL[/] MACD outputs have different IDs: {macd_ids}")
                failures += 1

        bb_keys = [k for k in feed_store.indicator_metadata.keys() if k.startswith('bb_')]
        if bb_keys:
            bb_ids = [feed_store.indicator_metadata[k].feature_spec_id for k in bb_keys]
            if len(set(bb_ids)) == 1:
                console.print(f"      [green]OK[/] BBands outputs share ID: {bb_ids[0]}")
            else:
                console.print(f"      [red]FAIL[/] BBands outputs have different IDs: {bb_ids}")
                failures += 1

    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error during validation: {e}")
        traceback.print_exc()
        failures += 1

    # =========================================================================
    # STEP 5: Export metadata
    # =========================================================================
    console.print(f"\n[bold cyan]Step 5: Export Metadata[/]")

    try:
        from ...backtest.runtime.indicator_metadata import (
            export_metadata_jsonl,
            export_metadata_json,
            export_metadata_csv,
        )

        export_path_obj = Path(export_path)
        export_path_obj.parent.mkdir(parents=True, exist_ok=True)

        if export_format == "jsonl":
            export_metadata_jsonl(feed_store, export_path_obj)
        elif export_format == "json":
            export_metadata_json(feed_store, export_path_obj)
        elif export_format == "csv":
            export_metadata_csv(feed_store, export_path_obj)
        else:
            console.print(f"  [red]FAIL[/] Unknown format: {export_format}")
            return 2

        # Verify file exists and has content
        if export_path_obj.exists():
            file_size = export_path_obj.stat().st_size
            console.print(f"  [green]OK[/] Exported to {export_path}")
            console.print(f"      Format: {export_format}")
            console.print(f"      Size: {file_size:,} bytes")

            # Show preview
            with open(export_path_obj, 'r') as f:
                preview = f.read(500)
                console.print(f"      Preview (first 500 chars):")
                console.print(f"      [dim]{preview}...[/]" if len(preview) == 500 else f"      [dim]{preview}[/]")
        else:
            console.print(f"  [red]FAIL[/] Export file not created")
            return 2

    except Exception as e:
        import traceback
        console.print(f"  [red]FAIL[/] Error during export: {e}")
        traceback.print_exc()
        return 2

    # =========================================================================
    # SUMMARY
    # =========================================================================
    console.print(f"\n[bold cyan]{'='*60}[/]")
    console.print(f"[bold cyan]INDICATOR METADATA SMOKE TEST COMPLETE[/]")
    console.print(f"[bold cyan]{'='*60}[/]")

    console.print(f"\n[bold]Summary:[/]")
    console.print(f"  Symbol: {symbol}")
    console.print(f"  Timeframe: {tf}")
    console.print(f"  Bars: {sample_bars:,}")
    console.print(f"  Indicators: {len(feed_store.indicators)}")
    console.print(f"  Metadata entries: {len(feed_store.indicator_metadata)}")
    console.print(f"  Export: {export_path}")
    console.print(f"  Failures: {failures}")

    if failures == 0:
        console.print(f"\n[bold green]OK INDICATOR METADATA v1 VERIFIED[/]")
        return 0
    else:
        console.print(f"\n[bold red]FAIL {failures} VALIDATION(S) FAILED[/]")
        return 1
