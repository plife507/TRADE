"""
CLI Wrapper for IdeaCard-based backtests.

This is the GOLDEN PATH for backtest execution:
CLI (trade_cli.py subcommands) → this wrapper → domain (engine/data)

All backtest validation, including smoke tests, should call this wrapper.
No ad-hoc test harnesses that re-implement pipeline logic.

Responsibilities:
- env validation (live|demo) + resolved DuckDB path + table name
- symbol normalization (uppercase + USDT-pair validation)
- timeframe validation (canonical: 1m/5m/15m/1h/4h/1d)
- tz normalization (strip tzinfo for DuckDB UTC-naive storage)
- window correctness (requested vs effective with warmup)
- coverage check against DuckDB
- indicator key printing (exec/htf/mtf)
- strict error messages (missing key vs NaN cause)
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List, Set
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
from ..backtest.idea_card import load_idea_card, list_idea_cards, IdeaCard
from ..backtest.execution_validation import (
    validate_idea_card_full,
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

def backtest_preflight_idea_card_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    idea_cards_dir: Optional[Path] = None,
    symbol_override: Optional[str] = None,
    fix_gaps: bool = False,
) -> ToolResult:
    """
    Run preflight check for an IdeaCard backtest using production preflight gate.
    
    Phase 6: Calls run_preflight_gate() and returns PreflightReport.to_dict() unchanged.
    
    Args:
        idea_card_id: IdeaCard identifier
        env: Data environment ("live" or "demo")
        symbol: Override symbol (default: first in IdeaCard.symbol_universe)
        start: Window start (required)
        end: Window end (default: now)
        idea_cards_dir: Override IdeaCard directory
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
        
        # Load IdeaCard
        try:
            idea_card = load_idea_card(idea_card_id, base_dir=idea_cards_dir)
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=str(e),
                data={
                    "env": env,
                    "db_path": str(db_path),
                    "available_idea_cards": list_idea_cards(idea_cards_dir),
                },
            )
        
        # Validate IdeaCard
        validation = validate_idea_card_full(idea_card)
        if not validation.is_valid:
            return ToolResult(
                success=False,
                error=f"IdeaCard validation failed: {[i.message for i in validation.errors]}",
                data={"validation_errors": [i.message for i in validation.errors]},
            )
        
        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return ToolResult(
                    success=False,
                    error="IdeaCard has no symbols in symbol_universe and none provided",
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

def backtest_run_idea_card_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    smoke: bool = False,
    strict: bool = True,
    write_artifacts: bool = True,
    artifacts_dir: Optional[Path] = None,
    idea_cards_dir: Optional[Path] = None,
    initial_equity_override: Optional[float] = None,
    max_leverage_override: Optional[float] = None,
    emit_snapshots: bool = False,
    symbol_override: Optional[str] = None,
    fix_gaps: bool = True,
    validate_artifacts_after: bool = True,
) -> ToolResult:
    """
    Run a backtest for an IdeaCard.
    
    This is the GOLDEN PATH for backtest execution.
    All validation, data loading, and execution flows through here.
    
    Capital/account config comes from IdeaCard.account section (required).
    CLI can override specific values using the override parameters.
    
    Args:
        idea_card_id: IdeaCard identifier
        env: Data environment ("live" or "demo")
        symbol: Override symbol
        start: Window start
        end: Window end
        smoke: If True, run fast smoke check (small window if not provided)
        strict: If True, use strict indicator access (default: True)
        write_artifacts: If True, write result artifacts
        artifacts_dir: Override artifacts directory
        idea_cards_dir: Override IdeaCard directory
        initial_equity_override: Override starting equity (defaults to IdeaCard.account.starting_equity_usdt)
        max_leverage_override: Override max leverage (defaults to IdeaCard.account.max_leverage)
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
        preflight_result = backtest_preflight_idea_card_tool(
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
        
        # Load IdeaCard
        idea_card = load_idea_card(idea_card_id, base_dir=idea_cards_dir)
        
        # Validate account config is present (required - no defaults)
        if idea_card.account is None:
            return ToolResult(
                success=False,
                error=(
                    f"IdeaCard '{idea_card_id}' is missing account section. "
                    "account.starting_equity_usdt and account.max_leverage are required."
                ),
            )
        
        # Resolve config values (IdeaCard is source of truth, CLI can override)
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
        
        # Resolve symbol from preflight data or IdeaCard
        resolved_symbol = preflight_data.get("symbol") or idea_card.symbol_universe[0]
        exec_tf = validate_canonical_tf(idea_card.exec_tf)
        
        # Print Resolved Config Summary (Phase 5.3 requirement)
        logger.info("=" * 60)
        logger.info("RESOLVED CONFIG SUMMARY")
        logger.info("=" * 60)
        logger.info(f"  symbol: {resolved_symbol}")
        logger.info(f"  tf_exec: {exec_tf}")
        if idea_card.htf:
            logger.info(f"  tf_htf: {idea_card.htf}")
        if idea_card.mtf:
            logger.info(f"  tf_mtf: {idea_card.mtf}")
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
        # Warmup spans
        for role in ["exec", "htf", "mtf"]:
            if role in idea_card.tf_configs:
                warmup = idea_card.get_required_warmup_bars(role)
                tf = idea_card.tf_configs[role].tf
                logger.info(f"  warmup_{role}: {warmup} bars ({tf})")
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
        
        # Compute expanded keys from IdeaCard FeatureSpecs
        available_keys_by_role = {}
        declared_keys_by_role = {}
        for role, tf_config in idea_card.tf_configs.items():
            specs = list(tf_config.feature_specs)
            expanded = get_required_indicator_columns_from_specs(specs)
            available_keys_by_role[role] = set(expanded)
            declared_keys_by_role[role] = sorted(expanded)
        
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
        logger.info(f"Declared indicator keys (exec): {declared_keys_by_role.get('exec', [])}")
        if declared_keys_by_role.get("htf"):
            logger.info(f"Declared indicator keys (htf): {declared_keys_by_role['htf']}")
        if declared_keys_by_role.get("mtf"):
            logger.info(f"Declared indicator keys (mtf): {declared_keys_by_role['mtf']}")
        
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
        # P1.2 Refactor: engine_factory is now handled internally via create_engine_from_idea_card()
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
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    idea_cards_dir: Optional[Path] = None,
    compute_values: bool = False,
) -> ToolResult:
    """
    Discover and print indicator keys for an IdeaCard.
    
    This command replaces pytest-based indicator key validation.
    Run this to see exactly what indicator keys will be computed
    so you can fix FeatureSpec/IdeaCard declarations.
    
    Args:
        idea_card_id: IdeaCard identifier
        data_env: Data environment ("live" or "demo")
        symbol: Override symbol
        start: Window start (for computing actual values)
        end: Window end
        idea_cards_dir: Override IdeaCard directory
        compute_values: If True, actually compute indicators and show first non-NaN index
        
    Returns:
        ToolResult with indicator key discovery results
    """
    try:
        # Validate env
        data_env = validate_data_env(data_env)
        db_path = resolve_db_path(data_env)
        ohlcv_table = resolve_table_name("ohlcv", data_env)
        
        # Load IdeaCard
        try:
            idea_card = load_idea_card(idea_card_id, base_dir=idea_cards_dir)
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=str(e),
                data={"available_idea_cards": list_idea_cards(idea_cards_dir)},
            )
        
        # Validate IdeaCard
        validation = validate_idea_card_full(idea_card)
        if not validation.is_valid:
            return ToolResult(
                success=False,
                error=f"IdeaCard validation failed: {[i.message for i in validation.errors]}",
            )
        
        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return ToolResult(
                    success=False,
                    error="IdeaCard has no symbols and none provided",
                )
            symbol = idea_card.symbol_universe[0]
        
        symbol = validate_symbol(symbol)
        
        # Get all feature specs by role
        feature_specs_by_role = {}
        declared_keys_by_role = {}
        expanded_keys_by_role = {}
        
        for role, tf_config in idea_card.tf_configs.items():
            specs = list(tf_config.feature_specs)
            feature_specs_by_role[role] = specs
            
            # Get declared keys (output_key from each spec)
            declared_keys_by_role[role] = sorted([s.output_key for s in specs])
            
            # Get expanded keys (including multi-output suffixes)
            expanded_keys_by_role[role] = sorted(get_required_indicator_columns_from_specs(specs))
        
        # Build result
        result_data = {
            "idea_card_id": idea_card_id,
            "data_env": data_env,
            "db_path": str(db_path),
            "symbol": symbol,
            "exec_tf": idea_card.exec_tf,
            "htf": idea_card.htf,
            "mtf": idea_card.mtf,
            "declared_keys_by_role": declared_keys_by_role,
            "expanded_keys_by_role": expanded_keys_by_role,
            "total_declared_keys": sum(len(v) for v in declared_keys_by_role.values()),
            "total_expanded_keys": sum(len(v) for v in expanded_keys_by_role.values()),
        }
        
        # If compute_values, actually load data and compute indicators
        if compute_values and start and end:
            from ..backtest.indicators import apply_feature_spec_indicators, find_first_valid_bar
            
            store = get_historical_store(env=data_env)
            
            computed_info = {}
            for role, specs in feature_specs_by_role.items():
                if not specs:
                    continue
                    
                tf = idea_card.tf_configs[role].tf
                
                # Normalize timestamps
                start_norm = normalize_timestamp(start)
                end_norm = normalize_timestamp(end) if end else datetime.now().replace(tzinfo=None)
                
                # Load data
                df = store.get_ohlcv(symbol, tf, start_norm, end_norm)
                
                if df is None or df.empty:
                    computed_info[role] = {"error": f"No data for {symbol} {tf}"}
                    continue
                
                # Apply indicators
                df = apply_feature_spec_indicators(df, specs)
                
                # Find first valid bar
                expanded_cols = get_required_indicator_columns_from_specs(specs)
                first_valid = find_first_valid_bar(df, expanded_cols)
                
                # Get actual computed columns
                actual_cols = [c for c in df.columns if c not in ['timestamp', 'open', 'high', 'low', 'close', 'volume']]
                
                computed_info[role] = {
                    "tf": tf,
                    "data_rows": len(df),
                    "first_valid_bar": first_valid,
                    "computed_columns": sorted(actual_cols),
                    "all_indicators_valid": first_valid >= 0,
                }
            
            result_data["computed_info"] = computed_info
        
        # Log output
        logger.info(f"Indicator key discovery for {idea_card_id}:")
        for role in ["exec", "htf", "mtf"]:
            if role in declared_keys_by_role:
                declared = declared_keys_by_role[role]
                expanded = expanded_keys_by_role[role]
                logger.info(f"  {role} ({idea_card.tf_configs.get(role, {}).tf if role in idea_card.tf_configs else 'N/A'}):")
                logger.info(f"    declared: {declared}")
                logger.info(f"    expanded: {expanded}")
        
        return ToolResult(
            success=True,
            message=f"Found {result_data['total_expanded_keys']} indicator keys across {len(feature_specs_by_role)} TF roles",
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

def _datetime_to_epoch_ms(dt: Optional[datetime]) -> Optional[int]:
    """Convert datetime to epoch milliseconds."""
    if dt is None:
        return None
    return int(dt.timestamp() * 1000)


def backtest_data_fix_tool(
    idea_card_id: str,
    env: DataEnv = DEFAULT_DATA_ENV,
    symbol: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    max_lookback_days: int = 7,
    sync_to_now: bool = False,
    fill_gaps: bool = True,
    heal: bool = False,
    idea_cards_dir: Optional[Path] = None,
) -> ToolResult:
    """
    Fix data for an IdeaCard backtest by calling existing data tools.
    
    Phase 6: Bounded enforcement + progress tracking + structured result.
    
    Args:
        idea_card_id: IdeaCard identifier
        env: Data environment
        symbol: Override symbol
        start: Sync from this date (default: IdeaCard warmup requirements)
        end: Sync to this date (required for bounded mode)
        max_lookback_days: Max lookback days (default 7). If (end - start) > this, clamp start.
        sync_to_now: If True, sync data to current time
        fill_gaps: If True, fill gaps after sync
        heal: If True, run full heal after sync
        idea_cards_dir: Override IdeaCard directory
        
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
        
        # Load IdeaCard to get TFs
        idea_card = load_idea_card(idea_card_id, base_dir=idea_cards_dir)
        
        # Resolve symbol
        if symbol is None:
            if not idea_card.symbol_universe:
                return ToolResult(
                    success=False,
                    error="IdeaCard has no symbols and none provided",
                )
            symbol = idea_card.symbol_universe[0]
        
        symbol = validate_symbol(symbol)
        
        # Get all TFs from IdeaCard + mandatory 1m for price feed
        tfs = set()
        for role, tf_config in idea_card.tf_configs.items():
            tfs.add(tf_config.tf)
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
# List IdeaCards (tools-layer)
# =============================================================================

