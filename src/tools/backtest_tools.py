"""
Backtest tools for TRADE trading bot.

Provides tool-layer access to backtesting functionality:
- Run backtests via system configs
- List available systems
- Prepare data for backtesting
- Preflight data health checks (Phase -1 gate)

All tools return ToolResult for consistency with other tools.
"""

from datetime import datetime
from typing import Any
from pathlib import Path
import os

from .shared import ToolResult, _get_historical_store
from .data_tools import (
    fill_gaps_tool,
    sync_range_tool, 
    sync_funding_tool,
    sync_full_from_launch_tool,
    get_data_extremes_tool,
)
from ..backtest.artifacts import ManifestWriter, EventLogWriter, ARTIFACT_VERSION
from ..backtest.system_config import (
    SystemConfig,
    RiskProfileConfig,
    load_system_config,
    list_systems,
    resolve_risk_profile,
    CONFIGS_DIR,
)
from ..backtest.engine import BacktestEngine
from ..backtest.types import BacktestMetrics
from ..backtest.runtime.windowing import (
    compute_load_window,
    compute_simple_load_window,
    WarmupConfig,
)
from ..backtest.runtime.data_health import DataHealthCheck, DataHealthReport
from ..backtest.indicators import get_max_warmup_from_specs_by_role
from ..strategies.registry import get_strategy, list_strategies, list_strategies_with_metadata, strategy_exists
from ..utils.epoch_tracking import StrategyEpochTracker, StrategyEpoch, get_artifact_writer
from ..utils.logger import get_logger
from ..config.constants import DataEnv


logger = get_logger()

# Phase -1: Maximum heal attempts before hard-fail
MAX_HEAL_ATTEMPTS = 3


# =============================================================================
# System Config Tools
# =============================================================================

def backtest_list_systems_tool() -> ToolResult:
    """
    List all available backtest system configurations.
    
    Returns:
        ToolResult with list of system_ids and their key attributes
    """
    try:
        system_ids = list_systems()
        
        if not system_ids:
            return ToolResult(
                success=True,
                message="No system configurations found",
                data={
                    "systems": [],
                    "configs_dir": str(CONFIGS_DIR),
                },
            )
        
        # Load basic info for each system
        systems = []
        for sys_id in system_ids:
            try:
                config = load_system_config(sys_id)
                systems.append({
                    "system_id": sys_id,
                    "system_uid": config.system_uid,
                    "symbol": config.symbol,
                    "tf": config.tf,
                    "strategy_id": config.strategy_id,
                    "strategy_version": config.strategy_version,
                    "risk_mode": config.risk_mode,
                    "windows": list(config.windows.keys()),
                })
            except Exception as e:
                systems.append({
                    "system_id": sys_id,
                    "error": str(e),
                })
        
        return ToolResult(
            success=True,
            message=f"Found {len(systems)} system configurations",
            data={
                "systems": systems,
                "configs_dir": str(CONFIGS_DIR),
            },
        )
        
    except Exception as e:
        logger.error(f"Error listing systems: {e}")
        return ToolResult(
            success=False,
            error=f"Failed to list systems: {e}",
        )


def backtest_get_system_tool(system_id: str) -> ToolResult:
    """
    Get detailed information about a system configuration.
    
    Args:
        system_id: System identifier
        
    Returns:
        ToolResult with full system config details
    """
    try:
        config = load_system_config(system_id)
        
        return ToolResult(
            success=True,
            message=f"Loaded system: {system_id}",
            data={
                "system_id": config.system_id,
                "system_uid": config.system_uid,
                "symbol": config.symbol,
                "tf": config.tf,
                "strategy_id": config.strategy_id,
                "strategy_version": config.strategy_version,
                "risk_mode": config.risk_mode,
                "windows": config.windows,
                "params": config.params,
                "risk_profile": config.risk_profile.to_dict(),
                "data_build": {
                    "env": config.data_build.env,
                    "period": config.data_build.period,
                    "tfs": config.data_build.tfs,
                },
            },
        )
        
    except FileNotFoundError as e:
        return ToolResult(
            success=False,
            error=str(e),
        )
    except Exception as e:
        logger.error(f"Error loading system {system_id}: {e}")
        return ToolResult(
            success=False,
            error=f"Failed to load system: {e}",
        )


