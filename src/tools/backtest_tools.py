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
# Legacy strategy registry imports removed (2026-01-11)
# The Play-based system replaces the old strategy registry
# Use CLI: python trade_cli.py backtest run --play <play_id>
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

