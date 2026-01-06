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
    extract_available_keys_from_feature_frames,
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
    """Raised when a gate fails."""
    pass


# =============================================================================
# Pipeline Version (for artifact tracking)
# =============================================================================
# Import from canonical source - single source of truth
from .artifacts.pipeline_signature import PIPELINE_VERSION


# =============================================================================
# Play-Native Backtest Execution
# =============================================================================

class PlayBacktestResult:
    """Result from Play-native backtest execution."""

    def __init__(
        self,
        trades: list[Any],
        equity_curve: list[Any],
        final_equity: float,
        play_hash: str,
        metrics: Any = None,  # BacktestMetrics from engine
    ):
        self.trades = trades
        self.equity_curve = equity_curve
        self.final_equity = final_equity
        self.play_hash = play_hash
        self.metrics = metrics


# =============================================================================
# DELETED: create_default_engine_factory and PlayEngineWrapper
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
    engine_factory: Callable | None = None,
) -> RunnerResult:
    """
    Run a backtest with all gates enforced.
    
    Args:
        config: Runner configuration
        engine_factory: Optional factory to create the backtest engine
                       (for testing/dependency injection)
    
    Returns:
        RunnerResult with success status and all gate results
    """
    run_start_time = time.time()
    # run_id will be auto-generated by ArtifactPathConfig based on sequential number
    run_id = ""  # Will be set by artifact config
    
    result = RunnerResult(success=False, run_id=run_id)
    
    try:
        # Load Play
        play = config.load_play()

        # Auto-infer window from DB coverage if not provided
        if not config.window_start or not config.window_end:
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

            # Still check after inference attempt
            if not config.window_start or not config.window_end:
                raise ValueError(
                    f"window_start and window_end are required. "
                    f"No data found for {symbol} {tf}. Use --start/--end or sync data first."
                )
        
        # Get first symbol (for now, only single-symbol support)
        if not play.symbol_universe:
            raise ValueError("Play has no symbols in symbol_universe")
        symbol = play.symbol_universe[0]
        
        # Compute play_hash for deterministic run folder naming
        play_hash = compute_play_hash(play)
        
        # Collect all timeframes from FeatureRegistry
        exec_tf = play.execution_tf
        tf_ctx = sorted(play.feature_registry.get_all_tfs())
        
        # Determine data source ID based on env (for data provenance)
        data_source_id = "duckdb_live"  # Default; would be set from config.data_env if available
        
        # Build input hash components (ALL factors affecting results)
        input_components = InputHashComponents(
            play_hash=play_hash,
            symbols=play.symbol_universe,
            tf_exec=exec_tf,
            tf_ctx=tf_ctx,
            window_start=config.window_start.strftime("%Y-%m-%d"),
            window_end=config.window_end.strftime("%Y-%m-%d"),
            # Execution model versions
            fee_model_version="1.0.0",
            simulator_version="1.0.0",
            engine_version=PIPELINE_VERSION,
            fill_policy_version="1.0.0",
            # Data provenance (REQUIRED for determinism)
            data_source_id=data_source_id,
            data_version=None,  # Could be DB version/timestamp if available
            candle_policy="closed_only",  # Backtest uses closed candles only
            # Randomness
            seed=None,  # No randomness currently
        )
        
        # Compute hashes
        full_hash = input_components.compute_full_hash()
        short_hash = input_components.compute_short_hash()  # Default 8 chars
        short_hash_length = len(short_hash)
        
        # Compute universe_id for folder path (avoids symbol redundancy)
        universe_id = input_components.universe_id
        
        # Setup artifact path (run_id = 8-char input hash)
        artifact_config = ArtifactPathConfig(
            base_dir=config.base_output_dir,
            category="_validation",  # Current mode: engine validation
            play_id=play.id,
            universe_id=universe_id,  # Symbol or uni_<hash> for multi-symbol
            tf_exec=exec_tf,
            window_start=config.window_start,
            window_end=config.window_end,
            run_id=short_hash,  # 8-char deterministic hash
            play_hash=play_hash,
            short_hash_length=short_hash_length,
        )
        # Capture the generated run_id
        run_id = artifact_config.run_id
        
        # Validate artifact config
        path_errors = validate_artifact_path_config(artifact_config)
        if path_errors:
            raise ValueError(f"Invalid artifact config: {'; '.join(path_errors)}")
        
        # Create output folder
        artifact_path = artifact_config.create_folder()
        result.artifact_path = artifact_path
        
        # Create and write RunManifest (MANDATORY for every run)
        manifest = RunManifest(
            # Hash identity
            full_hash=full_hash,
            short_hash=short_hash,
            short_hash_length=short_hash_length,
            hash_algorithm="sha256",
            # Strategy config
            play_id=play.id,
            play_hash=play_hash,
            # Symbol universe
            symbols=play.symbol_universe,
            universe_id=universe_id,
            # Timeframes
            tf_exec=exec_tf,
            tf_ctx=tf_ctx,
            # Window
            window_start=config.window_start.strftime("%Y-%m-%d"),
            window_end=config.window_end.strftime("%Y-%m-%d"),
            # Execution model versions
            fee_model_version="1.0.0",
            simulator_version="1.0.0",
            engine_version=PIPELINE_VERSION,
            fill_policy_version="1.0.0",
            # Data provenance
            data_source_id=data_source_id,
            data_version=None,
            candle_policy="closed_only",
            # Randomness
            seed=None,
            # Category & semantics
            category="_validation",
            is_promotable=False,
            allows_overwrite=True,
            attempt_id=None,  # Not used for _validation
        )
        manifest.write_json(artifact_path / "run_manifest.json")
        
        # Create logs directory
        (artifact_path / "logs").mkdir(exist_ok=True)

        # Initialize per-run logger (writes to artifact logs/ and global play-indexed logs/)
        run_logger = RunLogger(
            play_hash=play_hash,
            run_id=run_id,
            artifact_dir=artifact_path,
            play_id=play.id,
            symbol=symbol,
            tf=exec_tf,
        )
        set_run_logger(run_logger)
        run_logger.info("Run started", play_id=play.id, symbol=symbol, tf=exec_tf)

        # =====================================================================
        # GATE 1: Data Preflight
        # =====================================================================
        if not config.skip_preflight:
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
            
            # Update RunManifest with warmup/delay audit data (after preflight passes)
            # RENAMED: computed_warmup_by_role → computed_lookback_bars_by_role (breaking change)
            if preflight_report.computed_warmup_requirements:
                manifest.computed_lookback_bars_by_role = preflight_report.computed_warmup_requirements.warmup_by_role
                manifest.computed_delay_bars_by_role = preflight_report.computed_warmup_requirements.delay_by_role
            if preflight_report.auto_sync_result and preflight_report.auto_sync_result.tool_calls:
                manifest.warmup_tool_calls = [tc.to_dict() for tc in preflight_report.auto_sync_result.tool_calls]
            # Rewrite manifest with warmup data
            manifest.write_json(artifact_path / "run_manifest.json")
        
        # =====================================================================
        # GATE 2: Indicator Requirements Gate
        # =====================================================================
        # Validate that all required indicator keys are declared
        # This runs before simulation to catch misnamed keys early
        # The actual key availability check happens after frame preparation

        # Check if Play has any features declared
        registry = play.feature_registry
        has_features = len(list(registry.all_features())) > 0

        if has_features:
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
        else:
            print("\n[INDICATOR GATE] Skipped - no features declared")
        
        # =====================================================================
        # EXTRACT PREFLIGHT WARMUP + DELAY (SOURCE OF TRUTH)
        # =====================================================================
        # Runner MUST NOT compute warmup/delay - it consumes Preflight output only
        preflight_warmup_by_role: dict[str, int] | None = None
        preflight_delay_by_role: dict[str, int] | None = None
        if result.preflight_report and result.preflight_report.computed_warmup_requirements:
            preflight_warmup_by_role = result.preflight_report.computed_warmup_requirements.warmup_by_role
            preflight_delay_by_role = result.preflight_report.computed_warmup_requirements.delay_by_role
            print(f"[WARMUP] Using Preflight warmup: {preflight_warmup_by_role}")
            if preflight_delay_by_role and any(v > 0 for v in preflight_delay_by_role.values()):
                print(f"[DELAY] Using Preflight delay: {preflight_delay_by_role}")
        else:
            # Preflight skipped or no warmup computed - this is an error in the new flow
            if not config.skip_preflight:
                raise ValueError(
                    "MISSING_PREFLIGHT_WARMUP: Preflight passed but no computed_warmup_requirements found. "
                    "This indicates a bug in the Preflight gate."
                )
            # For skip_preflight mode (testing only), compute warmup directly
            # This is NOT the production path - only for testing without preflight
            print("[WARN] Preflight skipped - computing warmup directly (testing mode only)")
            warmup_reqs = compute_warmup_requirements(play)
            preflight_warmup_by_role = warmup_reqs.warmup_by_role
            preflight_delay_by_role = warmup_reqs.delay_by_role
        
        # =====================================================================
        # RUN BACKTEST
        # =====================================================================
        print("\n[RUN] Running Backtest...")
        
        # Import engine factory functions (P1.2 Refactor)
        from .engine import create_engine_from_play, run_engine_with_play
        
        # Create engine directly from Play (no adapter layer)
        if engine_factory is not None:
            # Custom factory provided (for testing/DI) - use legacy path
            engine = engine_factory(play, config)
            engine_result = engine.run()
        else:
            # Standard path: use new Play-native engine factory
            engine = create_engine_from_play(
                play=play,
                window_start=config.window_start,
                window_end=config.window_end,
                warmup_by_tf=preflight_warmup_by_role,
            )
            # Set play_hash for debug logging (hash tracing)
            engine.set_play_hash(play_hash)
            engine_result = run_engine_with_play(engine, play)
        
        # Extract trades and equity
        trades: list[dict[str, Any]] = []
        equity_curve: list[dict[str, Any]] = []
        play_hash = ""
        
        if hasattr(engine_result, 'trades'):
            trades = [t.to_dict() if hasattr(t, 'to_dict') else t for t in engine_result.trades]
        if hasattr(engine_result, 'equity_curve'):
            equity_curve = [e.to_dict() if hasattr(e, 'to_dict') else e for e in engine_result.equity_curve]
        if hasattr(engine_result, 'play_hash'):
            play_hash = engine_result.play_hash
        else:
            play_hash = compute_play_hash(play)
        
        # Write trades.parquet (Phase 3.2: Parquet-only)
        trades_df = pd.DataFrame(trades) if trades else pd.DataFrame(columns=[
            "entry_time", "exit_time", "side", "entry_price", "exit_price",
            "entry_size_usdt", "net_pnl", "stop_loss", "take_profit", "exit_reason",
        ])
        write_parquet(trades_df, artifact_path / "trades.parquet")
        
        # Write equity.parquet (Phase 3.2: Parquet-only, Phase 6: add ts_ms)
        equity_df = pd.DataFrame(equity_curve) if equity_curve else pd.DataFrame(columns=[
            "timestamp", "equity",
        ])
        
        # Phase 6: Add ts_ms column (epoch milliseconds) for smoke test assertions
        if not equity_df.empty and "timestamp" in equity_df.columns:
            # Convert timestamp to epoch-ms
            equity_df["ts_ms"] = pd.to_datetime(equity_df["timestamp"]).astype("int64") // 10**6
        else:
            equity_df["ts_ms"] = pd.Series(dtype="int64")
        
        write_parquet(equity_df, artifact_path / "equity.parquet")
        
        # Phase 6: Extract eval_start_ts_ms from engine result for manifest
        eval_start_ts_ms = None
        if hasattr(engine_result, 'metrics') and engine_result.metrics:
            # Try to get simulation_start from metrics
            if hasattr(engine_result.metrics, 'simulation_start'):
                sim_start = engine_result.metrics.simulation_start
                if sim_start is not None:
                    if hasattr(sim_start, 'timestamp'):
                        eval_start_ts_ms = int(sim_start.timestamp() * 1000)
                    elif isinstance(sim_start, (int, float)):
                        eval_start_ts_ms = int(sim_start)
        # Fallback: use first equity timestamp if available
        if eval_start_ts_ms is None and not equity_df.empty and "ts_ms" in equity_df.columns:
            eval_start_ts_ms = int(equity_df["ts_ms"].iloc[0])
        
        # Compute and write results summary
        run_duration = time.time() - run_start_time
        # Compute hashes for determinism tracking
        trades_hash = compute_trades_hash(engine_result.trades) if hasattr(engine_result, 'trades') and engine_result.trades else ""
        equity_hash = compute_equity_hash(engine_result.equity_curve) if hasattr(engine_result, 'equity_curve') and engine_result.equity_curve else ""
        run_hash = compute_run_hash(trades_hash, equity_hash, play_hash)
        
        # Resolve idea path (where Play was loaded from)
        resolved_idea_path = str(config.plays_dir / f"{play.id}.yml") if config.plays_dir else f"strategies/plays/{play.id}.yml"
        
        summary = compute_results_summary(
            play_id=play.id,
            symbol=symbol,
            tf_exec=exec_tf,
            window_start=config.window_start,
            window_end=config.window_end,
            run_id=run_id,
            trades=trades,
            equity_curve=equity_curve,
            artifact_path=str(artifact_path),
            run_duration_seconds=run_duration,
            # Gate D required fields
            idea_hash=play_hash,
            pipeline_version=PIPELINE_VERSION,
            resolved_idea_path=resolved_idea_path,
            # Determinism hashes (Phase 3)
            trades_hash=trades_hash,
            equity_hash=equity_hash,
            run_hash=run_hash,
            # Pass pre-computed metrics for comprehensive analytics
            metrics=engine_result.metrics,
        )
        
        result.summary = summary
        
        # Write result.json
        result_path = artifact_path / STANDARD_FILES["result"]
        summary.write_json(result_path)
        
        # =====================================================================
        # Write pipeline_signature.json (Gate D.1)
        # =====================================================================
        from .artifacts.pipeline_signature import (
            PipelineSignature, 
            PIPELINE_SIGNATURE_FILE,
            create_pipeline_signature,
        )
        
        # Get declared feature keys from Play feature_registry
        declared_keys = []
        for feature in play.feature_registry.all_features():
            declared_keys.append(feature.id)
            if feature.output_keys:
                declared_keys.extend(feature.output_keys)
        
        # Get computed feature keys (from engine result if available)
        computed_keys = declared_keys.copy()  # Assume match for now (validated in FeatureFrameBuilder)
        
        pipeline_sig = create_pipeline_signature(
            run_id=run_id,
            play=play,
            play_hash=play_hash,
            resolved_path=resolved_idea_path,
            declared_keys=declared_keys,
            computed_keys=computed_keys,
        )
        
        # Validate signature
        sig_errors = pipeline_sig.validate()
        if sig_errors:
            result.gate_failed = "pipeline_signature"
            result.error_message = f"Pipeline signature validation failed: {sig_errors}"
            raise GateFailure(result.error_message)
        
        # Write signature
        sig_path = artifact_path / PIPELINE_SIGNATURE_FILE
        pipeline_sig.write_json(sig_path)
        
        # =====================================================================
        # Phase 6: Update RunManifest with eval_start_ts_ms (engine truth)
        # =====================================================================
        manifest.eval_start_ts_ms = eval_start_ts_ms
        manifest.equity_timestamp_column = "ts_ms"
        manifest.write_json(artifact_path / "run_manifest.json")
        
        # =====================================================================
        # GATE 2: Artifact Validation
        # =====================================================================
        if not config.skip_artifact_validation:
            print("\n[ARTIFACTS] Running Artifact Export Gate...")
            
            artifact_validation = validate_artifacts(artifact_path)
            result.artifact_validation = artifact_validation
            
            # Print summary
            artifact_validation.print_summary()
            
            # Check gate
            if not artifact_validation.passed:
                result.gate_failed = "artifact_validation"
                result.error_message = "Artifact export gate failed - see validation errors"
                raise GateFailure(result.error_message)
        
        # =====================================================================
        # EMIT SNAPSHOTS (if requested)
        # =====================================================================
        # Emit lossless snapshot artifacts for verification suite
        if config.emit_snapshots:
            try:
                from .snapshot_artifacts import emit_snapshot_artifacts

                # Collect DataFrames and specs from the engine
                exec_df = None
                htf_df = None
                mtf_df = None
                exec_specs = None
                htf_specs = None
                mtf_specs = None

                # Get DataFrames from engine
                # The engine is actually an PlayEngineWrapper, so access the real engine
                real_engine = getattr(engine, 'engine', engine)

                # For single-TF mode, use _prepared_frame.full_df (includes computed indicators)
                # For multi-TF mode, use _ltf_df, _htf_df, etc. (these include indicators)
                if hasattr(real_engine, '_prepared_frame') and real_engine._prepared_frame is not None:
                    # Use full_df which includes warmup data and computed indicators
                    exec_df = real_engine._prepared_frame.full_df
                elif hasattr(real_engine, '_ltf_df') and real_engine._ltf_df is not None:
                    exec_df = real_engine._ltf_df

                if hasattr(real_engine, '_htf_df') and real_engine._htf_df is not None:
                    htf_df = real_engine._htf_df

                if hasattr(real_engine, '_mtf_df') and real_engine._mtf_df is not None:
                    mtf_df = real_engine._mtf_df

                # Get feature specs from the engine's config
                # The real engine has the SystemConfig with feature_specs_by_role
                if hasattr(real_engine, 'config') and hasattr(real_engine.config, 'feature_specs_by_role'):
                    engine_config = real_engine.config
                    exec_specs = engine_config.feature_specs_by_role.get('exec', [])
                    htf_specs = engine_config.feature_specs_by_role.get('htf', [])
                    mtf_specs = engine_config.feature_specs_by_role.get('mtf', [])


                # Emit snapshots
                snapshots_dir = emit_snapshot_artifacts(
                    run_dir=artifact_path,
                    play_id=play.id,
                    symbol=symbol,
                    window_start=config.window_start,
                    window_end=config.window_end,
                    exec_tf=exec_tf,
                    htf=play.htf,
                    mtf=play.mtf,
                    exec_df=exec_df,
                    htf_df=htf_df,
                    mtf_df=mtf_df,
                    exec_feature_specs=exec_specs,
                    htf_feature_specs=htf_specs,
                    mtf_feature_specs=mtf_specs,
                )

                print(f"\n[SNAPSHOTS] Emitted to {snapshots_dir}")

            except Exception as e:
                import traceback
                print(f"\n[SNAPSHOTS] Failed to emit snapshots: {e}")
                print(f"[SNAPSHOTS] Traceback: {traceback.format_exc()}")
                # Don't fail the run for snapshot emission errors

        # =====================================================================
        # SUCCESS
        # =====================================================================
        result.success = True

        # Finalize run logger (writes summary log and index.jsonl entry)
        run_logger.finalize(
            net_pnl=summary.net_pnl if summary else None,
            trades_count=summary.total_trades if summary else None,
            status="success",
        )
        set_run_logger(None)

        # Print final summary
        summary.print_summary()

        return result
        
    except GateFailure as e:
        # Gate failure - already handled
        print(f"\n[FAILED] Gate Failed: {result.gate_failed}")
        print(f"   {result.error_message}")
        # Finalize run logger with error status
        try:
            run_logger.finalize(status="gate_failed")
            set_run_logger(None)
        except NameError:
            pass  # run_logger not yet initialized
        return result

    except Exception as e:
        # Unexpected error
        import traceback
        result.error_message = str(e)
        print(f"\n[ERROR] Error: {e}")
        traceback.print_exc()
        # Finalize run logger with error status
        try:
            run_logger.finalize(status="error")
            set_run_logger(None)
        except NameError:
            pass  # run_logger not yet initialized
        return result