# =============================================================================
# Phase -1: Preflight Data Health Gate
# =============================================================================

def backtest_preflight_check_tool(
    system_id: str,
    window_name: str = "hygiene",
    heal_if_needed: bool = True,
    max_heal_attempts: int = MAX_HEAL_ATTEMPTS,
    auto_bootstrap: bool = True,
) -> ToolResult:
    """
    Phase -1 preflight data health check and heal loop.

    This gate runs BEFORE any simulation starts. It:
    1. Computes the required load window (test window + warmup + buffers)
    2. Checks if symbol has any data coverage; if not and auto_bootstrap=True,
       runs sync_full_from_launch_tool to bootstrap from launchTime
    3. Runs DataHealthCheck on required TFs/series
    4. If gaps detected and heal_if_needed=True, calls fill_gaps_tool and sync_range_tool
    5. Rechecks after healing, loops up to max_heal_attempts
    6. Hard-fails if still failing after max attempts

    Pattern: Use data tools (not direct store calls) for healing to maintain
    the tools-as-API boundary.
    
    Args:
        system_id: System configuration ID
        window_name: Window to verify data for
        heal_if_needed: If True, attempt to heal gaps automatically
        max_heal_attempts: Maximum healing attempts before hard-fail
        auto_bootstrap: If True, bootstrap new symbols via full_from_launch
        
    Returns:
        ToolResult with preflight status:
        - success=True: Data is healthy, simulation can proceed
        - success=False: Data issues could not be resolved
    """
    try:
        # Load system config
        config = load_system_config(system_id, window_name)
        window = config.get_window(window_name)
        
        # Compute load window with warmup and buffers from FeatureSpecs
        specs_by_role = config.feature_specs_by_role if hasattr(config, 'feature_specs_by_role') else {}
        max_warmup = get_max_warmup_from_specs_by_role(specs_by_role)
        load_window = compute_simple_load_window(
            test_start=window.start,
            test_end=window.end,
            tf=config.tf,
            max_lookback=max_warmup,
        )
        
        logger.info(
            f"Preflight check: {config.symbol} {config.tf} | "
            f"test=[{window.start}, {window.end}] | "
            f"load=[{load_window.load_start}, {load_window.load_end}]"
        )
        
        store = _get_historical_store(env=config.data_build.env)
        
        # Phase -1 NEW: Check if symbol has ANY data coverage
        # If symbol is new (no data), auto-bootstrap from launchTime
        existing_status = store.status(config.symbol)
        symbol_has_data = bool(existing_status)
        
        if not symbol_has_data and auto_bootstrap and heal_if_needed:
            logger.info(
                f"Symbol {config.symbol} has no data coverage. "
                f"Auto-bootstrapping from launchTime via sync_full_from_launch_tool..."
            )
            
            # Bootstrap using all timeframes from data_build config
            bootstrap_result = sync_full_from_launch_tool(
                symbol=config.symbol,
                timeframes=config.data_build.tfs,
                sync_funding=True,
                sync_oi=True,
                fill_gaps_after=True,
                heal_after=True,
                env=config.data_build.env,
            )
            
            if bootstrap_result.success:
                logger.info(f"Bootstrap complete: {bootstrap_result.message}")
            else:
                logger.warning(f"Bootstrap failed: {bootstrap_result.error}")
                # Continue to normal flow - it may still work for partial data
        
        # Run preflight check with heal loop
        attempt = 0
        last_report = None
        
        while attempt < max_heal_attempts:
            attempt += 1
            
            # Get timestamps for health check
            df = store.get_ohlcv(
                symbol=config.symbol,
                tf=config.tf,
                start=load_window.load_start,
                end=load_window.load_end,
            )
            
            # Build timestamps dict for health check
            timestamps_by_tf = {config.tf: []}
            if not df.empty:
                timestamps_by_tf[config.tf] = df["timestamp"].tolist()
            
            # Check funding data if required
            funding_df = store.get_funding(
                symbol=config.symbol,
                start=load_window.load_start,
                end=load_window.load_end,
            )
            funding_ts = funding_df["timestamp"].tolist() if not funding_df.empty else []
            
            # Run DataHealthCheck
            health_check = DataHealthCheck(
                load_start=load_window.load_start,
                load_end=load_window.load_end,
                required_tfs=[config.tf],
                symbol=config.symbol,
                required_series=["ohlcv", "funding"],
            )
            
            report = health_check.run(
                timestamps_by_series_tf={
                    "ohlcv": timestamps_by_tf,
                    "funding": {config.tf: funding_ts},  # Funding has no TF but we key it for consistency
                },
                data_rows_by_tf={config.tf: df.to_dict(orient="records")} if not df.empty else None,
            )
            
            last_report = report
            
            logger.info(
                f"Preflight attempt {attempt}/{max_heal_attempts}: "
                f"passed={report.passed}, gaps={len(report.gaps)}, "
                f"coverage_issues={len(report.coverage_issues)}"
            )
            
            # If passed, we're done
            if report.passed:
                # Build extremes metadata for the response
                extremes_result = get_data_extremes_tool(symbol=config.symbol, env=config.data_build.env)
                extremes_data = extremes_result.data.get("extremes", {}) if extremes_result.success else {}
                
                return ToolResult(
                    success=True,
                    message=f"Preflight check passed (attempt {attempt})",
                    symbol=config.symbol,
                    data={
                        "system_id": system_id,
                        "window_name": window_name,
                        "load_window": load_window.to_dict(),
                        "health_report": report.to_dict(),
                        "attempts": attempt,
                        "extremes": extremes_data.get(config.symbol, {}),
                    },
                )
            
            # If healing not enabled, fail immediately
            if not heal_if_needed:
                return ToolResult(
                    success=False,
                    error="Preflight check failed (healing disabled)",
                    symbol=config.symbol,
                    data={
                        "system_id": system_id,
                        "window_name": window_name,
                        "load_window": load_window.to_dict(),
                        "health_report": report.to_dict(),
                        "attempts": attempt,
                    },
                )
            
            # Attempt to heal gaps via ToolRegistry (Phase -1 requirement)
            logger.info(f"Healing data gaps via data tools (attempt {attempt})...")
            
            # First try to fill gaps in existing data via fill_gaps_tool
            if report.gaps:
                for gap in report.gaps:
                    if gap.series == "ohlcv":
                        fill_result = fill_gaps_tool(
                            symbol=config.symbol,
                            timeframe=gap.tf,
                            env=config.data_build.env,
                        )
                        if fill_result.success:
                            logger.info(f"fill_gaps_tool: {fill_result.message}")
                        else:
                            logger.warning(f"fill_gaps_tool failed: {fill_result.error}")
            
            # If coverage issues, try to sync missing ranges via sync_range_tool
            if report.coverage_issues:
                # Sync the full load window via data tools
                sync_result = sync_range_tool(
                    symbols=[config.symbol],
                    start=load_window.load_start,
                    end=load_window.load_end,
                    timeframes=[config.tf],
                    env=config.data_build.env,
                )
                if sync_result.success:
                    logger.info(f"sync_range_tool: {sync_result.message}")
                else:
                    logger.warning(f"sync_range_tool failed: {sync_result.error}")
                
                # Also sync funding via sync_funding_tool
                funding_result = sync_funding_tool(
                    symbols=[config.symbol],
                    period="6M",  # Use a generous period for funding
                    env=config.data_build.env,
                )
                if funding_result.success:
                    logger.info(f"sync_funding_tool: {funding_result.message}")
                else:
                    logger.warning(f"sync_funding_tool failed: {funding_result.error}")
        
        # Exhausted all attempts - hard fail
        return ToolResult(
            success=False,
            error=f"Preflight check failed after {max_heal_attempts} heal attempts",
            symbol=config.symbol,
            data={
                "system_id": system_id,
                "window_name": window_name,
                "load_window": load_window.to_dict(),
                "health_report": last_report.to_dict() if last_report else None,
                "attempts": attempt,
                "max_attempts": max_heal_attempts,
            },
        )
        
    except Exception as e:
        logger.error(f"Preflight check failed: {e}")
        return ToolResult(
            success=False,
            error=f"Preflight check error: {e}",
        )


