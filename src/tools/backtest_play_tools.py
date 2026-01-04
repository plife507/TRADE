"""
Play-based backtest tools.

This module contains all tools for Play workflow:
- Preflight check (data coverage validation)
- Run backtest (full execution)
- Indicator discovery (key listing)
- Data fix (sync/heal)
- List Plays
- Normalize Play (validation)

All tools are the GOLDEN PATH for backtest execution.
CLI and agents should use these tools, not direct engine access.
"""

from datetime import datetime, timedelta
from pathlib import Path
import traceback

import pandas as pd

from .shared import ToolResult
from ..config.constants import (
    DataEnv,
    DEFAULT_DATA_ENV,
    validate_data_env,
    validate_symbol,
    resolve_db_path,
    resolve_table_name,
)
from ..data.historical_data_store import (
    get_historical_store,
    TIMEFRAMES as DB_TIMEFRAMES,
    TF_MINUTES,
)
from ..backtest.play import load_play, list_plays, Play
from ..backtest.execution_validation import (
    validate_play_full,
    compute_warmup_requirements,
    get_declared_features_by_role,
)
from ..backtest.indicators import get_required_indicator_columns_from_specs
from ..backtest.system_config import validate_usdt_pair
from ..backtest.runtime.preflight import run_preflight_gate, PreflightReport, AutoSyncConfig
from ..utils.logger import get_logger


logger = get_logger()


# =============================================================================
# Canonical Timeframe Validation
# =============================================================================

# Canonical timeframes accepted by CLI (stored in DuckDB as-is)
CANONICAL_TIMEFRAMES = {"1m", "5m", "15m", "1h", "4h", "1d"}

# Bybit API intervals (NOT accepted - user must use canonical)
BYBIT_API_INTERVALS = {"1", "5", "15", "60", "240", "D"}

# Mapping from Bybit API interval to canonical
BYBIT_TO_CANONICAL = {
    "1": "1m",
    "5": "5m",
    "15": "15m",
    "60": "1h",
    "240": "4h",
    "D": "1d",
}


def validate_canonical_tf(tf: str) -> str:
    """
    Validate timeframe is canonical format.

    Args:
        tf: Timeframe string (e.g., "1h", "15m")

    Returns:
        Validated canonical tf string

    Raises:
        ValueError: If tf is not canonical (with fix-it message)
    """
    tf_lower = tf.lower().strip()

    if tf_lower in CANONICAL_TIMEFRAMES:
        return tf_lower

    # Check if it's a Bybit API interval
    if tf in BYBIT_API_INTERVALS:
        canonical = BYBIT_TO_CANONICAL.get(tf, tf)
        raise ValueError(
            f"Timeframe '{tf}' is a Bybit API interval, not canonical. "
            f"Use '{canonical}' instead. "
            f"Canonical timeframes: {sorted(CANONICAL_TIMEFRAMES)}"
        )

    raise ValueError(
        f"Invalid timeframe: '{tf}'. "
        f"Must be one of: {sorted(CANONICAL_TIMEFRAMES)}"
    )


def normalize_timestamp(dt: datetime) -> datetime:
    """
    Normalize timestamp to UTC-naive for DuckDB storage.

    DuckDB stores timestamps as UTC-naive. If user passes tz-aware datetime,
    we strip the timezone info and log the normalization.

    Args:
        dt: Datetime (may be tz-aware)

    Returns:
        UTC-naive datetime
    """
    if dt.tzinfo is not None:
        # Convert to UTC first if needed, then strip
        try:
            dt_utc = dt.utctimetuple()
            dt = datetime(*dt_utc[:6])
        except Exception:
            # Just strip tzinfo if conversion fails
            dt = dt.replace(tzinfo=None)
        logger.info(f"Normalized tz-aware timestamp to UTC-naive: {dt}")
    return dt


# =============================================================================
# Preflight Check (tools-layer)
# =============================================================================