def backtest_list_idea_cards_tool(
    idea_cards_dir: Optional[Path] = None,
) -> ToolResult:
    """
    List available IdeaCards.
    
    Args:
        idea_cards_dir: Override IdeaCard directory
        
    Returns:
        ToolResult with list of IdeaCard IDs
    """
    try:
        cards = list_idea_cards(base_dir=idea_cards_dir)
        
        return ToolResult(
            success=True,
            message=f"Found {len(cards)} IdeaCards",
            data={
                "idea_cards": cards,
                "directory": str(idea_cards_dir) if idea_cards_dir else "configs/idea_cards/",
            },
        )
        
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to list IdeaCards: {e}",
        )


# =============================================================================
# IdeaCard Normalization (build-time validation)
# =============================================================================

def backtest_idea_card_normalize_tool(
    idea_card_id: str,
    idea_cards_dir: Optional[Path] = None,
    write_in_place: bool = False,
) -> ToolResult:
    """
    Normalize and validate an IdeaCard YAML at build time.
    
    This command validates:
    - All indicator_types are supported
    - All params are accepted by each indicator
    - All signal_rules/risk_model references use expanded keys (not base keys)
    
    If validation passes and write_in_place=True, writes the normalized YAML
    with auto-generated required_indicators.
    
    Agent Rule:
        Agents may only generate IdeaCards through this command and must
        refuse to write YAML if normalization fails.
    
    Args:
        idea_card_id: IdeaCard identifier
        idea_cards_dir: Override IdeaCard directory
        write_in_place: If True, write normalized YAML back to file
        
    Returns:
        ToolResult with validation results
    """
    import yaml
    from ..backtest.idea_card import IDEA_CARDS_DIR
    from ..backtest.idea_card_yaml_builder import (
        normalize_idea_card_yaml,
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
            cards = list_idea_cards(base_dir=idea_cards_dir)
            return ToolResult(
                success=False,
                error=f"IdeaCard '{idea_card_id}' not found in {search_dir}",
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
        normalized, result = normalize_idea_card_yaml(raw, auto_generate_required=True)
        
        if not result.is_valid:
            error_details = format_validation_errors(result.errors)
            return ToolResult(
                success=False,
                error=f"IdeaCard validation failed with {len(result.errors)} error(s)",
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
                message=f"IdeaCard '{idea_card_id}' normalized and written to {yaml_path}",
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
            message=f"IdeaCard '{idea_card_id}' passed validation (dry-run, not written)",
            data={
                "idea_card_id": idea_card_id,
                "yaml_path": str(yaml_path),
                "normalized": True,
                "written": False,
                "warnings": result.warnings,
            },
        )
        
    except Exception as e:
        logger.error(f"IdeaCard normalization failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Normalization error: {e}",
        )


# =============================================================================
# Audit Toolkit (indicator registry consistency check)
# =============================================================================

def backtest_idea_card_normalize_batch_tool(
    idea_cards_dir: Path,
    write_in_place: bool = False,
) -> ToolResult:
    """
    Batch normalize all IdeaCards in a directory.

    Args:
        idea_cards_dir: Directory containing IdeaCard YAML files
        write_in_place: If True, write normalized YAML back to files

    Returns:
        ToolResult with batch normalization results
    """
    try:
        from ..backtest.idea_card import list_idea_cards

        # Get all IdeaCard IDs in the directory
        idea_card_ids = list_idea_cards(base_dir=idea_cards_dir)

        if not idea_card_ids:
            return ToolResult(
                success=False,
                error=f"No IdeaCard YAML files found in {idea_cards_dir}",
            )

        results = []
        passed_count = 0
        failed_count = 0

        logger.info(f"Batch normalizing {len(idea_card_ids)} IdeaCards in {idea_cards_dir}")

        # Process each IdeaCard
        for idea_card_id in idea_card_ids:
            try:
                # Use the existing single-card normalize function
                single_result = backtest_idea_card_normalize_tool(
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


def backtest_audit_math_from_snapshots_tool(run_dir: Path) -> ToolResult:
    """
    Audit math parity by comparing snapshot artifacts against fresh pandas_ta computation.

    Args:
        run_dir: Directory containing snapshots/ subdirectory with artifacts

    Returns:
        ToolResult with audit results including per-column diff statistics
    """
    try:
        from ..backtest.audits.audit_math_parity import audit_math_parity_from_snapshots

        result = audit_math_parity_from_snapshots(run_dir)

        if result.success:
            return ToolResult(
                success=True,
                message="Math parity audit completed successfully",
                data=result.data,
            )
        else:
            return ToolResult(
                success=False,
                error=result.error_message or "Math parity audit failed",
                data=result.data,
            )

    except Exception as e:
        logger.error(f"Math parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Math parity audit error: {e}",
        )


def backtest_audit_toolkit_tool(
    sample_bars: int = 2000,
    seed: int = 1337,
    fail_on_extras: bool = False,
    strict: bool = True,
) -> ToolResult:
    """
    Run the toolkit contract audit over all registry indicators.
    
    Gate 1 of the verification suite - ensures the registry is the contract:
    - Every indicator produces exactly registry-declared canonical outputs
    - No canonical collisions
    - No missing declared outputs
    - Extras are dropped + recorded
    
    Uses deterministic synthetic OHLCV data for reproducibility.

    Args:
        sample_bars: Number of bars in synthetic OHLCV (default: 2000)
        seed: Random seed for reproducibility (default: 1337)
        fail_on_extras: If True, treat extras as failures (default: False)
        strict: If True, fail on any contract breach (default: True)

    Returns:
        ToolResult with complete audit results
    """
    try:
        from ..backtest.audits.toolkit_contract_audit import run_toolkit_contract_audit

        result = run_toolkit_contract_audit(
            sample_bars=sample_bars,
            seed=seed,
            fail_on_extras=fail_on_extras,
            strict=strict,
        )

        if result.success:
            return ToolResult(
                success=True,
                message=(
                    f"Toolkit contract audit PASSED: {result.passed_indicators}/{result.total_indicators} "
                    f"indicators OK ({result.indicators_with_extras} have extras dropped)"
                ),
                data=result.to_dict(),
            )
        else:
            # Collect failure details
            failed = [r for r in result.indicator_results if not r.passed]
            failure_summary = [
                {
                    "indicator": r.indicator_type,
                    "missing": r.missing_outputs,
                    "collisions": r.collisions,
                    "error": r.error_message,
                }
                for r in failed
            ]
            return ToolResult(
                success=False,
                error=(
                    f"Toolkit contract audit FAILED: {result.failed_indicators} indicator(s) "
                    f"with contract breaches"
                ),
                data=result.to_dict(),
            )

    except Exception as e:
        logger.error(f"Toolkit contract audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Toolkit contract audit error: {e}",
        )

    except Exception as e:
        logger.error(f"Toolkit audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Audit error: {e}",
        )


def backtest_audit_in_memory_parity_tool(
    idea_card: str,
    start_date: str,
    end_date: str,
    output_dir: Optional[str] = None,
) -> ToolResult:
    """
    Run in-memory math parity audit for an IdeaCard.
    
    Compares FeatureFrameBuilder output against fresh pandas_ta computation.
    Does NOT emit snapshot artifacts or Parquet — purely in-memory comparison.
    
    Args:
        idea_card: Path to IdeaCard YAML
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        output_dir: Optional output directory for diff CSV (written only on failure)
        
    Returns:
        ToolResult with parity audit results
    """
    try:
        from ..backtest.audits.audit_in_memory_parity import run_in_memory_parity_for_idea_card
        
        output_path = Path(output_dir) if output_dir else None
        
        result = run_in_memory_parity_for_idea_card(
            idea_card_path=idea_card,
            start_date=start_date,
            end_date=end_date,
            output_dir=output_path,
        )
        
        if result.success:
            return ToolResult(
                success=True,
                message=(
                    f"In-memory parity audit PASSED: {result.summary['passed_columns']}/{result.summary['total_columns']} "
                    f"columns OK (max_diff={result.summary['max_abs_diff']:.2e})"
                ),
                data=result.to_dict(),
            )
        else:
            return ToolResult(
                success=False,
                error=(
                    f"In-memory parity audit FAILED: {result.summary['failed_columns']} column(s) "
                    f"exceeded tolerance (max_diff={result.summary['max_abs_diff']:.2e})"
                    if result.summary else result.error_message
                ),
                data=result.to_dict(),
            )
    
    except Exception as e:
        logger.error(f"In-memory parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"In-memory parity audit error: {e}",
        )


def backtest_math_parity_tool(
    idea_card: str,
    start_date: str,
    end_date: str,
    output_dir: Optional[str] = None,
    contract_sample_bars: int = 2000,
    contract_seed: int = 1337,
) -> ToolResult:
    """
    Run math parity audit: contract audit + in-memory parity.
    
    Validates indicator math correctness by running:
    1. Toolkit contract audit (registry validation)
    2. In-memory math parity audit (indicator computation validation)
    
    Args:
        idea_card: Path to IdeaCard YAML for parity audit
        start_date: Start date for parity audit (YYYY-MM-DD)
        end_date: End date for parity audit (YYYY-MM-DD)
        output_dir: Optional output directory for diff reports
        contract_sample_bars: Synthetic bars for contract audit
        contract_seed: Random seed for contract audit
        
    Returns:
        ToolResult with combined audit results
    """
    from ..backtest.audits.toolkit_contract_audit import run_toolkit_contract_audit
    from ..backtest.audits.audit_in_memory_parity import run_in_memory_parity_for_idea_card
    
    results = {
        "contract_audit": None,
        "parity_audit": None,
    }
    
    try:
        # Step 1: Toolkit contract audit
        contract_result = run_toolkit_contract_audit(
            sample_bars=contract_sample_bars,
            seed=contract_seed,
            fail_on_extras=False,
            strict=True,
        )
        results["contract_audit"] = {
            "success": contract_result.success,
            "passed": contract_result.passed_indicators,
            "failed": contract_result.failed_indicators,
            "total": contract_result.total_indicators,
        }
        
        if not contract_result.success:
            return ToolResult(
                success=False,
                error=f"Math parity FAILED at contract audit: {contract_result.failed_indicators} indicator(s) with breaches",
                data=results,
            )
        
        # Step 2: In-memory parity audit
        output_path = Path(output_dir) if output_dir else None
        parity_result = run_in_memory_parity_for_idea_card(
            idea_card_path=idea_card,
            start_date=start_date,
            end_date=end_date,
            output_dir=output_path,
        )
        results["parity_audit"] = {
            "success": parity_result.success,
            "summary": parity_result.summary,
        }
        
        if not parity_result.success:
            return ToolResult(
                success=False,
                error=f"Math parity FAILED: {parity_result.summary.get('failed_columns', 0)} column(s) mismatched",
                data=results,
            )
        
        # Both passed
        return ToolResult(
            success=True,
            message=(
                f"Math parity PASSED: "
                f"contract={contract_result.passed_indicators}/{contract_result.total_indicators}, "
                f"parity={parity_result.summary['passed_columns']}/{parity_result.summary['total_columns']}"
            ),
            data=results,
        )
    
    except Exception as e:
        logger.error(f"Math parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Math parity audit error: {e}",
            data=results,
        )


# =============================================================================
# Phase 3: Artifact Parity Verification (CSV ↔ Parquet)
# =============================================================================

def verify_artifact_parity_tool(
    idea_card_id: str,
    symbol: str,
    run_id: Optional[str] = None,
    base_dir: Optional[str] = None,
) -> ToolResult:
    """
    Verify CSV ↔ Parquet parity for backtest artifacts.
    
    Phase 3.1 tool: Validates that dual-written CSV and Parquet files
    contain identical data. Used during migration validation.
    
    Args:
        idea_card_id: IdeaCard ID
        symbol: Trading symbol
        run_id: Specific run ID (e.g., "run-001") or None for latest
        base_dir: Base backtests directory (default: "backtests")
        
    Returns:
        ToolResult with parity verification results
    """
    from ..backtest.artifact_parity_verifier import (
        verify_idea_card_parity,
        RunParityResult,
    )
    
    try:
        # Default base dir
        backtests_dir = Path(base_dir) if base_dir else Path("backtests")
        
        # Run parity verification
        result = verify_idea_card_parity(
            base_dir=backtests_dir,
            idea_card_id=idea_card_id,
            symbol=symbol,
            run_id=run_id,
        )
        
        if result.passed:
            return ToolResult(
                success=True,
                message=f"CSV ↔ Parquet parity PASSED: {result.artifacts_passed}/{result.artifacts_checked} artifacts",
                data=result.to_dict(),
            )
        else:
            return ToolResult(
                success=False,
                error=f"CSV ↔ Parquet parity FAILED: {result.artifacts_passed}/{result.artifacts_checked} artifacts passed",
                data=result.to_dict(),
            )
    
    except Exception as e:
        logger.error(f"Artifact parity verification failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Parity verification error: {e}",
        )


# =============================================================================
# Phase 4: Snapshot Plumbing Parity Audit
# =============================================================================

def backtest_audit_snapshot_plumbing_tool(
    idea_card_id: str,
    start_date: str,
    end_date: str,
    symbol: Optional[str] = None,
    max_samples: int = 2000,
    tolerance: float = 1e-12,
    strict: bool = True,
) -> ToolResult:
    """
    Run Phase 4 snapshot plumbing parity audit.
    
    Validates RuntimeSnapshotView.get_feature() against direct FeedStore reads.
    This audit proves the plumbing is correct without testing indicator math.
    
    Args:
        idea_card_id: IdeaCard identifier or path
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        symbol: Override symbol (optional, inferred from IdeaCard)
        max_samples: Max exec bar samples (default: 2000)
        tolerance: Tolerance for float comparison (default: 1e-12)
        strict: Stop at first mismatch (default: True)
        
    Returns:
        ToolResult with plumbing parity audit results
    """
    from ..backtest.audits.audit_snapshot_plumbing_parity import audit_snapshot_plumbing_parity
    
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
        
        result = audit_snapshot_plumbing_parity(
            idea_card_id=idea_card_id,
            symbol=symbol,
            start_date=start,
            end_date=end,
            max_samples=max_samples,
            tolerance=tolerance,
            strict=strict,
        )
        
        if result.success:
            return ToolResult(
                success=True,
                message=(
                    f"Snapshot plumbing parity PASSED: "
                    f"{result.total_samples} samples, {result.total_comparisons} comparisons "
                    f"(runtime: {result.runtime_seconds:.1f}s)"
                ),
                data=result.to_dict(),
            )
        else:
            return ToolResult(
                success=False,
                error=result.error_message or "Plumbing parity audit failed",
                data=result.to_dict(),
            )
    
    except Exception as e:
        logger.error(f"Snapshot plumbing parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Plumbing audit error: {e}",
        )


# =============================================================================
# Rollup Parity Audit (1m Price Feed Validation)
# =============================================================================

def backtest_audit_rollup_parity_tool(
    n_intervals: int = 10,
    quotes_per_interval: int = 15,
    seed: int = 1337,
    tolerance: float = 1e-10,
) -> ToolResult:
    """
    Run rollup parity audit for ExecRollupBucket and RuntimeSnapshotView accessors.

    Validates the 1m rollup system that aggregates price data between exec closes:
    - ExecRollupBucket.accumulate() correctly tracks min/max/sum/count
    - ExecRollupBucket.freeze() produces correct px.rollup.* values
    - RuntimeSnapshotView accessors return correct rollup values
    - Rollup values match manual recomputation from 1m quote data

    This is a critical audit for the simulator - rollups are used for:
    - Zone touch detection (Market Structure)
    - Intrabar price movement analysis
    - Stop/limit fill simulation accuracy

    Args:
        n_intervals: Number of exec intervals to test (default: 10)
        quotes_per_interval: Approximate quotes per interval (default: 15)
        seed: Random seed for reproducibility (default: 1337)
        tolerance: Float comparison tolerance (default: 1e-10)

    Returns:
        ToolResult with rollup parity audit results
    """
    try:
        from ..backtest.audits.audit_rollup_parity import run_rollup_parity_audit

        result = run_rollup_parity_audit(
            n_intervals=n_intervals,
            quotes_per_interval=quotes_per_interval,
            seed=seed,
            tolerance=tolerance,
        )

        if result.success:
            return ToolResult(
                success=True,
                message=(
                    f"Rollup parity audit PASSED: "
                    f"{result.passed_intervals}/{result.total_intervals} intervals, "
                    f"{result.total_comparisons} comparisons "
                    f"(bucket={result.bucket_tests_passed}, accessors={result.accessor_tests_passed})"
                ),
                data=result.to_dict(),
            )
        else:
            return ToolResult(
                success=False,
                error=(
                    f"Rollup parity audit FAILED: "
                    f"{result.failed_intervals} interval(s) failed, "
                    f"{result.failed_comparisons} comparison(s) failed"
                    + (f" - {result.error_message}" if result.error_message else "")
                ),
                data=result.to_dict(),
            )

    except Exception as e:
        logger.error(f"Rollup parity audit failed: {e}\n{traceback.format_exc()}")
        return ToolResult(
            success=False,
            error=f"Rollup audit error: {e}",
        )