# =============================================================================
# Backtest Run Tool
# =============================================================================

def backtest_run_tool(
    system_id: str,
    window_name: str = "hygiene",
    write_artifacts: bool = True,
    risk_overrides: dict[str, Any] | None = None,
    run_preflight: bool = True,
    heal_if_needed: bool = True,
) -> ToolResult:
    """
    Run a backtest for a system configuration.
    
    Loads the system config, optionally applies risk overrides, gets the strategy,
    and runs the backtest engine. Optionally writes artifacts.
    
    Phase -1 preflight gate is run first (unless disabled) to ensure data health.
    
    Args:
        system_id: System configuration ID
        window_name: Window to run ("hygiene" or "test")
        write_artifacts: Whether to write run artifacts
        risk_overrides: Optional dict with overrides for risk profile:
            - initial_equity: Starting equity
            - risk_per_trade_pct: Risk per trade percentage
            - max_leverage: Maximum leverage
        run_preflight: If True (default), run Phase -1 preflight data health check
        heal_if_needed: If True (default), attempt to heal data gaps during preflight
        
    Returns:
        ToolResult with backtest results including metrics, trades summary, and artifact path
    """
    try:
        # Phase -1: Preflight data health gate
        if run_preflight:
            preflight_result = backtest_preflight_check_tool(
                system_id=system_id,
                window_name=window_name,
                heal_if_needed=heal_if_needed,
            )
            
            if not preflight_result.success:
                return ToolResult(
                    success=False,
                    error=f"Preflight check failed: {preflight_result.error}",
                    data={
                        "system_id": system_id,
                        "window_name": window_name,
                        "preflight": preflight_result.data,
                        "suggestion": "Run data sync or check data coverage for required window",
                    },
                )
            
            logger.info(f"Preflight check passed for {system_id}/{window_name}")
        
        # Load system config
        config = load_system_config(system_id, window_name)
        
        # Apply risk overrides if provided
        if risk_overrides:
            resolved_risk = resolve_risk_profile(config.risk_profile, risk_overrides)
            # Create a new config with the resolved risk profile
            # We need to rebuild the config to update system_uid
            config = SystemConfig(
                system_id=config.system_id,
                symbol=config.symbol,
                tf=config.tf,
                strategies=config.strategies,
                primary_strategy_instance_id=config.primary_strategy_instance_id,
                windows=config.windows,
                risk_profile=resolved_risk,
                risk_mode=config.risk_mode,
                data_build=config.data_build,
                warmup_bars_by_role=config.warmup_bars_by_role,
            )
            logger.info(f"Applied risk overrides: {risk_overrides}")
        
        # Get strategy from primary instance
        primary = config.get_primary_strategy()
        try:
            strategy = get_strategy(primary.strategy_id, primary.strategy_version)
        except ValueError as e:
            return ToolResult(
                success=False,
                error=f"Strategy not found: {e}",
            )
        
        # Determine run directory for artifacts (system-first layout)
        run_dir = None
        if write_artifacts:
            writer = get_artifact_writer()
            run_id = f"run-{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            run_dir = writer.get_backtest_run_dir(
                system_id=config.system_id,
                symbol=config.symbol,
                tf=config.tf,
                window_name=window_name,
                run_id=run_id,
            )
        
        # Create engine and run
        engine = BacktestEngine(config, window_name, run_dir=run_dir)
        
        # Load data first to catch data errors early
        try:
            engine.load_data()
        except ValueError as e:
            return ToolResult(
                success=False,
                error=f"Data error: {e}",
                data={
                    "system_id": system_id,
                    "symbol": config.symbol,
                    "tf": config.tf,
                    "window": window_name,
                    "suggestion": "Run data sync for this symbol/tf",
                },
            )
        
        # Run backtest
        result = engine.run(strategy)
        
        # Write manifest and eventlog (Phase 5 requirement)
        manifest_eventlog_paths = {}
        if write_artifacts and run_dir:
            preflight_data = preflight_result.data if run_preflight and preflight_result.success else None
            manifest_eventlog_paths = _write_manifest_and_eventlog(
                run_dir=run_dir,
                config=config,
                window_name=window_name,
                result=result,
                preflight_data=preflight_data,
            )
            logger.info(f"Wrote manifest and eventlog to {run_dir}")
        
        # Also write via epoch tracker if artifacts enabled (for lineage)
        if write_artifacts:
            _write_epoch_artifacts(config, window_name, result)
        
        # Get metrics (now a BacktestMetrics object)
        metrics = result.metrics
        
        # Build message based on early-stop status
        if result.stopped_early:
            msg = (f"Backtest stopped early ({result.stop_reason}): "
                   f"{metrics.total_trades} trades, PnL=${metrics.net_profit:,.2f}")
        else:
            msg = f"Backtest complete: {metrics.total_trades} trades, PnL=${metrics.net_profit:,.2f}"
        
        # Build response with new contract
        return ToolResult(
            success=True,
            message=msg,
            symbol=config.symbol,
            data={
                "run_id": result.run_id,
                # Identity (global)
                "system_id": result.system_id,
                "system_uid": result.system_uid,
                "strategy_id": result.strategy_id,
                "strategy_version": result.strategy_version,
                # Run context
                "window_name": result.window_name,
                "symbol": result.symbol,
                "tf": result.tf,
                "risk_mode": result.risk_mode,
                # Metrics (key fields for quick view)
                "metrics": metrics.to_dict(),
                "net_return_pct": metrics.net_return_pct,
                "max_drawdown_pct": metrics.max_drawdown_pct,
                "total_trades": metrics.total_trades,
                "sharpe": metrics.sharpe,
                # Resolved risk used
                "risk_initial_equity_used": result.risk_initial_equity_used,
                "risk_per_trade_pct_used": result.risk_per_trade_pct_used,
                "risk_max_leverage_used": result.risk_max_leverage_used,
                # Artifact paths
                "artifact_dir": result.artifact_dir,
                "trades_path": result.trades_path,
                "equity_path": result.equity_path,
                "result_path": result.result_path,
                "manifest_path": str(manifest_eventlog_paths.get("run_manifest.json", "")) if manifest_eventlog_paths else None,
                "eventlog_path": str(manifest_eventlog_paths.get("events.jsonl", "")) if manifest_eventlog_paths else None,
                # Trade summary
                "trade_count": len(result.trades),
                "trades_summary": {
                    "total": len(result.trades),
                    "winners": metrics.win_count,
                    "losers": metrics.loss_count,
                },
                # Early-stop fields
                "stopped_early": result.stopped_early,
                "stop_reason": result.stop_reason,
                "stop_details": result.stop_details,
            },
        )
        
    except Exception as e:
        logger.error(f"Backtest failed for {system_id}/{window_name}: {e}")
        return ToolResult(
            success=False,
            error=f"Backtest failed: {e}",
        )