def backtest_preflight_play_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    idea_cards_dir: Path | None = None,
    symbol_override: str | None = None,
    fix_gaps: bool = False,
) -> ToolResult:
    """
    Run preflight check for an Play backtest using production preflight gate.

    Phase 6: Calls run_preflight_gate() and returns PreflightReport.to_dict() unchanged.

    Args:
        idea_card_id: Play identifier
        env: Data environment ("live" or "demo")
        symbol: Override symbol (default: first in Play.symbol_universe)
        start: Window start (required)
        end: Window end (default: now)
        idea_cards_dir: Override Play directory
        symbol_override: Alias for symbol (Phase 6 smoke test support)
        fix_gaps: If True, auto-fetch and fix missing data (uses data tools)

    Returns:
        ToolResult with PreflightReport.to_dict() in data
    """
    try:
        # Phase 6: symbol_override is an alias for symbol
        if symbol_override and not symbol:
            symbol = symbol_override

        # Validate env
        env = validate_data_env(env)
        db_path = resolve_db_path(env)

        # Load Play
        try:
            idea_card = load_play(idea_card_id, base_dir=idea_cards_dir)
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=str(e),
                data={
                    "env": env,
                    "db_path": str(db_path),
                    "available_idea_cards": list_plays(idea_cards_dir),
                },
            )

        # Validate Play
        validation = validate_play_full(idea_card)
        if not validation.is_valid:
            return ToolResult(
                success=False,
                error=f"Play validation failed: {[i.message for i in validation.errors]}",
                data={"validation_errors": [i.message for i in validation.errors]},
            )

        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return ToolResult(
                    success=False,
                    error="Play has no symbols in symbol_universe and none provided",
                )
            symbol = idea_card.symbol_universe[0]

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
            exec_tf = validate_canonical_tf(idea_card.exec_tf)
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
        if fix_gaps:
            auto_sync_config = AutoSyncConfig(
                enabled=True,
                max_attempts=2,
                data_env=env,
            )

        preflight_report = run_preflight_gate(
            idea_card=idea_card,
            data_loader=data_loader,
            window_start=start,
            window_end=end,
            auto_sync_missing=fix_gaps,
            auto_sync_config=auto_sync_config,
        )

        # Get exec TF info for message
        exec_tf = validate_canonical_tf(idea_card.exec_tf)

        # Return PreflightReport.to_dict() unchanged (Phase 6 requirement)
        report_dict = preflight_report.to_dict()

        # Add env info for convenience
        report_dict["env"] = env
        report_dict["db_path"] = str(db_path)
        report_dict["symbol"] = symbol

        if preflight_report.overall_status.value == "passed":
            return ToolResult(
                success=True,
                message=f"Preflight OK for {idea_card_id}: {symbol} {exec_tf}",
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
# Run Backtest (tools-layer)
# =============================================================================

def backtest_run_play_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    smoke: bool = False,
    strict: bool = True,
    write_artifacts: bool = True,
    artifacts_dir: Path | None = None,
    idea_cards_dir: Path | None = None,
    initial_equity_override: float | None = None,
    max_leverage_override: float | None = None,
    emit_snapshots: bool = False,
    symbol_override: str | None = None,
    fix_gaps: bool = True,
    validate_artifacts_after: bool = True,
) -> ToolResult:
    """
    Run a backtest for an Play.

    This is the GOLDEN PATH for backtest execution.
    All validation, data loading, and execution flows through here.

    Capital/account config comes from Play.account section (required).
    CLI can override specific values using the override parameters.

    Args:
        idea_card_id: Play identifier
        env: Data environment ("live" or "demo")
        symbol: Override symbol
        start: Window start
        end: Window end
        smoke: If True, run fast smoke check (small window if not provided)
        strict: If True, use strict indicator access (default: True)
        write_artifacts: If True, write result artifacts
        artifacts_dir: Override artifacts directory
        idea_cards_dir: Override Play directory
        initial_equity_override: Override starting equity (defaults to Play.account.starting_equity_usdt)
        max_leverage_override: Override max leverage (defaults to Play.account.max_leverage)
        symbol_override: Alias for symbol (Phase 6 smoke test support)
        fix_gaps: If True (default), auto-fetch and fix missing data during preflight
        validate_artifacts_after: If True (default), validate artifacts after run (HARD FAIL if invalid)

    Returns:
        ToolResult with backtest results
    """
    try:
        # Phase 6: symbol_override is an alias for symbol
        if symbol_override and not symbol:
            symbol = symbol_override

        # Run preflight first (with auto-sync if fix_gaps=True)
        preflight_result = backtest_preflight_play_tool(
            idea_card_id=idea_card_id,
            env=env,
            symbol=symbol,
            start=start,
            end=end,
            idea_cards_dir=idea_cards_dir,
            fix_gaps=fix_gaps,
        )

        if not preflight_result.success:
            return preflight_result

        preflight_data = preflight_result.data

        # Load Play
        idea_card = load_play(idea_card_id, base_dir=idea_cards_dir)

        # Validate account config is present (required - no defaults)
        if idea_card.account is None:
            return ToolResult(
                success=False,
                error=(
                    f"Play '{idea_card_id}' is missing account section. "
                    "account.starting_equity_usdt and account.max_leverage are required."
                ),
            )

        # Resolve config values (Play is source of truth, CLI can override)
        resolved_starting_equity = (
            initial_equity_override
            if initial_equity_override is not None
            else idea_card.account.starting_equity_usdt
        )
        resolved_max_leverage = (
            max_leverage_override
            if max_leverage_override is not None
            else idea_card.account.max_leverage
        )
        resolved_min_trade = idea_card.account.min_trade_notional_usdt or 1.0

        # Resolve symbol from preflight data or Play
        resolved_symbol = preflight_data.get("symbol") or idea_card.symbol_universe[0]
        exec_tf = validate_canonical_tf(idea_card.exec_tf)

        # Print Resolved Config Summary (Phase 5.3 requirement)
        logger.info("=" * 60)
        logger.info("RESOLVED CONFIG SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  symbol: {resolved_symbol}")
        logger.info(f"  tf_exec: {exec_tf}")
        # Show all unique TFs from features
        all_tfs = idea_card.get_all_tfs()
        other_tfs = sorted([tf for tf in all_tfs if tf != exec_tf])
        if other_tfs:
            logger.info(f"  other_tfs: {', '.join(other_tfs)}")
        logger.info("-" * 40)
        logger.info(f"  starting_equity_usdt: {resolved_starting_equity:,.2f}")
        logger.info(f"  max_leverage: {resolved_max_leverage:.1f}x")
        logger.info(f"  min_trade_notional_usdt: {resolved_min_trade:.2f}")
        if idea_card.account.fee_model:
            logger.info(f"  taker_fee_bps: {idea_card.account.fee_model.taker_bps}")
            logger.info(f"  maker_fee_bps: {idea_card.account.fee_model.maker_bps}")
        if idea_card.account.slippage_bps:
            logger.info(f"  slippage_bps: {idea_card.account.slippage_bps}")
        logger.info("-" * 40)
        # Warmup spans - use feature_registry
        from ..backtest.execution_validation import compute_warmup_requirements
        warmup_reqs = compute_warmup_requirements(idea_card)
        for tf in sorted(all_tfs):
            warmup = warmup_reqs.warmup_by_role.get(tf, 0)
            logger.info(f"  warmup_{tf}: {warmup} bars")
        logger.info("=" * 60)

        # If smoke mode and no start/end provided, use last 100 bars from DB
        # Get db_latest from coverage data (epoch-ms)
        coverage = preflight_data.get("coverage", {})
        db_end_ts_ms = coverage.get("db_end_ts_ms")
        db_latest_dt = None
        if db_end_ts_ms:
            db_latest_dt = datetime.fromtimestamp(db_end_ts_ms / 1000)

        if smoke:
            if db_latest_dt:
                # Use DB latest as end for smoke (not now(), which is always ahead)
                if end is None:
                    end = db_latest_dt
                    logger.info(f"Smoke mode: using DB latest as end={end}")

                # Use last 100 bars for start
                if start is None:
                    tf_minutes = TF_MINUTES.get(exec_tf, 15)
                    start = db_latest_dt - timedelta(minutes=tf_minutes * 100)
                    logger.info(f"Smoke mode: using last 100 bars, start={start}")

        # Normalize timestamps
        if start:
            start = normalize_timestamp(start)
        if end:
            end = normalize_timestamp(end)
        else:
            end = datetime.now().replace(tzinfo=None)

        # =====================================================================
        # GATE: Indicator Requirements Validation
        # Validates that required indicators are declared in FeatureSpecs
        # =====================================================================
        from ..backtest.gates.indicator_requirements_gate import (
            validate_indicator_requirements,
            IndicatorGateStatus,
        )

        # Compute expanded keys from Play feature_registry
        available_keys_by_role = {}
        declared_keys_by_role = {}
        registry = idea_card.feature_registry
        for tf in registry.get_all_tfs():
            features = registry.get_for_tf(tf)
            expanded = set()
            for feature in features:
                expanded.add(feature.id)
                if feature.output_keys:
                    expanded.update(feature.output_keys)
            available_keys_by_role[tf] = expanded
            declared_keys_by_role[tf] = sorted(expanded)

        indicator_gate_result = validate_indicator_requirements(
            idea_card=idea_card,
            available_keys_by_role=available_keys_by_role,
        )

        if indicator_gate_result.failed:
            logger.error("INDICATOR REQUIREMENTS GATE FAILED")
            logger.error(indicator_gate_result.format_error())
            return ToolResult(
                success=False,
                error=indicator_gate_result.error_message,
                data={
                    "gate": "indicator_requirements",
                    "result": indicator_gate_result.to_dict(),
                    "preflight": preflight_data,
                },
            )

        if indicator_gate_result.status == IndicatorGateStatus.PASSED:
            logger.info("[GATE] Indicator requirements: PASSED")
        elif indicator_gate_result.status == IndicatorGateStatus.SKIPPED:
            logger.info("[GATE] Indicator requirements: SKIPPED (no required_indicators declared)")

        # Print indicator keys (Phase B requirement)
        exec_tf = idea_card.execution_tf
        logger.info(f"Declared indicator keys ({exec_tf}): {declared_keys_by_role.get(exec_tf, [])}")

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
        store = get_historical_store(env=env)

        def data_loader(symbol: str, tf: str, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
            """Load OHLCV data from DuckDB."""
            df = store.get_ohlcv(symbol, tf, start=start_dt, end=end_dt)
            if df is None:
                return pd.DataFrame()
            return df

        # Build runner config with correct field names
        # NOTE: skip_preflight=True because CLI wrapper already ran its own preflight
        # The runner's preflight is more strict (checks HTF/MTF warmup separately)
        # For smoke tests, we trust the CLI wrapper's preflight check
        # NOTE: skip_artifact_validation=True because we skip preflight (no preflight_report.json)
        runner_config = RunnerConfig(
            idea_card_id=idea_card_id,
            idea_card=idea_card,
            window_start=start,
            window_end=end,
            base_output_dir=artifacts_dir,
            idea_cards_dir=idea_cards_dir,
            skip_preflight=True,  # CLI wrapper already validated
            skip_artifact_validation=True,  # Skip because preflight is skipped (no preflight_report.json)
            data_loader=data_loader,
            emit_snapshots=emit_snapshots,
        )

        # Run backtest with gates
        # P1.2 Refactor: engine_factory is now handled internally via create_engine_from_play()
        run_result = run_backtest_with_gates(
            config=runner_config,
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
            "idea_card_id": idea_card_id,
            "symbol": resolved_symbol,
            "exec_tf": exec_tf,
            "env": env,
            "start": start.isoformat() if start else None,
            "end": end.isoformat() if end else None,
            "smoke": smoke,
            "strict": strict,
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
            data={"preflight": preflight_result.data if preflight_result.success else None},
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
            data={"preflight": preflight_result.data if preflight_result.success else None},
        )

    except Exception as e:
        logger.error(f"Backtest run failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Backtest error: {e}",
        )


# =============================================================================
# Indicator Key Discovery (tools-layer)
# =============================================================================

def backtest_indicators_tool(
    idea_card_id: str,
    data_env: DataEnv = DEFAULT_DATA_ENV,
    symbol: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    idea_cards_dir: Path | None = None,
    compute_values: bool = False,
) -> ToolResult:
    """
    Discover and print indicator keys for an Play.

    This command replaces pytest-based indicator key validation.
    Run this to see exactly what indicator keys will be computed
    so you can fix FeatureSpec/Play declarations.

    Args:
        idea_card_id: Play identifier
        data_env: Data environment ("live" or "demo")
        symbol: Override symbol
        start: Window start (for computing actual values)
        end: Window end
        idea_cards_dir: Override Play directory
        compute_values: If True, actually compute indicators and show first non-NaN index

    Returns:
        ToolResult with indicator key discovery results
    """
    try:
        # Validate env
        data_env = validate_data_env(data_env)
        db_path = resolve_db_path(data_env)
        ohlcv_table = resolve_table_name("ohlcv", data_env)

        # Load Play
        try:
            idea_card = load_play(idea_card_id, base_dir=idea_cards_dir)
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=str(e),
                data={"available_idea_cards": list_plays(idea_cards_dir)},
            )

        # Validate Play
        validation = validate_play_full(idea_card)
        if not validation.is_valid:
            return ToolResult(
                success=False,
                error=f"Play validation failed: {[i.message for i in validation.errors]}",
            )

        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return ToolResult(
                    success=False,
                    error="Play has no symbols and none provided",
                )
            symbol = idea_card.symbol_universe[0]

        symbol = validate_symbol(symbol)

        # Get all features by TF from registry
        registry = idea_card.feature_registry
        all_tfs = registry.get_all_tfs()
        declared_keys_by_role = {}
        expanded_keys_by_role = {}

        for tf in all_tfs:
            features = registry.get_for_tf(tf)
            declared = set()
            expanded = set()
            for feature in features:
                declared.add(feature.id)
                expanded.add(feature.id)
                if feature.output_keys:
                    expanded.update(feature.output_keys)
            declared_keys_by_role[tf] = sorted(declared)
            expanded_keys_by_role[tf] = sorted(expanded)

        # Build result
        result_data = {
            "idea_card_id": idea_card_id,
            "data_env": data_env,
            "db_path": str(db_path),
            "symbol": symbol,
            "exec_tf": idea_card.exec_tf,
            "all_tfs": sorted(all_tfs),
            "declared_keys_by_role": declared_keys_by_role,
            "expanded_keys_by_role": expanded_keys_by_role,
            "total_declared_keys": sum(len(v) for v in declared_keys_by_role.values()),
            "total_expanded_keys": sum(len(v) for v in expanded_keys_by_role.values()),
        }

        # If compute_values, actually load data and compute indicators
        # Note: This feature requires further refactoring to work with new schema
        if compute_values and start and end:
            logger.warning("compute_values not yet supported with new Play schema")
            result_data["computed_info"] = {"warning": "Not yet supported"}

        # Log output
        logger.info(f"Indicator key discovery for {idea_card_id}:")
        for tf in sorted(all_tfs):
            if tf in declared_keys_by_role:
                declared = declared_keys_by_role[tf]
                expanded = expanded_keys_by_role[tf]
                logger.info(f"  {tf}:")
                logger.info(f"    declared: {declared}")
                logger.info(f"    expanded: {expanded}")

        return ToolResult(
            success=True,
            message=f"Found {result_data['total_expanded_keys']} indicator keys across {len(all_tfs)} TFs",
            symbol=symbol,
            data=result_data,
        )

    except Exception as e:
        logger.error(f"Indicator discovery failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Indicator discovery error: {e}",
        )