def run_smoke_test(
    play_id: str,
    window_start: datetime,
    window_end: datetime,
    data_loader: DataLoader,
    base_output_dir: Path = Path("backtests"),
    plays_dir: Path | None = None,
) -> RunnerResult:
    """
    Convenience function to run a smoke test for an Play.
    
    Args:
        play_id: Play identifier
        window_start: Backtest window start
        window_end: Backtest window end
        data_loader: Function to load data (symbol, tf) -> DataFrame
        base_output_dir: Base directory for artifacts
        plays_dir: Directory containing Play YAMLs
        
    Returns:
        RunnerResult with success status
    """
    config = RunnerConfig(
        play_id=play_id,
        window_start=window_start,
        window_end=window_end,
        data_loader=data_loader,
        base_output_dir=base_output_dir,
        plays_dir=plays_dir,
    )
    
    return run_backtest_with_gates(config)


# =============================================================================
# CLI Entrypoint
# =============================================================================

def main():
    """
    CLI entrypoint for running backtests.
    
    Usage:
        python -m src.backtest.runner --idea <id> --start <date> --end <date> --env <live|demo> --export-root <path>
    
    Example:
        python -m src.backtest.runner --idea SOLUSDT_15m_ema_crossover --start 2024-01-01 --end 2024-03-01 --env live --export-root backtests/
    """
    import argparse
    import sys
    
    parser = argparse.ArgumentParser(
        description="Run Play-based backtest with gate enforcement",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    
    parser.add_argument(
        "--idea",
        required=True,
        help="Play ID (filename without .yml) or path to YAML file",
    )
    parser.add_argument(
        "--start",
        required=True,
        help="Backtest start date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--end",
        required=True,
        help="Backtest end date (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--env",
        choices=["live", "demo"],
        default="live",
        help="Data environment (live or demo)",
    )
    parser.add_argument(
        "--export-root",
        default="backtests/",
        help="Base directory for artifact export",
    )
    parser.add_argument(
        "--idea-dir",
        default=None,
        help="Override Play directory (default: strategies/plays/)",
    )
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Skip data preflight gate (for testing only)",
    )
    parser.add_argument(
        "--auto-sync",
        action="store_true",
        help="Auto-sync missing data during preflight",
    )
    
    args = parser.parse_args()
    
    # Parse dates
    try:
        window_start = datetime.fromisoformat(args.start)
        window_end = datetime.fromisoformat(args.end)
    except ValueError as e:
        print(f"[ERROR] Invalid date format: {e}")
        print("Use YYYY-MM-DD format (e.g., 2024-01-01)")
        sys.exit(1)
    
    # Ensure dates are timezone-aware
    if window_start.tzinfo is None:
        window_start = window_start.replace(tzinfo=timezone.utc)
    if window_end.tzinfo is None:
        window_end = window_end.replace(tzinfo=timezone.utc)
    
    # Create data loader
    from ..data.historical_data_store import get_historical_store
    
    store = get_historical_store(env=args.env)
    
    def data_loader(symbol: str, tf: str, start: datetime, end: datetime):
        """Load OHLCV data from DuckDB."""
        return store.get_ohlcv(symbol=symbol, tf=tf, start=start, end=end)
    
    # Build config
    config = RunnerConfig(
        play_id=args.idea,
        window_start=window_start,
        window_end=window_end,
        data_loader=data_loader,
        base_output_dir=Path(args.export_root),
        plays_dir=Path(args.idea_dir) if args.idea_dir else None,
        skip_preflight=args.skip_preflight,
        auto_sync_missing_data=args.auto_sync,
    )
    
    # Run backtest
    print(f"\n{'='*60}")
    print(f"  BACKTEST RUNNER")
    print(f"{'='*60}")
    print(f"  Play:   {args.idea}")
    print(f"  Window:     {window_start.date()} -> {window_end.date()}")
    print(f"  Env:        {args.env}")
    print(f"  Export:     {args.export_root}")
    print(f"{'='*60}\n")
    
    result = run_backtest_with_gates(config)
    
    # Exit with appropriate code
    if result.success:
        print(f"\n[SUCCESS] Backtest completed successfully")
        print(f"  Artifacts: {result.artifact_path}")
        sys.exit(0)
    else:
        print(f"\n[FAILED] Backtest failed")
        if result.gate_failed:
            print(f"  Gate failed: {result.gate_failed}")
        if result.error_message:
            print(f"  Error: {result.error_message}")
        sys.exit(1)


if __name__ == "__main__":
    main()
