"""
Play-based backtest tools — core execution path.

This module contains the GOLDEN PATH for backtest execution:
- Preflight check (data coverage validation)
- Run backtest (full execution)

Related tools split into sibling modules:
- backtest_play_data_tools: indicator discovery, data fix, list plays
- backtest_play_normalize_tools: normalize single/batch Play YAML

CLI and agents should use these tools, not direct engine access.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from collections.abc import Callable
from typing import Any, cast
import traceback

import pandas as pd

from .shared import ToolResult
from ..utils.datetime_utils import datetime_to_epoch_ms, normalize_timestamp
from ..utils.timeframes import validate_canonical_tf
from ..config.constants import (
    DataEnv,
    DEFAULT_BACKTEST_ENV,
    validate_data_env,
    validate_symbol,
    resolve_db_path,
)
from ..data.historical_data_store import (
    get_historical_store,
    TF_MINUTES,
)
from ..backtest.play import load_play, list_plays, Play
from ..backtest.execution_validation import (
    validate_play_full,
    compute_warmup_requirements,
)
from ..backtest.system_config import validate_usdt_pair
from ..backtest.runtime.preflight import run_preflight_gate, PreflightReport, AutoSyncConfig
from ..utils.logger import get_logger


logger = get_logger()


# =============================================================================
# Preflight Check (tools-layer)
# =============================================================================

def backtest_preflight_play_tool(
    play_id: str,
    env: DataEnv = DEFAULT_BACKTEST_ENV,
    start: datetime | None = None,
    end: datetime | None = None,
    plays_dir: Path | None = None,
    sync: bool = False,
) -> ToolResult:
    """
    Run preflight check for an Play backtest using production preflight gate.

    Phase 6: Calls run_preflight_gate() and returns PreflightReport.to_dict() unchanged.

    Args:
        play_id: Play identifier
        env: Data environment ("live" or "demo")
        start: Window start (required)
        end: Window end (default: now)
        plays_dir: Override Play directory
        sync: If True, auto-fetch and fix missing data (uses data tools)

    Returns:
        ToolResult with PreflightReport.to_dict() in data

    Note:
        Symbol is taken from the Play configuration (Play.symbol_universe[0]).
        Plays are self-contained and deterministic.
    """
    try:
        # Validate env
        env = validate_data_env(env)
        db_path = resolve_db_path(env)

        # Load Play
        try:
            play = load_play(play_id, base_dir=plays_dir)
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=str(e),
                data={
                    "env": env,
                    "db_path": str(db_path),
                    "available_plays": list_plays(plays_dir),
                },
            )

        # Validate Play
        validation = validate_play_full(play)
        if not validation.is_valid:
            return ToolResult(
                success=False,
                error=f"Play validation failed: {[i.message for i in validation.errors]}",
                data={"validation_errors": [i.message for i in validation.errors]},
            )

        # Get symbol from Play (Play is the single source of truth)
        if not play.symbol_universe:
            return ToolResult(
                success=False,
                error="Play has no symbols in symbol_universe",
            )
        symbol = play.symbol_universe[0]

        # Validate symbol
        symbol = validate_symbol(symbol)
        try:
            validate_usdt_pair(symbol)
        except ValueError as e:
            return ToolResult(
                success=False,
                error=str(e),
            )

        # Create data loader from HistoricalDataStore
        store = get_historical_store(env=env)

        # Normalize timestamps
        if start:
            start = normalize_timestamp(start)
        if end:
            end = normalize_timestamp(end)
        else:
            end = datetime.now().replace(tzinfo=None)

        # If start is None, query DB for coverage and use last 100 bars (smoke mode support)
        if start is None:
            exec_tf = validate_canonical_tf(play.exec_tf)
            # Query DB for coverage of exec TF
            key = f"{symbol}_{exec_tf}"
            db_status = store.status(symbol)
            # Find the exec TF coverage
            for db_key, info in db_status.items():
                if info.get("timeframe") == exec_tf:
                    last_ts = info.get("last_timestamp")
                    if last_ts:
                        # Use last_ts as end if earlier than current end
                        if last_ts < end:
                            end = last_ts
                        # Compute start as 100 bars before end
                        tf_minutes = TF_MINUTES.get(exec_tf, 15)
                        assert end is not None
                        start = end - timedelta(minutes=tf_minutes * 100)
                        logger.info(f"Preflight auto-window: start={start}, end={end} (from DB coverage)")
                    break

            # If still None, fail with clear error
            if start is None:
                return ToolResult(
                    success=False,
                    error=f"No data found for {symbol} {exec_tf} in database. Cannot determine window start. "
                          f"Use --start to provide explicit window start, or sync data first.",
                    data={"symbol": symbol, "exec_tf": exec_tf, "env": env},
                )

        def data_loader(sym: str, tf: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
            """Load OHLCV data from DuckDB."""
            df = store.get_ohlcv(sym, tf, start=start_dt, end=end_dt)
            if df is None:
                return pd.DataFrame()
            return df

        # Run production preflight gate with optional auto-sync
        auto_sync_config = None
        if sync:
            auto_sync_config = AutoSyncConfig(
                enabled=True,
                max_attempts=2,
                data_env=env,
            )

        assert end is not None
        preflight_report = run_preflight_gate(
            play=play,
            data_loader=data_loader,
            window_start=start,
            window_end=end,
            auto_sync_missing=sync,
            auto_sync_config=auto_sync_config,
        )

        # Print summary so user sees all TF statuses (including 1m)
        preflight_report.print_summary()

        # Get exec TF info for message
        exec_tf = validate_canonical_tf(play.exec_tf)

        # Return PreflightReport.to_dict() unchanged (Phase 6 requirement)
        report_dict = preflight_report.to_dict()

        # Add env info for convenience
        report_dict["env"] = env
        report_dict["db_path"] = str(db_path)
        report_dict["symbol"] = symbol

        if preflight_report.overall_status.value == "passed":
            return ToolResult(
                success=True,
                message=f"Preflight OK for {play_id}: {symbol} {exec_tf}",
                symbol=symbol,
                data=report_dict,
            )
        else:
            error_msg = preflight_report.error_code or "Preflight check failed"
            if preflight_report.error_details:
                error_msg += f": {preflight_report.error_details}"

            return ToolResult(
                success=False,
                error=error_msg,
                symbol=symbol,
                data=report_dict,
            )

    except Exception as e:
        logger.error(f"Preflight check failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Preflight check error: {e}",
        )


# =============================================================================
# Run Backtest Helpers
# =============================================================================


@dataclass
class ResolvedBacktestConfig:
    """Resolved configuration for backtest run."""

    starting_equity: float
    max_leverage: float
    min_trade: float
    symbol: str
    exec_tf: str
    all_tfs: list[str]
    warmup_by_tf: dict[str, int]


def _resolve_backtest_config(
    play: Play,
    preflight_data: dict[str, Any],
    initial_equity_override: float | None,
    max_leverage_override: float | None,
) -> ResolvedBacktestConfig:
    """
    Resolve backtest configuration from Play and overrides.

    Args:
        play: Loaded Play configuration
        preflight_data: Data from preflight check
        initial_equity_override: CLI override for starting equity
        max_leverage_override: CLI override for max leverage

    Returns:
        ResolvedBacktestConfig with all resolved values
    """
    assert play.account is not None, "Play.account is required for backtest"
    starting_equity = (
        initial_equity_override
        if initial_equity_override is not None
        else play.account.starting_equity_usdt
    )
    max_leverage = (
        max_leverage_override
        if max_leverage_override is not None
        else play.account.max_leverage
    )
    min_trade = play.account.min_trade_notional_usdt or 1.0
    symbol = preflight_data.get("symbol") or play.symbol_universe[0]
    exec_tf = validate_canonical_tf(play.exec_tf)
    all_tfs = sorted(play.get_all_tfs())

    # Compute warmup requirements
    warmup_reqs = compute_warmup_requirements(play)
    warmup_by_tf = {tf: warmup_reqs.warmup_by_role.get(tf, 0) for tf in all_tfs}

    return ResolvedBacktestConfig(
        starting_equity=starting_equity,
        max_leverage=max_leverage,
        min_trade=min_trade,
        symbol=symbol,
        exec_tf=exec_tf,
        all_tfs=all_tfs,
        warmup_by_tf=warmup_by_tf,
    )


def _log_backtest_config(config: ResolvedBacktestConfig, play: Play) -> None:
    """
    Log resolved backtest configuration summary.

    Args:
        config: Resolved configuration
        play: Play for fee model and slippage info
    """
    logger.info("=" * 60)
    logger.info("RESOLVED CONFIG SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  symbol: {config.symbol}")
    logger.info(f"  tf_exec: {config.exec_tf}")

    other_tfs = sorted([tf for tf in config.all_tfs if tf != config.exec_tf])
    if other_tfs:
        logger.info(f"  other_tfs: {', '.join(other_tfs)}")

    logger.info("-" * 40)
    logger.info(f"  starting_equity_usdt: {config.starting_equity:,.2f}")
    logger.info(f"  max_leverage: {config.max_leverage:.1f}x")
    logger.info(f"  min_trade_notional_usdt: {config.min_trade:.2f}")

    if play.account is not None and play.account.fee_model:
        logger.info(f"  taker_fee_bps: {play.account.fee_model.taker_bps}")
        logger.info(f"  maker_fee_bps: {play.account.fee_model.maker_bps}")
    if play.account is not None and play.account.slippage_bps:
        logger.info(f"  slippage_bps: {play.account.slippage_bps}")

    logger.info("-" * 40)
    for tf in sorted(config.all_tfs):
        warmup = config.warmup_by_tf.get(tf, 0)
        logger.info(f"  warmup_{tf}: {warmup} bars")
    logger.info("=" * 60)


def _compute_smoke_window(
    smoke: bool,
    start: datetime | None,
    end: datetime | None,
    exec_tf: str,
    db_end_ts_ms: int | None,
) -> tuple[datetime | None, datetime | None]:
    """
    Compute start/end window for smoke mode.

    Args:
        smoke: Whether smoke mode is enabled
        start: User-provided start
        end: User-provided end
        exec_tf: Execution timeframe
        db_end_ts_ms: Latest timestamp in DB (epoch ms)

    Returns:
        Tuple of (start, end) datetime values
    """
    if not smoke or not db_end_ts_ms:
        return start, end

    db_latest_dt = datetime.fromtimestamp(db_end_ts_ms / 1000)

    # Use DB latest as end for smoke (not now(), which is always ahead)
    if end is None:
        end = db_latest_dt
        logger.info(f"Smoke mode: using DB latest as end={end}")

    # Use last 100 bars for start
    if start is None:
        tf_minutes = TF_MINUTES.get(exec_tf, 15)
        start = db_latest_dt - timedelta(minutes=tf_minutes * 100)
        logger.info(f"Smoke mode: using last 100 bars, start={start}")

    return start, end


def _validate_indicator_gate(play: Play) -> tuple[bool, dict[str, Any] | None, str | None]:
    """
    Validate indicator requirements gate.

    Args:
        play: Play configuration

    Returns:
        Tuple of (passed, gate_result_dict, error_message)
        If passed is False, error_message contains the failure reason
    """
    from ..backtest.gates.indicator_requirements_gate import (
        validate_indicator_requirements,
        IndicatorGateStatus,
    )

    # Compute expanded keys from Play feature_registry
    available_keys_by_role = {}
    declared_keys_by_role = {}
    registry = play.feature_registry

    for tf in registry.get_all_tfs():
        features = registry.get_for_tf(tf)
        expanded = set()
        for feature in features:
            expanded.add(feature.id)
            if feature.output_keys:
                expanded.update(feature.output_keys)
        available_keys_by_role[tf] = expanded
        declared_keys_by_role[tf] = sorted(expanded)

    gate_result = validate_indicator_requirements(
        play=play,
        available_keys_by_role=available_keys_by_role,
    )

    if gate_result.failed:
        logger.error("INDICATOR REQUIREMENTS GATE FAILED")
        logger.error(gate_result.format_error())
        return False, gate_result.to_dict(), gate_result.error_message

    if gate_result.status == IndicatorGateStatus.PASSED:
        logger.info("[GATE] Indicator requirements: PASSED")
    elif gate_result.status == IndicatorGateStatus.SKIPPED:
        logger.info("[GATE] Indicator requirements: SKIPPED (no required_indicators declared)")

    # Log declared keys
    exec_tf = play.exec_tf
    logger.info(f"Declared indicator keys ({exec_tf}): {declared_keys_by_role.get(exec_tf, [])}")

    return True, gate_result.to_dict(), None


# =============================================================================
# Run Backtest (tools-layer)
# =============================================================================

def backtest_run_play_tool(
    play_id: str,
    env: DataEnv = DEFAULT_BACKTEST_ENV,
    start: datetime | None = None,
    end: datetime | None = None,
    smoke: bool = False,
    write_artifacts: bool = True,
    artifacts_dir: Path | None = None,
    plays_dir: Path | None = None,
    initial_equity_override: float | None = None,
    max_leverage_override: float | None = None,
    emit_snapshots: bool = False,
    sync: bool = True,
    validate_artifacts_after: bool = True,
    skip_preflight: bool = False,
    use_synthetic: bool = False,
) -> ToolResult:
    """
    Run a backtest for an Play.

    This is the GOLDEN PATH for backtest execution.
    All validation, data loading, and execution flows through here.

    Capital/account config comes from Play.account section (required).
    CLI can override specific values using the override parameters.

    Args:
        play_id: Play identifier
        env: Data environment ("live" or "demo")
        start: Window start
        end: Window end
        smoke: If True, run fast smoke check (small window if not provided)
        write_artifacts: If True, write result artifacts
        artifacts_dir: Override artifacts directory
        plays_dir: Override Play directory
        initial_equity_override: Override starting equity (defaults to Play.account.starting_equity_usdt)
        max_leverage_override: Override max leverage (defaults to Play.account.max_leverage)
        sync: If True (default), auto-fetch and fix missing data during preflight
        validate_artifacts_after: If True (default), validate artifacts after run (HARD FAIL if invalid)
        skip_preflight: If True, skip preflight checks. Use for parallel execution where
                       data was already synced by the parent process.
        use_synthetic: If True and Play has a synthetic: block, use synthetic data.
                      If False (default), the synthetic block is ignored and real data is used.

    Returns:
        ToolResult with backtest results

    Note:
        Symbol is taken from the Play configuration (Play.symbol_universe[0]).
        Plays are self-contained and deterministic.
    """
    preflight_result = None
    try:
        # Load Play FIRST to check for synthetic config
        play = load_play(play_id, base_dir=plays_dir)

        # Synthetic mode requires play to have a validation: block
        synthetic_provider = None
        if use_synthetic:
            if play.validation is None:
                raise ValueError(
                    f"Play '{play_id}' has no validation: block. "
                    f"Add a validation: section with pattern: to the play YAML."
                )

            from src.forge.validation import generate_synthetic_candles
            from src.forge.validation.synthetic_provider import SyntheticCandlesProvider
            from src.backtest.execution_validation import compute_synthetic_bars

            # Auto-compute bars from indicator/structure warmup requirements
            synthetic_bars = compute_synthetic_bars(play)
            synthetic_pattern = play.validation.pattern

            # Collect required timeframes
            exec_tf = play.exec_tf
            required_tfs = {exec_tf, "1m"}  # Always need exec and 1m
            if play.low_tf:
                required_tfs.add(play.low_tf)
            if play.med_tf:
                required_tfs.add(play.med_tf)
            if play.high_tf:
                required_tfs.add(play.high_tf)
            for tf in play.feature_registry.get_all_tfs():
                required_tfs.add(tf)

            print(f"[SYNTHETIC] Auto-generating data ({synthetic_bars} bars from indicator/structure warmup)")
            print(f"[SYNTHETIC] Pattern: {synthetic_pattern}, Bars: {synthetic_bars}")
            print(f"[SYNTHETIC] Required TFs: {sorted(required_tfs)}")

            # Generate synthetic candles
            from src.forge.validation.synthetic_data import PatternType
            candles = generate_synthetic_candles(
                symbol=play.symbol_universe[0] if play.symbol_universe else "BTCUSDT",
                timeframes=list(required_tfs),
                bars_per_tf=synthetic_bars,
                seed=42,
                pattern=cast(PatternType, synthetic_pattern),
            )

            # Create provider and set window from synthetic data
            synthetic_provider = SyntheticCandlesProvider(candles)
            data_start, data_end = synthetic_provider.get_data_range(exec_tf)
            start = data_start
            end = data_end
            skip_preflight = True  # No DB data to validate

            print(f"[SYNTHETIC] Data range: {start} to {end}")
            print(f"[SYNTHETIC] Data hash: {candles.data_hash}")
            preflight_data = {"synthetic": True, "data_hash": candles.data_hash}

        # Skip preflight if requested or if using synthetic data
        elif skip_preflight:
            logger.warning("[WARN] --skip-preflight bypasses ALL data validation!")
            logger.warning("[WARN] Use only for testing. Production runs MUST use preflight gate.")
            preflight_data = {}
        else:
            # Run preflight first (with auto-sync if sync=True)
            preflight_result = backtest_preflight_play_tool(
                play_id=play_id,
                env=env,
                start=start,
                end=end,
                plays_dir=plays_dir,
                sync=sync,
            )

            if not preflight_result.success:
                return preflight_result

            preflight_data = preflight_result.data

        # Validate account config is present (required - no defaults)
        if play.account is None:
            return ToolResult(
                success=False,
                error=(
                    f"Play '{play_id}' is missing account section. "
                    "account.starting_equity_usdt and account.max_leverage are required."
                ),
            )

        # Resolve configuration from Play and overrides
        assert preflight_data is not None
        config = _resolve_backtest_config(
            play=play,
            preflight_data=preflight_data,
            initial_equity_override=initial_equity_override,
            max_leverage_override=max_leverage_override,
        )
        resolved_symbol = config.symbol
        exec_tf = config.exec_tf

        # Log resolved configuration
        _log_backtest_config(config, play)

        # Compute smoke window if applicable
        coverage = preflight_data.get("coverage", {})
        db_end_ts_ms = coverage.get("db_end_ts_ms")
        start, end = _compute_smoke_window(smoke, start, end, exec_tf, db_end_ts_ms)

        # Normalize timestamps
        if start:
            start = normalize_timestamp(start)
        if end:
            end = normalize_timestamp(end)
        else:
            end = datetime.now().replace(tzinfo=None)

        # Validate indicator requirements gate
        gate_passed, gate_result_dict, gate_error = _validate_indicator_gate(play)
        if not gate_passed:
            return ToolResult(
                success=False,
                error=gate_error,
                data={
                    "gate": "indicator_requirements",
                    "result": gate_result_dict,
                    "preflight": preflight_data,
                },
            )

        # Use the existing runner infrastructure
        from ..backtest.runner import (
            RunnerConfig,
            RunnerResult,
            run_backtest_with_gates,
        )

        # Set default artifacts dir
        if artifacts_dir is None:
            artifacts_dir = Path("backtests")

        # Create data_loader from HistoricalDataStore
        # Skip DuckDB entirely for synthetic runs (no DB access needed)
        data_loader_fn: Callable[[str, str, datetime, datetime], pd.DataFrame] | None = None
        if synthetic_provider is None:
            store = get_historical_store(env=env)

            def data_loader(symbol: str, tf: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
                """Load OHLCV data from DuckDB."""
                df = store.get_ohlcv(symbol, tf, start=start_dt, end=end_dt)
                if df is None:
                    return pd.DataFrame()
                return df

            data_loader_fn = data_loader

        # Build runner config with correct field names
        # NOTE: skip_preflight=True because CLI wrapper already ran its own preflight
        # The runner's preflight is more strict (checks high_tf/med_tf warmup separately)
        # For smoke tests, we trust the CLI wrapper's preflight check
        # NOTE: skip_artifact_validation=True because we skip preflight (no preflight_report.json)
        runner_config = RunnerConfig(
            play_id=play_id,
            play=play,
            window_start=start,
            window_end=end,
            base_output_dir=artifacts_dir,
            plays_dir=plays_dir,
            skip_preflight=True,  # CLI wrapper already validated
            skip_artifact_validation=True,  # Skip because preflight is skipped (no preflight_report.json)
            data_loader=data_loader_fn,
            emit_snapshots=emit_snapshots,
            data_env=env,  # Pass data environment for correct DB selection
        )

        # Run backtest with gates
        # P1.2 Refactor: engine_factory is now handled internally via create_engine_from_play()
        run_result = run_backtest_with_gates(
            config=runner_config,
            synthetic_provider=synthetic_provider,
        )

        # Extract results
        if not run_result.success:
            return ToolResult(
                success=False,
                error=run_result.error_message or "Backtest failed",
                symbol=resolved_symbol,
                data={
                    "preflight": preflight_data,
                    "run_result": run_result.to_dict(),
                    "gate_failed": run_result.gate_failed,
                },
            )

        # Build result summary
        summary = run_result.summary
        trades_count = summary.trades_count if summary else 0

        result_data = {
            "preflight": preflight_data,
            "play_id": play_id,
            "symbol": resolved_symbol,
            "exec_tf": exec_tf,
            "env": env,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "smoke": smoke,
            "trades_count": trades_count,
            "run_id": run_result.run_id,
        }

        if summary:
            result_data["summary"] = summary.to_dict()

        if run_result.artifact_path:
            result_data["artifact_dir"] = str(run_result.artifact_path)

            # Phase 2: Post-backtest artifact validation gate
            # Validates all artifacts exist and conform to standards
            if validate_artifacts_after:
                from ..backtest.artifacts import validate_artifacts

                artifact_validation = validate_artifacts(run_result.artifact_path)
                result_data["artifact_validation"] = artifact_validation.to_dict()

                if not artifact_validation.passed:
                    # HARD FAIL: Artifact validation failures must be caught early
                    logger.warning(
                        f"Artifact validation FAILED: {artifact_validation.errors + artifact_validation.pipeline_signature_errors}"
                    )
                    return ToolResult(
                        success=False,
                        error="Artifact validation failed - see artifact_validation in data for details",
                        symbol=resolved_symbol,
                        data=result_data,
                    )
                else:
                    logger.info("[GATE] Artifact validation: PASSED")
                    if artifact_validation.pipeline_signature_valid:
                        logger.info("[GATE] Pipeline signature: VALID")
            else:
                logger.info("[GATE] Artifact validation: SKIPPED (--no-validate)")

        return ToolResult(
            success=True,
            message=f"Backtest complete: {trades_count} trades",
            symbol=resolved_symbol,
            data=result_data,
        )

    except KeyError as e:
        # Indicator key error - provide helpful message
        error_msg = str(e)
        available_info = ""
        if "not declared" in error_msg.lower() or "available" in error_msg.lower():
            available_info = " Check declared_keys in preflight output."

        return ToolResult(
            success=False,
            error=f"Indicator key error: {error_msg}{available_info}",
            data={"preflight": preflight_result.data if preflight_result and preflight_result.success else None},
        )

    except ValueError as e:
        error_msg = str(e)
        # Check for NaN errors and provide warmup guidance
        if "nan" in error_msg.lower():
            guidance = (
                " This may be a warmup issue (not enough bars before window start) "
                "or insufficient DB coverage. Check effective_start in preflight output."
            )
            error_msg += guidance

        return ToolResult(
            success=False,
            error=error_msg,
            data={"preflight": preflight_result.data if preflight_result and preflight_result.success else None},
        )

    except Exception as e:
        logger.error(f"Backtest run failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Backtest error: {e}",
        )