# =============================================================================
# Data Fix (tools-layer dispatch to existing tools)
# =============================================================================

def _datetime_to_epoch_ms(dt: datetime | None) -> int | None:
    """Convert datetime to epoch milliseconds."""
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def backtest_data_fix_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: str | None = None,
    start: datetime | None = None,
    end: datetime | None = None,
    max_lookback_days: int = 7,
    sync_to_now: bool = False,
    fill_gaps: bool = True,
    heal: bool = False,
    idea_cards_dir: Path | None = None,
) -> ToolResult:
    """
    Fix data for an Play backtest by calling existing data tools.

    Phase 6: Bounded enforcement + progress tracking + structured result.

    Args:
        idea_card_id: Play identifier
        env: Data environment
        symbol: Override symbol
        start: Sync from this date (default: Play warmup requirements)
        end: Sync to this date (required for bounded mode)
        max_lookback_days: Max lookback days (default 7). If (end - start) > this, clamp start.
        sync_to_now: If True, sync data to current time
        fill_gaps: If True, fill gaps after sync
        heal: If True, run full heal after sync
        idea_cards_dir: Override Play directory

    Returns:
        ToolResult with structured data fix summary including bounds and progress
    """
    from .data_tools import (
        sync_range_tool,
        sync_to_now_and_fill_gaps_tool,
        fill_gaps_tool,
        heal_data_tool,
    )

    try:
        # Validate env
        env = validate_data_env(env)
        db_path = resolve_db_path(env)

        # Load Play to get TFs
        idea_card = load_play(idea_card_id, base_dir=idea_cards_dir)

        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return ToolResult(
                    success=False,
                    error="Play has no symbols and none provided",
                )
            symbol = idea_card.symbol_universe[0]

        symbol = validate_symbol(symbol)

        # Get all TFs from Play + mandatory 1m for price feed
        tfs = set(idea_card.get_all_tfs())
        # 1m is mandatory for price feed (quote proxy) - always include
        tfs.add("1m")
        tfs = sorted(tfs)

        # Phase 6: Track progress via callback counter
        progress_lines_count = 0

        def progress_callback(sym: str, tf: str, msg: str):
            nonlocal progress_lines_count
            progress_lines_count += 1
            logger.info(f"  [{sym} {tf}] {msg}")

        operations = []

        # Phase 6: Bounded enforcement
        bounds_applied = False
        original_start = start

        if end is None:
            end = datetime.now().replace(tzinfo=None)
        else:
            end = normalize_timestamp(end)

        if start:
            start = normalize_timestamp(start)
            requested_days = (end - start).days

            if requested_days > max_lookback_days:
                # Clamp start to end - max_lookback_days
                start = end - timedelta(days=max_lookback_days)
                bounds_applied = True
                logger.info(f"Data-fix: Clamped start from {original_start} to {start} (max_lookback_days={max_lookback_days})")

        # Build bounds info
        bounds = {
            "start_ts_ms": _datetime_to_epoch_ms(start),
            "end_ts_ms": _datetime_to_epoch_ms(end),
            "cap": {"max_lookback_days": max_lookback_days},
            "applied": bounds_applied,
        }

        logger.info(f"Data fix for {idea_card_id}: env={env}, db={db_path}, symbol={symbol}, tfs={tfs}")
        if bounds_applied:
            logger.info(f"  Bounds applied: start clamped to {start}")

        # Sync range if start provided
        if start and not sync_to_now:
            result = sync_range_tool(
                symbols=[symbol],
                start=start,
                end=end,
                timeframes=tfs,
                env=env,
            )
            operations.append({
                "name": "sync_range",
                "success": result.success,
                "message": result.message if result.success else result.error,
            })
            # Count as progress line
            progress_lines_count += 1

        # Sync to now + fill gaps
        if sync_to_now:
            result = sync_to_now_and_fill_gaps_tool(
                symbols=[symbol],
                timeframes=tfs,
                env=env,
            )
            operations.append({
                "name": "sync_to_now_and_fill_gaps",
                "success": result.success,
                "message": result.message if result.success else result.error,
            })
            progress_lines_count += 1

        # Fill gaps
        if fill_gaps and not sync_to_now:
            for tf in tfs:
                result = fill_gaps_tool(
                    symbol=symbol,
                    timeframe=tf,
                    env=env,
                )
                operations.append({
                    "name": "fill_gaps",
                    "tf": tf,
                    "success": result.success,
                    "message": result.message if result.success else result.error,
                })
                progress_lines_count += 1

        # Heal
        if heal:
            result = heal_data_tool(
                symbol=symbol,
                env=env,
            )
            operations.append({
                "name": "heal",
                "success": result.success,
                "message": result.message if result.success else result.error,
            })
            progress_lines_count += 1

        # Summarize - Phase 6: structured result with bounds, operations, progress
        all_success = all(op.get("success", False) for op in operations)
        summary = {
            "env": env,
            "db_path": str(db_path),
            "symbol": symbol,
            "tfs": tfs,
            "bounds": bounds,
            "operations": operations,
            "progress_lines_count": progress_lines_count,
        }

        if all_success:
            return ToolResult(
                success=True,
                message=f"Data fix complete for {symbol}: {len(operations)} operations, bounds_applied={bounds_applied}",
                symbol=symbol,
                data=summary,
            )
        else:
            failed = [op["name"] for op in operations if not op.get("success", False)]
            return ToolResult(
                success=False,
                error=f"Some operations failed: {failed}",
                symbol=symbol,
                data=summary,
            )

    except Exception as e:
        logger.error(f"Data fix failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Data fix error: {e}",
        )


