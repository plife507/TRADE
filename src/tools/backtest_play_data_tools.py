"""
Play data and discovery tools.

Extracted from backtest_play_tools.py:
- Indicator key discovery
- Data fix (sync/heal for Play)
- List plays
"""

import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

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
from ..backtest.play import load_play, list_plays
from ..backtest.execution_validation import validate_play_full
from ..utils.logger import get_logger


logger = get_logger()


# =============================================================================
# Indicator Key Discovery (tools-layer)
# =============================================================================

def backtest_indicators_tool(
    play_id: str,
    data_env: DataEnv = DEFAULT_BACKTEST_ENV,
    start: datetime | None = None,
    end: datetime | None = None,
    plays_dir: Path | None = None,
    compute_values: bool = False,
) -> ToolResult:
    """
    Discover and print indicator keys for an Play.

    This command replaces pytest-based indicator key validation.
    Run this to see exactly what indicator keys will be computed
    so you can fix FeatureSpec/Play declarations.

    Args:
        play_id: Play identifier
        data_env: Data environment ("live" or "demo")
        start: Window start (for computing actual values)
        end: Window end
        plays_dir: Override Play directory
        compute_values: If True, actually compute indicators and show first non-NaN index

    Returns:
        ToolResult with indicator key discovery results

    Note:
        Symbol is taken from the Play configuration (Play.symbol_universe[0]).
        Plays are self-contained and deterministic.
    """
    try:
        # Validate env
        data_env = validate_data_env(data_env)
        db_path = resolve_db_path(data_env)

        # Load Play
        try:
            play = load_play(play_id, base_dir=plays_dir)
        except FileNotFoundError as e:
            return ToolResult(
                success=False,
                error=str(e),
                data={"available_plays": list_plays(plays_dir)},
            )

        # Validate Play
        validation = validate_play_full(play)
        if not validation.is_valid:
            return ToolResult(
                success=False,
                error=f"Play validation failed: {[i.message for i in validation.errors]}",
            )

        # Get symbol from Play (Play is the single source of truth)
        if not play.symbol_universe:
            return ToolResult(
                success=False,
                error="Play has no symbols in symbol_universe",
            )
        symbol = validate_symbol(play.symbol_universe[0])

        # Get all features by TF from registry
        registry = play.feature_registry
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
            "play_id": play_id,
            "data_env": data_env,
            "db_path": str(db_path),
            "symbol": symbol,
            "exec_tf": play.exec_tf,
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
        logger.info(f"Indicator key discovery for {play_id}:")
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


def backtest_data_fix_tool(
    play_id: str,
    env: DataEnv = DEFAULT_BACKTEST_ENV,
    start: datetime | None = None,
    end: datetime | None = None,
    max_lookback_days: int = 7,
    sync_to_now: bool = False,
    sync: bool = True,
    heal: bool = False,
    plays_dir: Path | None = None,
) -> ToolResult:
    """
    Fix data for an Play backtest by calling existing data tools.

    Phase 6: Bounded enforcement + progress tracking + structured result.

    Args:
        play_id: Play identifier
        env: Data environment
        start: Sync from this date (default: Play warmup requirements)
        end: Sync to this date (required for bounded mode)
        max_lookback_days: Max lookback days (default 7). If (end - start) > this, clamp start.
        sync_to_now: If True, sync data to current time
        sync: If True, sync gaps after range sync
        heal: If True, run full heal after sync
        plays_dir: Override Play directory

    Returns:
        ToolResult with structured data fix summary including bounds and progress

    Note:
        Symbol is taken from the Play configuration (Play.symbol_universe[0]).
        Plays are self-contained and deterministic.
    """
    from .data_tools import (
        sync_range_tool,
        sync_forward_tool,
        sync_data_tool,
        heal_data_tool,
    )

    try:
        # Validate env
        env = validate_data_env(env)
        db_path = resolve_db_path(env)

        # Load Play to get TFs
        play = load_play(play_id, base_dir=plays_dir)

        # Get symbol from Play (Play is the single source of truth)
        if not play.symbol_universe:
            return ToolResult(
                success=False,
                error="Play has no symbols in symbol_universe",
            )
        symbol = validate_symbol(play.symbol_universe[0])

        # Get all TFs from Play + mandatory 1m for price feed
        tfs = set(play.get_all_tfs())
        # 1m is mandatory for price feed (quote proxy) - always include
        tfs.add("1m")
        tfs = sorted(tfs)

        # Phase 6: Track progress via callback counter
        progress_lines_count = 0

        def progress_callback(sym: str, tf: str, msg: str):
            nonlocal progress_lines_count
            progress_lines_count += 1
            logger.info(f"  [{sym} {tf}] {msg}")

        operations: list[dict[str, Any]] = []

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
            "start_ts_ms": datetime_to_epoch_ms(start),
            "end_ts_ms": datetime_to_epoch_ms(end),
            "cap": {"max_lookback_days": max_lookback_days},
            "applied": bounds_applied,
        }

        logger.info(f"Data fix for {play_id}: env={env}, db={db_path}, symbol={symbol}, tfs={tfs}")
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

        # Sync to now + sync gaps
        if sync_to_now:
            result = sync_forward_tool(
                symbols=[symbol],
                timeframes=tfs,
                env=env,
            )
            operations.append({
                "name": "sync_forward",
                "success": result.success,
                "message": result.message if result.success else result.error,
            })
            progress_lines_count += 1

        # Sync gaps
        if sync and not sync_to_now:
            for tf in tfs:
                result = sync_data_tool(
                    symbol=symbol,
                    timeframe=tf,
                    env=env,
                )
                operations.append({
                    "name": "sync_data",
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
    plays_dir: Path | None = None,
) -> ToolResult:
    """
    List available Plays.

    Args:
        plays_dir: Override Play directory

    Returns:
        ToolResult with list of Play IDs
    """
    try:
        cards = list_plays(base_dir=plays_dir)

        return ToolResult(
            success=True,
            message=f"Found {len(cards)} Plays",
            data={
                "plays": cards,
                "directory": str(plays_dir) if plays_dir else "plays/",
            },
        )

    except Exception as e:
        return ToolResult(
            success=False,
            error=f"Failed to list Plays: {e}",
        )
