"""
Backtest Runner with Gate Enforcement.

The canonical runner for executing Play-based backtests.
Enforces all gates before and after the run:

1. Data Preflight Gate (before run)
   - Validates data availability for all TFs
   - Checks timestamps, gaps, alignment
   - Writes preflight_report.json

2. Backtest Execution
   - Runs the backtest engine
   - Produces trades, equity curve, events

3. Artifact Export Gate (after run)
   - Validates all required files exist
   - Checks column headers
   - Validates result.json fields

4. Results Summary
   - Prints console summary
   - Writes result.json

If any gate fails, the runner stops and returns a failure status.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from pathlib import Path
import json
import time


def _utcnow() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)

import pandas as pd

from .play import Play, load_play
from .runtime.preflight import (
    PreflightStatus,
    PreflightReport,
    run_preflight_gate,
    DataLoader,
)
from .artifacts.artifact_standards import (
    ArtifactPathConfig,
    ArtifactValidationResult,
    validate_artifacts,
    validate_artifact_path_config,
    ResultsSummary,
    compute_results_summary,
    STANDARD_FILES,
    RunManifest,
)
from .artifacts.hashes import (
    compute_trades_hash,
    compute_equity_hash,
    compute_run_hash,
    InputHashComponents,
)
from .artifacts.parquet_writer import write_parquet
from .gates.indicator_requirements_gate import (
    validate_indicator_requirements,
    IndicatorGateStatus,
    IndicatorRequirementsResult,
)
from .execution_validation import (
    validate_play_full,
    compute_warmup_requirements,
    compute_play_hash,
    PlaySignalEvaluator,
    SignalDecision,
)
from .logging import RunLogger, set_run_logger


class GateFailure(Exception):
    """
    Raised when a validation gate fails during backtest execution.

    Gates are pre-execution checks that validate Play configuration,
    data availability, and engine state before running a backtest.
    """


# =============================================================================
# Pipeline Version (for artifact tracking)
# =============================================================================
# Import from canonical source - single source of truth
from .artifacts.pipeline_signature import PIPELINE_VERSION


@dataclass
class _RunContext:
    """Internal context passed between helper functions during a backtest run."""
    # Core objects
    play: Play | None = None
    config: "RunnerConfig | None" = None
    result: "RunnerResult | None" = None

    # Computed values
    symbol: str = ""
    exec_tf: str = ""
    play_hash: str = ""
    run_id: str = ""
    data_source_id: str = ""

    # Artifact setup
    artifact_path: Path | None = None
    manifest: RunManifest | None = None

    # Preflight results
    preflight_warmup_by_role: dict[str, int] | None = None
    preflight_delay_by_role: dict[str, int] | None = None

    # Engine results
    engine: Any = None
    engine_result: Any = None
    trades: list[dict[str, Any]] = field(default_factory=list)
    equity_curve: list[dict[str, Any]] = field(default_factory=list)

    # Timing
    run_start_time: float = 0.0

    # Logger
    run_logger: RunLogger | None = None


# =============================================================================
# G4.1 Refactor: Helper functions for run_backtest_with_gates
# =============================================================================

def _setup_synthetic_provider(
    play: Play,
    config: "RunnerConfig",
    synthetic_provider: "SyntheticDataProvider | None",
) -> "SyntheticDataProvider | None":
    """
    Setup synthetic data provider if Play has synthetic config.

    Returns updated synthetic_provider (may be newly created or passed through).
    Also modifies config.window_start/end and config.skip_preflight if synthetic.
    """
    if play.synthetic is None or synthetic_provider is not None:
        return synthetic_provider

    from src.forge.validation import generate_synthetic_candles
    from src.forge.validation.synthetic_provider import SyntheticCandlesProvider

    # Collect required timeframes
    exec_tf = play.execution_tf
    required_tfs = {exec_tf, "1m"}  # Always need exec and 1m
    if play.low_tf:
        required_tfs.add(play.low_tf)
    if play.med_tf:
        required_tfs.add(play.med_tf)
    if play.high_tf:
        required_tfs.add(play.high_tf)
    for tf in play.feature_registry.get_all_tfs():
        required_tfs.add(tf)

    print(f"[SYNTHETIC] Auto-generating data for Play with synthetic config")
    print(f"[SYNTHETIC] Pattern: {play.synthetic.pattern}, Bars: {play.synthetic.bars}, Seed: {play.synthetic.seed}")
    print(f"[SYNTHETIC] Required TFs: {sorted(required_tfs)}")

    # Generate synthetic candles
    candles = generate_synthetic_candles(
        symbol=play.symbol_universe[0] if play.symbol_universe else "BTCUSDT",
        timeframes=list(required_tfs),
        bars_per_tf=play.synthetic.bars,
        seed=play.synthetic.seed,
        pattern=play.synthetic.pattern,
    )

    # Create provider and set window from synthetic data
    new_provider = SyntheticCandlesProvider(candles)
    data_start, data_end = new_provider.get_data_range(exec_tf)
    config.window_start = data_start
    config.window_end = data_end
    config.skip_preflight = True  # No DB data to validate

    print(f"[SYNTHETIC] Data range: {config.window_start} to {config.window_end}")
    print(f"[SYNTHETIC] Data hash: {candles.data_hash}")

    return new_provider


def _resolve_window(play: Play, config: "RunnerConfig") -> None:
    """
    Auto-infer window from DB coverage if not provided.

    Modifies config.window_start and config.window_end in place.
    Raises ValueError if window cannot be determined.
    """
    if config.window_start and config.window_end:
        return  # Already set

    from src.data.historical_data_store import get_historical_store

    if not play.symbol_universe:
        raise ValueError("Play has no symbols in symbol_universe")

    symbol = play.symbol_universe[0]
    tf = play.execution_tf

    store = get_historical_store()
    status = store.status(symbol)
    key = f"{symbol}_{tf}"

    if key in status:
        info = status[key]
        first_ts = info.get("first_timestamp")
        last_ts = info.get("last_timestamp")
        if first_ts and last_ts:
            config.window_start = config.window_start or first_ts
            config.window_end = config.window_end or last_ts

    # Validate after inference attempt
    if not config.window_start or not config.window_end:
        raise ValueError(
            f"window_start and window_end are required. "
            f"No data found for {symbol} {tf}. Use --start/--end or sync data first."
        )


def _create_artifact_setup(
    play: Play,
    config: "RunnerConfig",
    synthetic_provider: "SyntheticDataProvider | None",
) -> tuple[Path, str, str, str, InputHashComponents, RunManifest]:
    """
    Create artifact path config, compute hashes, create manifest.

    Returns: (artifact_path, run_id, play_hash, data_source_id, input_components, manifest)
    """
    play_hash = compute_play_hash(play)
    exec_tf = play.execution_tf
    tf_ctx = sorted(play.feature_registry.get_all_tfs())

    # Determine data source ID
    data_source_id = "synthetic" if synthetic_provider is not None else "duckdb_live"

    # Build input hash components
    input_components = InputHashComponents(
        play_hash=play_hash,
        symbols=play.symbol_universe,
        tf_exec=exec_tf,
        tf_ctx=tf_ctx,
        window_start=config.window_start.strftime("%Y-%m-%d"),
        window_end=config.window_end.strftime("%Y-%m-%d"),
        fee_model_version="1.0.0",
        simulator_version="1.0.0",
        engine_version=PIPELINE_VERSION,
        fill_policy_version="1.0.0",
        data_source_id=data_source_id,
        data_version=None,
        candle_policy="closed_only",
        seed=None,
    )

    # Compute hashes
    full_hash = input_components.compute_full_hash()
    short_hash = input_components.compute_short_hash()
    short_hash_length = len(short_hash)
    universe_id = input_components.universe_id

    # Setup artifact path
    artifact_config = ArtifactPathConfig(
        base_dir=config.base_output_dir,
        category="_validation",
        play_id=play.id,
        universe_id=universe_id,
        tf_exec=exec_tf,
        window_start=config.window_start,
        window_end=config.window_end,
        run_id=short_hash,
        play_hash=play_hash,
        short_hash_length=short_hash_length,
    )
    run_id = artifact_config.run_id

    # Validate artifact config
    path_errors = validate_artifact_path_config(artifact_config)
    if path_errors:
        raise ValueError(f"Invalid artifact config: {'; '.join(path_errors)}")

    # Create output folder
    artifact_path = artifact_config.create_folder()

    # Create RunManifest
    manifest = RunManifest(
        full_hash=full_hash,
        short_hash=short_hash,
        short_hash_length=short_hash_length,
        hash_algorithm="sha256",
        play_id=play.id,
        play_hash=play_hash,
        symbols=play.symbol_universe,
        universe_id=universe_id,
        tf_exec=exec_tf,
        tf_ctx=tf_ctx,
        window_start=config.window_start.strftime("%Y-%m-%d"),
        window_end=config.window_end.strftime("%Y-%m-%d"),
        fee_model_version="1.0.0",
        simulator_version="1.0.0",
        engine_version=PIPELINE_VERSION,
        fill_policy_version="1.0.0",
        data_source_id=data_source_id,
        data_version=None,
        candle_policy="closed_only",
        seed=None,
        category="_validation",
        is_promotable=False,
        allows_overwrite=True,
        attempt_id=None,
    )
    manifest.write_json(artifact_path / "run_manifest.json")

    return artifact_path, run_id, play_hash, data_source_id, input_components, manifest


def _run_preflight_gate(
    ctx: _RunContext,
) -> PreflightReport | None:
    """
    Run the data preflight gate.

    Returns PreflightReport if run, None if skipped.
    Raises GateFailure if preflight fails.
    """
    config = ctx.config
    play = ctx.play
    artifact_path = ctx.artifact_path
    manifest = ctx.manifest
    result = ctx.result

    if config.skip_preflight:
        print("\n[WARN] --skip-preflight bypasses ALL data validation!")
        print("[WARN] Use only for testing. Production runs MUST use preflight gate.")
        return None

    if not config.data_loader:
        raise ValueError("data_loader is required for preflight gate")

    print("\n[PREFLIGHT] Running Data Preflight Gate...")

    preflight_report = run_preflight_gate(
        play=play,
        data_loader=config.data_loader,
        window_start=config.window_start,
        window_end=config.window_end,
        gap_threshold_multiplier=3.0,
        auto_sync_missing=config.auto_sync_missing_data,
    )

    result.preflight_report = preflight_report

    # Write preflight report
    preflight_path = artifact_path / STANDARD_FILES["preflight"]
    preflight_report.write_json(preflight_path)

    # Print summary
    preflight_report.print_summary()

    # Check gate
    if preflight_report.overall_status == PreflightStatus.FAILED:
        result.gate_failed = "preflight"
        result.error_message = "Data preflight gate failed - see preflight_report.json for details"
        raise GateFailure(result.error_message)

    # Update manifest with warmup data
    if preflight_report.computed_warmup_requirements:
        manifest.computed_lookback_bars_by_role = preflight_report.computed_warmup_requirements.warmup_by_role
        manifest.computed_delay_bars_by_role = preflight_report.computed_warmup_requirements.delay_by_role
    if preflight_report.auto_sync_result and preflight_report.auto_sync_result.tool_calls:
        manifest.warmup_tool_calls = [tc.to_dict() for tc in preflight_report.auto_sync_result.tool_calls]
    manifest.write_json(artifact_path / "run_manifest.json")

    return preflight_report


def _run_indicator_gate(play: Play, result: "RunnerResult") -> None:
    """
    Run the indicator requirements gate.

    Raises GateFailure if indicator requirements not met.
    """
    registry = play.feature_registry
    has_features = len(list(registry.all_features())) > 0

    if not has_features:
        print("\n[INDICATOR GATE] Skipped - no features declared")
        return

    print("\n[INDICATOR GATE] Validating Indicator Requirements...")

    # Build available keys from feature registry
    available_keys_by_role: dict[str, set] = {}
    for tf in registry.get_all_tfs():
        features = registry.get_for_tf(tf)
        keys = set()
        for f in features:
            keys.add(f.id)
            if f.output_keys:
                keys.update(f.output_keys)
        available_keys_by_role[tf] = keys

    # Validate required vs available
    indicator_gate_result = validate_indicator_requirements(
        play=play,
        available_keys_by_role=available_keys_by_role,
    )

    # Print result
    if indicator_gate_result.passed:
        print("  [PASS] All required indicators are declared in features")
    elif indicator_gate_result.status == IndicatorGateStatus.SKIPPED:
        print("  [SKIP] No features declared in Play")
    else:
        print(indicator_gate_result.format_error())
        result.gate_failed = "indicator_requirements"
        result.error_message = indicator_gate_result.error_message
        raise GateFailure(result.error_message)


def _get_warmup_config(
    result: "RunnerResult",
    config: "RunnerConfig",
    play: Play,
) -> tuple[dict[str, int] | None, dict[str, int] | None]:
    """
    Extract warmup and delay configuration from preflight or compute directly.

    Returns: (warmup_by_role, delay_by_role)
    """
    if result.preflight_report and result.preflight_report.computed_warmup_requirements:
        warmup_by_role = result.preflight_report.computed_warmup_requirements.warmup_by_role
        delay_by_role = result.preflight_report.computed_warmup_requirements.delay_by_role
        print(f"[WARMUP] Using Preflight warmup: {warmup_by_role}")
        if delay_by_role and any(v > 0 for v in delay_by_role.values()):
            print(f"[DELAY] Using Preflight delay: {delay_by_role}")
        return warmup_by_role, delay_by_role

    # Preflight skipped or no warmup computed
    if not config.skip_preflight:
        raise ValueError(
            "MISSING_PREFLIGHT_WARMUP: Preflight passed but no computed_warmup_requirements found. "
            "This indicates a bug in the Preflight gate."
        )

    # For skip_preflight mode (testing only)
    print("[WARN] Preflight skipped - computing warmup directly (testing mode only)")
    warmup_reqs = compute_warmup_requirements(play)
    return warmup_reqs.warmup_by_role, warmup_reqs.delay_by_role


def _execute_backtest(
    ctx: _RunContext,
    synthetic_provider: "SyntheticDataProvider | None",
) -> None:
    """
    Create engine and run backtest.

    Updates ctx with engine, engine_result, trades, equity_curve.
    """
    from .engine_factory import create_engine_from_play, run_engine_with_play

    print("\n[RUN] Running Backtest...")

    # Create engine and run
    engine = create_engine_from_play(
        play=ctx.play,
        window_start=ctx.config.window_start,
        window_end=ctx.config.window_end,
        warmup_by_tf=ctx.preflight_warmup_by_role,
        synthetic_provider=synthetic_provider,
        data_env=ctx.config.data_env,
    )
    engine.set_play_hash(ctx.play_hash)
    engine_result = run_engine_with_play(engine, ctx.play)

    # Extract trades and equity
    trades: list[dict[str, Any]] = []
    equity_curve: list[dict[str, Any]] = []

    if hasattr(engine_result, 'trades'):
        trades = [t.to_dict() if hasattr(t, 'to_dict') else t for t in engine_result.trades]
    if hasattr(engine_result, 'equity_curve'):
        equity_curve = [e.to_dict() if hasattr(e, 'to_dict') else e for e in engine_result.equity_curve]
    if hasattr(engine_result, 'play_hash'):
        ctx.play_hash = engine_result.play_hash
    else:
        ctx.play_hash = compute_play_hash(ctx.play)

    ctx.engine = engine
    ctx.engine_result = engine_result
    ctx.trades = trades
    ctx.equity_curve = equity_curve


def _write_trade_artifacts(ctx: _RunContext) -> int | None:
    """
    Write trades.parquet and equity.parquet.

    Returns eval_start_ts_ms for manifest.
    """
    artifact_path = ctx.artifact_path

    # Write trades.parquet
    trades_df = pd.DataFrame(ctx.trades) if ctx.trades else pd.DataFrame(columns=[
        "entry_time", "exit_time", "side", "entry_price", "exit_price",
        "entry_size_usdt", "net_pnl", "stop_loss", "take_profit", "exit_reason",
    ])
    write_parquet(trades_df, artifact_path / "trades.parquet")

    # Write equity.parquet
    equity_df = pd.DataFrame(ctx.equity_curve) if ctx.equity_curve else pd.DataFrame(columns=[
        "timestamp", "equity",
    ])

    # Add ts_ms column
    if not equity_df.empty and "timestamp" in equity_df.columns:
        equity_df["ts_ms"] = pd.to_datetime(equity_df["timestamp"]).astype("int64") // 10**6
    else:
        equity_df["ts_ms"] = pd.Series(dtype="int64")

    write_parquet(equity_df, artifact_path / "equity.parquet")

    # Extract eval_start_ts_ms
    eval_start_ts_ms = None
    if hasattr(ctx.engine_result, 'metrics') and ctx.engine_result.metrics:
        if hasattr(ctx.engine_result.metrics, 'simulation_start'):
            sim_start = ctx.engine_result.metrics.simulation_start
            if sim_start is not None:
                if hasattr(sim_start, 'timestamp'):
                    eval_start_ts_ms = int(sim_start.timestamp() * 1000)
                elif isinstance(sim_start, (int, float)):
                    eval_start_ts_ms = int(sim_start)

    # Fallback to first equity timestamp
    if eval_start_ts_ms is None and not equity_df.empty and "ts_ms" in equity_df.columns:
        first_ts = equity_df["ts_ms"].iloc[0]
        if pd.notna(first_ts):
            eval_start_ts_ms = int(first_ts)

    return eval_start_ts_ms


def _write_results_summary(ctx: _RunContext) -> ResultsSummary:
    """
    Compute and write results summary.

    Returns ResultsSummary.
    """
    run_duration = time.time() - ctx.run_start_time

    # Compute hashes
    trades_hash = ""
    equity_hash = ""
    if hasattr(ctx.engine_result, 'trades') and ctx.engine_result.trades:
        trades_hash = compute_trades_hash(ctx.engine_result.trades)
    if hasattr(ctx.engine_result, 'equity_curve') and ctx.engine_result.equity_curve:
        equity_hash = compute_equity_hash(ctx.engine_result.equity_curve)
    run_hash = compute_run_hash(trades_hash, equity_hash, ctx.play_hash)

    # Resolve idea path
    resolved_idea_path = (
        str(ctx.config.plays_dir / f"{ctx.play.id}.yml")
        if ctx.config.plays_dir
        else f"tests/functional/plays/{ctx.play.id}.yml"
    )

    # Extract leverage and equity from Play
    play_leverage = int(ctx.play.account.max_leverage) if ctx.play.account else 1
    play_initial_equity = ctx.play.account.starting_equity_usdt if ctx.play.account else 10000.0

    summary = compute_results_summary(
        play_id=ctx.play.id,
        symbol=ctx.symbol,
        tf_exec=ctx.exec_tf,
        window_start=ctx.config.window_start,
        window_end=ctx.config.window_end,
        run_id=ctx.run_id,
        trades=ctx.trades,
        equity_curve=ctx.equity_curve,
        artifact_path=str(ctx.artifact_path),
        run_duration_seconds=run_duration,
        idea_hash=ctx.play_hash,
        pipeline_version=PIPELINE_VERSION,
        resolved_idea_path=resolved_idea_path,
        trades_hash=trades_hash,
        equity_hash=equity_hash,
        run_hash=run_hash,
        metrics=ctx.engine_result.metrics,
        leverage=play_leverage,
        initial_equity=play_initial_equity,
    )

    # Write result.json
    result_path = ctx.artifact_path / STANDARD_FILES["result"]
    summary.write_json(result_path)

    return summary


def _write_pipeline_signature(ctx: _RunContext) -> None:
    """
    Create and write pipeline signature.

    Raises GateFailure if signature validation fails.
    """
    from .artifacts.pipeline_signature import (
        PIPELINE_SIGNATURE_FILE,
        create_pipeline_signature,
    )

    # Resolve idea path
    resolved_idea_path = (
        str(ctx.config.plays_dir / f"{ctx.play.id}.yml")
        if ctx.config.plays_dir
        else f"tests/functional/plays/{ctx.play.id}.yml"
    )

    # Get declared feature keys
    declared_keys = []
    for feature in ctx.play.feature_registry.all_features():
        declared_keys.append(feature.id)
        if feature.output_keys:
            declared_keys.extend(feature.output_keys)

    computed_keys = declared_keys.copy()

    pipeline_sig = create_pipeline_signature(
        run_id=ctx.run_id,
        play=ctx.play,
        play_hash=ctx.play_hash,
        resolved_path=resolved_idea_path,
        declared_keys=declared_keys,
        computed_keys=computed_keys,
    )

    # Validate signature
    sig_errors = pipeline_sig.validate()
    if sig_errors:
        ctx.result.gate_failed = "pipeline_signature"
        ctx.result.error_message = f"Pipeline signature validation failed: {sig_errors}"
        raise GateFailure(ctx.result.error_message)

    # Write signature
    sig_path = ctx.artifact_path / PIPELINE_SIGNATURE_FILE
    pipeline_sig.write_json(sig_path)


def _run_artifact_validation(ctx: _RunContext) -> None:
    """
    Run artifact validation gate.

    Raises GateFailure if validation fails.
    """
    if ctx.config.skip_artifact_validation:
        return

    print("\n[ARTIFACTS] Running Artifact Export Gate...")

    artifact_validation = validate_artifacts(ctx.artifact_path)
    ctx.result.artifact_validation = artifact_validation

    artifact_validation.print_summary()

    if not artifact_validation.passed:
        ctx.result.gate_failed = "artifact_validation"
        ctx.result.error_message = "Artifact export gate failed - see validation errors"
        raise GateFailure(ctx.result.error_message)


def _emit_snapshots(ctx: _RunContext) -> None:
    """
    Emit snapshot artifacts if requested.

    Non-fatal errors are logged but don't fail the run.
    """
    if not ctx.config.emit_snapshots:
        return

    try:
        from .snapshot_artifacts import emit_snapshot_artifacts

        # Get DataFrames from engine
        real_engine = getattr(ctx.engine, 'engine', ctx.engine)

        # Get dataframes for each of the 3 definable timeframes
        low_tf_df = None
        med_tf_df = None
        high_tf_df = None
        low_tf_specs = None
        med_tf_specs = None
        high_tf_specs = None

        # Get prepared frame if available (single-TF mode)
        if hasattr(real_engine, '_prepared_frame') and real_engine._prepared_frame is not None:
            low_tf_df = real_engine._prepared_frame.full_df

        # Get multi-TF dataframes
        if hasattr(real_engine, '_low_tf_df') and real_engine._low_tf_df is not None:
            low_tf_df = real_engine._low_tf_df
        if hasattr(real_engine, '_med_tf_df') and real_engine._med_tf_df is not None:
            med_tf_df = real_engine._med_tf_df
        if hasattr(real_engine, '_high_tf_df') and real_engine._high_tf_df is not None:
            high_tf_df = real_engine._high_tf_df

        # Get feature specs for each role
        if hasattr(real_engine, 'config') and hasattr(real_engine.config, 'feature_specs_by_role'):
            engine_config = real_engine.config
            low_tf_specs = engine_config.feature_specs_by_role.get('low_tf', [])
            med_tf_specs = engine_config.feature_specs_by_role.get('med_tf', [])
            high_tf_specs = engine_config.feature_specs_by_role.get('high_tf', [])

        # exec_role indicates which of the 3 TFs is the execution TF
        exec_role = ctx.play.exec_role if hasattr(ctx.play, 'exec_role') else "low_tf"

        snapshots_dir = emit_snapshot_artifacts(
            run_dir=ctx.artifact_path,
            play_id=ctx.play.id,
            symbol=ctx.symbol,
            window_start=ctx.config.window_start,
            window_end=ctx.config.window_end,
            # The 3 concrete TF values
            low_tf=ctx.play.low_tf,
            med_tf=ctx.play.med_tf,
            high_tf=ctx.play.high_tf,
            # exec_role pointer
            exec_role=exec_role,
            # DataFrames for the 3 definable TFs
            low_tf_df=low_tf_df,
            med_tf_df=med_tf_df,
            high_tf_df=high_tf_df,
            # Feature specs for each TF role
            low_tf_feature_specs=low_tf_specs,
            med_tf_feature_specs=med_tf_specs,
            high_tf_feature_specs=high_tf_specs,
        )

        print(f"\n[SNAPSHOTS] Emitted to {snapshots_dir}")

    except Exception as e:
        import traceback
        print(f"\n[SNAPSHOTS] Failed to emit snapshots: {e}")
        print(f"[SNAPSHOTS] Traceback: {traceback.format_exc()}")
# P1.2 Refactor: PlayBacktestResult moved to engine_factory.py (single definition)
# Use from src.backtest.engine_factory import PlayBacktestResult if needed
# =============================================================================
# P1.2 Refactor: These adapter classes have been deleted.
# Use engine.create_engine_from_play() and engine.run_engine_with_play()
# directly from src.backtest.engine module.
# =============================================================================


@dataclass
class RunnerConfig:
    """Configuration for the backtest runner."""
    # Play
    play_id: str = ""
    play: Play | None = None

    # Window
    window_start: datetime | None = None
    window_end: datetime | None = None
    window_name: str | None = None  # Alternative to explicit dates

    # Paths
    base_output_dir: Path = field(default_factory=lambda: Path("backtests"))
    plays_dir: Path | None = None

    # Gates
    skip_preflight: bool = False  # For testing only
    skip_artifact_validation: bool = False  # For testing only

    # Data loader
    data_loader: DataLoader | None = None

    # Auto-sync
    auto_sync_missing_data: bool = False

    # Snapshot emission
    emit_snapshots: bool = False

    # Data environment (backtest, live, demo) - determines which DuckDB to use
    data_env: str = "backtest"
    
    def load_play(self) -> Play:
        """Load the Play if not already loaded."""
        if self.play is not None:
            return self.play
        
        if not self.play_id:
            raise ValueError("play_id is required")
        
        self.play = load_play(self.play_id, base_dir=self.plays_dir)
        return self.play


@dataclass
class RunnerResult:
    """Result of a backtest run."""
    success: bool
    run_id: str
    artifact_path: Path | None = None

    # Gate results
    preflight_report: PreflightReport | None = None
    artifact_validation: ArtifactValidationResult | None = None

    # Summary
    summary: ResultsSummary | None = None

    # Error info
    error_message: str | None = None
    gate_failed: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dict for serialization."""
        return {
            "success": self.success,
            "run_id": self.run_id,
            "artifact_path": str(self.artifact_path) if self.artifact_path else None,
            "preflight_passed": self.preflight_report.overall_status == PreflightStatus.PASSED if self.preflight_report else None,
            "artifact_validation_passed": self.artifact_validation.passed if self.artifact_validation else None,
            "summary": self.summary.to_dict() if self.summary else None,
            "error_message": self.error_message,
            "gate_failed": self.gate_failed,
        }