def _write_manifest_and_eventlog(
    run_dir: Path,
    config: SystemConfig,
    window_name: str,
    result,
    preflight_data: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """
    Write run_manifest.json and events.jsonl to run_dir.

    Called from backtest_run_tool after engine.run() completes.
    This respects the isolation rule (artifacts wired from tools layer).

    Pattern: Tools layer is responsible for artifact I/O. Engine produces data structures,
    tools write them to disk. This keeps the engine testable without filesystem dependencies.

    Args:
        run_dir: Directory for artifacts
        config: System configuration
        window_name: Window name
        result: BacktestResult from engine
        preflight_data: Optional preflight health report data

    Returns:
        Dict mapping artifact names to paths
    """
    artifacts = {}

    # 1. Write run_manifest.json (run metadata and config snapshot)
    manifest_writer = ManifestWriter(run_dir, artifact_version=ARTIFACT_VERSION)
    manifest_writer.set_run_info(
        run_id=result.run_id,
        system_id=result.system_id,
        symbol=result.symbol,
        tf_mapping={"htf": result.tf, "mtf": result.tf, "ltf": result.tf},  # Single-TF for now
    )
    manifest_writer.set_data_window(
        load_start=datetime.fromisoformat(result.data_window_loaded_start) if result.data_window_loaded_start else result.start_ts,
        load_end=datetime.fromisoformat(result.data_window_loaded_end) if result.data_window_loaded_end else result.end_ts,
        test_start=result.start_ts,
        test_end=result.end_ts,
    )
    manifest_writer.set_config(config.to_dict())
    if preflight_data and "health_report" in preflight_data:
        manifest_writer.set_health_report(preflight_data["health_report"])
    manifest_writer.set_git_info()
    manifest_writer.add_metadata("window_name", window_name)
    manifest_writer.add_metadata("risk_mode", result.risk_mode)
    manifest_writer.add_metadata("system_uid", result.system_uid)
    if result.stop_classification:
        manifest_writer.add_metadata("stop_classification", result.stop_classification.value)
    manifest_path = manifest_writer.write()
    artifacts["run_manifest.json"] = manifest_path
    
    # 2. Write events.jsonl (reconstruct from result data)
    with EventLogWriter(run_dir) as event_log:
        # Log equity curve as step events
        for eq_point in result.equity_curve:
            event_log.log_event("equity", {
                "ts": eq_point.timestamp.isoformat(),
                "equity": eq_point.equity,
                "drawdown": eq_point.drawdown,
                "drawdown_pct": eq_point.drawdown_pct,
            }, timestamp=eq_point.timestamp)
        
        # Log trades as fill events
        for trade in result.trades:
            # Entry fill
            event_log.log_fill({
                "trade_id": trade.trade_id,
                "symbol": trade.symbol,
                "side": trade.side,
                "type": "entry",
                "price": trade.entry_price,
                "qty": trade.entry_size,
                "size_usdt": trade.entry_size_usdt,
            }, timestamp=trade.entry_time)
            
            # Exit fill (if closed)
            if trade.exit_time:
                event_log.log_fill({
                    "trade_id": trade.trade_id,
                    "symbol": trade.symbol,
                    "side": trade.side,
                    "type": "exit",
                    "price": trade.exit_price,
                    "qty": trade.exit_size,
                    "pnl": trade.net_pnl,
                    "pnl_pct": trade.pnl_pct,
                }, timestamp=trade.exit_time)
        
        # Log stop event if applicable
        if result.stop_classification:
            event_log.log_event("stop", {
                "classification": result.stop_classification.value,
                "reason": result.stop_reason_detail,
                "bar_index": result.stop_bar_index,
            }, timestamp=result.stop_ts)
        
        # Log starvation event if applicable
        if result.first_starved_ts:
            event_log.log_entries_disabled(
                reason=f"Starvation at bar {result.first_starved_bar_index}",
                timestamp=result.first_starved_ts,
            )
    
    artifacts["events.jsonl"] = event_log.get_path()
    
    return artifacts


def _write_epoch_artifacts(
    config: SystemConfig,
    window_name: str,
    result,
) -> str | None:
    """Write epoch tracking metadata for lineage (separate from engine artifacts)."""
    try:
        tracker = StrategyEpochTracker(
            strategy_id=config.strategy_id,
            strategy_name=f"{config.system_id} ({config.strategy_id})",
        )
        
        # Build metadata including early-stop info
        metadata = {
            # Global identifiers (stable)
            "system_id": result.system_id,
            "system_uid": result.system_uid,
            "strategy_id": result.strategy_id,
            "strategy_version": result.strategy_version,
            # Run context
            "window_name": window_name,
            "risk_mode": result.risk_mode,
            "tf": result.tf,
            # Data context
            "data_env": result.data_env,
            # Risk used
            "risk_initial_equity_used": result.risk_initial_equity_used,
            "risk_per_trade_pct_used": result.risk_per_trade_pct_used,
            "risk_max_leverage_used": result.risk_max_leverage_used,
        }
        
        # Include early-stop info in metadata if applicable
        if result.stopped_early:
            metadata["stopped_early"] = result.stopped_early
            metadata["stop_reason"] = result.stop_reason
            metadata["stop_details"] = result.stop_details
        
        # Start epoch with full lineage metadata
        run_id = tracker.epoch_start(
            epoch=StrategyEpoch.BACKTEST,
            symbol=config.symbol,
            tfs=[config.tf],
            metadata=metadata,
            write_artifacts=True,
        )
        
        # Log trades
        for trade in result.trades:
            tracker.log_trade(
                run_id=run_id,
                symbol=trade.symbol,
                side=trade.side.upper(),
                size_usdt=trade.entry_size_usdt,
                price=trade.entry_price,
                pnl=trade.net_pnl,
            )
        
        # Determine passed/promotion_reason based on stop_reason or profitability
        metrics = result.metrics
        stop_reason = result.stop_reason
        
        # Early-stop terminal states always fail
        if stop_reason == "account_blown":
            passed = False
            promotion_reason = "Account blown"
        elif stop_reason == "insufficient_free_margin":
            passed = False
            promotion_reason = "Insufficient free margin"
        else:
            # Normal completion - pass if profitable
            passed = metrics.net_profit > 0
            promotion_reason = "Profitable" if passed else "Not profitable"
        
        # Complete epoch with BacktestMetrics as dict
        tracker.epoch_complete(
            run_id=run_id,
            epoch=StrategyEpoch.BACKTEST,
            symbol=config.symbol,
            metrics=metrics.to_dict(),
            passed=passed,
            promotion_reason=promotion_reason,
            write_artifacts=True,
        )
        
        # Return artifact directory
        writer = get_artifact_writer()
        return str(writer.get_run_dir(run_id))
        
    except Exception as e:
        logger.warning(f"Failed to write epoch artifacts: {e}")
        return None


# =============================================================================
# Data Preparation Tools (for backtest)
# =============================================================================

def backtest_prepare_data_tool(
    system_id: str,
    fresh_db: bool = False,
) -> ToolResult:
    """
    Prepare data for backtesting based on system config.
    
    Syncs the required symbol/tfs/period from the system's data_build config.
    Optionally wipes the database first (fresh_db=True).
    
    Args:
        system_id: System configuration ID
        fresh_db: If True, delete all data first (opt-in reset)
        
    Returns:
        ToolResult with sync results
    """
    try:
        # Load system config
        config = load_system_config(system_id)
        data_build = config.data_build
        
        # Optionally wipe database
        if fresh_db:
            logger.info("Fresh DB requested - wiping all data")
            from . import delete_all_data_tool
            wipe_result = delete_all_data_tool(vacuum=True, env=data_build.env)
            if not wipe_result.success:
                return ToolResult(
                    success=False,
                    error=f"Failed to wipe database: {wipe_result.error}",
                )
            logger.info("Database wiped successfully")
        
        # Get the store
        store = _get_historical_store(env=data_build.env)
        
        # Sync data for all tfs
        logger.info(
            f"Syncing data: {config.symbol} {data_build.period} "
            f"tfs={data_build.tfs}"
        )
        
        results = store.sync(
            symbols=[config.symbol],
            period=data_build.period,
            timeframes=data_build.tfs,
            show_spinner=False,
        )
        
        # Get status after sync
        status = store.status(config.symbol)
        
        return ToolResult(
            success=True,
            message=f"Data prepared for {config.symbol}: synced {len(data_build.tfs)} tfs",
            symbol=config.symbol,
            data={
                "system_id": system_id,
                "symbol": config.symbol,
                "period": data_build.period,
                "tfs": data_build.tfs,
                "sync_results": results,
                "status": status,
                "fresh_db": fresh_db,
            },
        )
        
    except Exception as e:
        logger.error(f"Data preparation failed: {e}")
        return ToolResult(
            success=False,
            error=f"Data preparation failed: {e}",
        )


def backtest_verify_data_tool(
    system_id: str,
    window_name: str = "hygiene",
    heal_gaps: bool = True,
) -> ToolResult:
    """
    Verify data quality for a backtest run.
    
    Checks if the required data exists and optionally heals gaps.
    
    Args:
        system_id: System configuration ID
        window_name: Window to verify data for
        heal_gaps: If True, attempt to heal gaps automatically
        
    Returns:
        ToolResult with data verification status
    """
    try:
        config = load_system_config(system_id, window_name)
        window = config.get_window(window_name)
        
        store = _get_historical_store(env=config.data_build.env)
        
        # Check data exists
        df = store.get_ohlcv(
            symbol=config.symbol,
            tf=config.tf,
            start=window.start,
            end=window.end,
        )
        
        has_data = not df.empty
        bar_count = len(df) if has_data else 0
        
        # Detect gaps
        gaps = []
        if has_data:
            gaps = store.detect_gaps(config.symbol, config.tf)
        
        # Optionally heal gaps
        gaps_healed = 0
        if heal_gaps and gaps:
            logger.info(f"Healing {len(gaps)} gaps for {config.symbol} {config.tf}")
            heal_result = store.fill_gaps(
                symbol=config.symbol,
                tf=config.tf,
            )
            gaps_healed = sum(heal_result.values()) if heal_result else 0
            
            # Recheck gaps
            gaps = store.detect_gaps(config.symbol, config.tf)
        
        # Get final status
        status = store.status(config.symbol)
        
        verification_passed = has_data and len(gaps) == 0
        
        return ToolResult(
            success=verification_passed,
            message=f"Data verification {'passed' if verification_passed else 'failed'}: "
                    f"{bar_count} bars, {len(gaps)} gaps",
            symbol=config.symbol,
            data={
                "system_id": system_id,
                "window_name": window_name,
                "symbol": config.symbol,
                "tf": config.tf,
                "window_start": window.start.isoformat(),
                "window_end": window.end.isoformat(),
                "has_data": has_data,
                "bar_count": bar_count,
                "gaps_found": len(gaps),
                "gaps_healed": gaps_healed,
                "verification_passed": verification_passed,
                "status": status,
            },
        )
        
    except Exception as e:
        logger.error(f"Data verification failed: {e}")
        return ToolResult(
            success=False,
            error=f"Data verification failed: {e}",
        )


# =============================================================================
# Strategy Tools
# =============================================================================

def backtest_list_strategies_tool() -> ToolResult:
    """
    List all available strategies with metadata.
    
    Strategies are code implementations. System configs select which strategy to use.
    
    Returns:
        ToolResult with list of strategies including:
        - strategy_id: Stable identifier
        - description: Human-readable description
        - default_version: Default version if not specified in system YAML
    """
    try:
        strategies = list_strategies_with_metadata()
        
        return ToolResult(
            success=True,
            message=f"Found {len(strategies)} strategies",
            data={
                "strategies": strategies,
                "note": "Strategies are code. System configs select which to use.",
            },
        )
    
    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to list strategies: {e}",
        )