# =============================================================================
# List Plays (tools-layer)
# =============================================================================

def backtest_list_plays_tool(
    idea_cards_dir: Path | None = None,
) -> ToolResult:
    """
    List available Plays.

    Args:
        idea_cards_dir: Override Play directory

    Returns:
        ToolResult with list of Play IDs
    """
    try:
        cards = list_plays(base_dir=idea_cards_dir)

        return ToolResult(
            success=True,
            message=f"Found {len(cards)} Plays",
            data={
                "idea_cards": cards,
                "directory": str(idea_cards_dir) if idea_cards_dir else "configs/plays/",
            },
        )

    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to list Plays: {e}",
        )


# =============================================================================
# Play Normalization (build-time validation)
# =============================================================================

def backtest_play_normalize_tool(
    idea_card_id: str,
    idea_cards_dir: Path | None = None,
    write_in_place: bool = False,
) -> ToolResult:
    """
    Normalize and validate an Play YAML at build time.

    This command validates:
    - All indicator_types are supported
    - All params are accepted by each indicator
    - All signal_rules/risk_model references use expanded keys (not base keys)

    If validation passes and write_in_place=True, writes the normalized YAML
    with auto-generated required_indicators.

    Agent Rule:
        Agents may only generate Plays through this command and must
        refuse to write YAML if normalization fails.

    Args:
        idea_card_id: Play identifier
        idea_cards_dir: Override Play directory
        write_in_place: If True, write normalized YAML back to file

    Returns:
        ToolResult with validation results
    """
    import yaml
    from ..backtest.play import IDEA_CARDS_DIR
    from ..backtest.play_yaml_builder import (
        normalize_play_yaml,
        format_validation_errors,
    )

    try:
        # Resolve path
        search_dir = idea_cards_dir or IDEA_CARDS_DIR
        yaml_path = None

        for ext in (".yml", ".yaml"):
            path = search_dir / f"{idea_card_id}{ext}"
            if path.exists():
                yaml_path = path
                break

        if yaml_path is None:
            cards = list_plays(base_dir=idea_cards_dir)
            return ToolResult(
                success=False,
                error=f"Play '{idea_card_id}' not found in {search_dir}",
                data={"available_idea_cards": cards},
            )

        # Load raw YAML
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        if not raw:
            return ToolResult(
                success=False,
                error=f"Empty or invalid YAML in {yaml_path}",
            )

        # Normalize and validate
        normalized, result = normalize_play_yaml(raw, auto_generate_required=True)

        if not result.is_valid:
            error_details = format_validation_errors(result.errors)
            return ToolResult(
                success=False,
                error=f"Play validation failed with {len(result.errors)} error(s)",
                data={
                    "idea_card_id": idea_card_id,
                    "yaml_path": str(yaml_path),
                    "errors": [e.to_dict() for e in result.errors],
                    "error_details": error_details,
                },
            )

        # If write_in_place, write back the normalized YAML
        if write_in_place:
            with open(yaml_path, "w", encoding="utf-8") as f:
                yaml.dump(normalized, f, sort_keys=False, default_flow_style=False)

            return ToolResult(
                success=True,
                message=f"Play '{idea_card_id}' normalized and written to {yaml_path}",
                data={
                    "idea_card_id": idea_card_id,
                    "yaml_path": str(yaml_path),
                    "normalized": True,
                    "written": True,
                },
            )

        # Dry-run: just return validation success
        return ToolResult(
            success=True,
            message=f"Play '{idea_card_id}' passed validation (dry-run, not written)",
            data={
                "idea_card_id": idea_card_id,
                "yaml_path": str(yaml_path),
                "normalized": True,
                "written": False,
                "warnings": result.warnings,
            },
        )

    except Exception as e:
        logger.error(f"Play normalization failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Normalization error: {e}",
        )