def run_backtest_with_gates(
    config: RunnerConfig,
    synthetic_provider: "SyntheticDataProvider | None" = None,
) -> RunnerResult:
    """
    Run a backtest with all gates enforced.

    G4.1 Refactor: Main orchestrator function that delegates to helper functions.
    Each helper handles a specific phase of the backtest pipeline.

    Args:
        config: Runner configuration
        synthetic_provider: Optional synthetic data provider (bypasses DB access)

    Returns:
        RunnerResult with success status and all gate results
    """
    # Initialize context and result
    ctx = _RunContext(
        config=config,
        result=RunnerResult(success=False, run_id=""),
        run_start_time=time.time(),
    )
    result = ctx.result

    try:
        # Phase 1: Load Play and setup synthetic data
        ctx.play = config.load_play()
        synthetic_provider = _setup_synthetic_provider(ctx.play, config, synthetic_provider)

        # Phase 2: Resolve window (from DB if not provided)
        _resolve_window(ctx.play, config)

        # Phase 3: Validate symbol universe
        if not ctx.play.symbol_universe:
            raise ValueError("Play has no symbols in symbol_universe")
        ctx.symbol = ctx.play.symbol_universe[0]
        ctx.exec_tf = ctx.play.execution_tf

        # Phase 4: Create artifact setup (hashes, paths, manifest)
        (
            ctx.artifact_path,
            ctx.run_id,
            ctx.play_hash,
            ctx.data_source_id,
            _,  # input_components not needed after this
            ctx.manifest,
        ) = _create_artifact_setup(ctx.play, config, synthetic_provider)
        result.artifact_path = ctx.artifact_path
        result.run_id = ctx.run_id

        # Phase 5: Initialize run logger
        (ctx.artifact_path / "logs").mkdir(exist_ok=True)
        ctx.run_logger = RunLogger(
            play_hash=ctx.play_hash,
            run_id=ctx.run_id,
            artifact_dir=ctx.artifact_path,
            play_id=ctx.play.id,
            symbol=ctx.symbol,
            tf=ctx.exec_tf,
        )
        set_run_logger(ctx.run_logger)
        ctx.run_logger.info("Run started", play_id=ctx.play.id, symbol=ctx.symbol, tf=ctx.exec_tf)

        # Phase 6: Run preflight gate
        _run_preflight_gate(ctx)

        # Phase 7: Run indicator requirements gate
        _run_indicator_gate(ctx.play, result)

        # Phase 8: Get warmup configuration
        ctx.preflight_warmup_by_role, ctx.preflight_delay_by_role = _get_warmup_config(
            result, config, ctx.play
        )

        # Phase 9: Execute backtest
        _execute_backtest(ctx, synthetic_provider)

        # Phase 10: Write trade artifacts
        eval_start_ts_ms = _write_trade_artifacts(ctx)

        # Phase 11: Write results summary
        summary = _write_results_summary(ctx)
        result.summary = summary

        # Phase 12: Write pipeline signature
        _write_pipeline_signature(ctx)

        # Phase 13: Update manifest with eval_start_ts_ms
        ctx.manifest.eval_start_ts_ms = eval_start_ts_ms
        ctx.manifest.equity_timestamp_column = "ts_ms"
        ctx.manifest.write_json(ctx.artifact_path / "run_manifest.json")

        # Phase 14: Run artifact validation gate
        _run_artifact_validation(ctx)

        # Phase 15: Emit snapshots (if requested)
        _emit_snapshots(ctx)

        # Phase 16: Success
        result.success = True
        ctx.run_logger.finalize(
            net_pnl=summary.net_pnl_usdt if summary else None,
            trades_count=summary.trades_count if summary else None,
            status="success",
        )
        set_run_logger(None)

        # Print risk mode warning and summary
        real_engine = getattr(ctx.engine, 'engine', ctx.engine)
        if hasattr(real_engine, 'config') and hasattr(real_engine.config, 'risk_mode'):
            if real_engine.config.risk_mode == "none":
                print("\n[WARN] Risk limits disabled (risk_mode=none)")
                print("[WARN] Set risk_mode='rules' for production risk management.")
        summary.print_summary()

        return result

    except GateFailure:
        # Gate failure - already handled
        print(f"\n[FAILED] Gate Failed: {result.gate_failed}")
        print(f"   {result.error_message}")
        _finalize_logger_on_error(ctx, "gate_failed")
        return result

    except Exception as e:
        # Unexpected error
        import traceback
        result.error_message = str(e)
        print(f"\n[ERROR] Error: {e}")
        traceback.print_exc()
        _finalize_logger_on_error(ctx, "error")
        return result


def _finalize_logger_on_error(ctx: _RunContext, status: str) -> None:
    """Helper to finalize run logger on error without raising."""
    try:
        if ctx.run_logger:
            ctx.run_logger.finalize(status=status)
            set_run_logger(None)
    except (OSError, IOError, AttributeError) as e:
        # BUG-004 fix: Specific exceptions for logger cleanup
        # File may be closed or logger already finalized
        pass


# =============================================================================
# G1: Dead code removed (2026-01-27)
# =============================================================================
# - run_smoke_test() - unused convenience wrapper
# - main() CLI entrypoint - unused, backtest runs via trade_cli.py
# =============================================================================