def backtest_idea_card_normalize_batch_tool(
    idea_cards_dir: Path,
    write_in_place: bool = False,
) -> ToolResult:
    """
    Batch normalize all Plays in a directory.

    Args:
        idea_cards_dir: Directory containing Play YAML files
        write_in_place: If True, write normalized YAML back to files

    Returns:
        ToolResult with batch normalization results
    """
    try:
        from ..backtest.play import list_plays

        # Get all Play IDs in the directory
        idea_card_ids = list_plays(base_dir=idea_cards_dir)

        if not idea_card_ids:
            return ToolResult(
                success=False,
                error=f"No Play YAML files found in {idea_cards_dir}",
            )

        results = []
        passed_count = 0
        failed_count = 0

        logger.info(f"Batch normalizing {len(idea_card_ids)} Plays in {idea_cards_dir}")

        # Process each Play
        for idea_card_id in idea_card_ids:
            try:
                # Use the existing single-card normalize function
                single_result = backtest_play_normalize_tool(
                    idea_card_id=idea_card_id,
                    idea_cards_dir=idea_cards_dir,
                    write_in_place=write_in_place,
                )

                card_result = {
                    "idea_card_id": idea_card_id,
                    "success": single_result.success,
                    "message": single_result.message if single_result.success else single_result.error,
                    "data": single_result.data,
                }

                if single_result.success:
                    passed_count += 1
                else:
                    failed_count += 1

                results.append(card_result)

            except Exception as e:
                logger.error(f"Failed to process {idea_card_id}: {e}")
                card_result = {
                    "idea_card_id": idea_card_id,
                    "success": False,
                    "message": str(e),
                    "data": None,
                }
                failed_count += 1
                results.append(card_result)

        # Determine overall success (all cards must pass)
        overall_success = failed_count == 0

        summary = {
            "total_cards": len(idea_card_ids),
            "passed": passed_count,
            "failed": failed_count,
            "directory": str(idea_cards_dir),
            "write_in_place": write_in_place,
        }

        if overall_success:
            return ToolResult(
                success=True,
                message=f"Batch normalization successful: {passed_count}/{len(idea_card_ids)} cards passed",
                data={
                    "summary": summary,
                    "results": results,
                },
            )
        else:
            return ToolResult(
                success=False,
                error=f"Batch normalization failed: {failed_count}/{len(idea_card_ids)} cards failed",
                data={
                    "summary": summary,
                    "results": results,
                },
            )

    except Exception as e:
        logger.error(f"Batch normalization failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Batch normalization error: {e}",
        )
