"""
Backtest tools for TRADE trading bot (DEPRECATED).

IMPORTANT: SystemConfig-based tools in this file are deprecated.
Use Play-based tools from backtest_play_tools.py instead:
  - backtest_list_plays_tool()
  - backtest_run_play_tool()

CLI equivalent:
  python trade_cli.py backtest run --play <play_id> --start <date> --end <date>

See docs/specs/PLAY_DSL_COOKBOOK.md for Play YAML format documentation.
"""

from typing import Any

from .shared import ToolResult
# Legacy imports removed - SystemConfig tools are deprecated
# Use Play-based tools: backtest_run_play_tool() etc.
from ..utils.logger import get_logger

logger = get_logger()

# Phase -1: Maximum heal attempts before hard-fail
MAX_HEAL_ATTEMPTS = 3

# =============================================================================
# System Config Tools (DEPRECATED - Use Play tools instead)
# =============================================================================

_SYSTEM_DEPRECATION_MSG = (
    "REMOVED: SystemConfig-based tools are no longer supported.\n\n"
    "Use Play-based tools instead:\n"
    "  - backtest_list_plays_tool() to list available plays\n"
    "  - backtest_run_play_tool() to run a backtest\n\n"
    "CLI equivalent:\n"
    "  python trade_cli.py backtest run --play <play_id> --start <date> --end <date>\n\n"
    "See docs/specs/PLAY_DSL_COOKBOOK.md for Play YAML format documentation."
)


def backtest_list_systems_tool() -> ToolResult:
    """
    REMOVED: SystemConfig is no longer supported. Use backtest_list_plays_tool() instead.
    """
    return ToolResult(
        success=False,
        error=_SYSTEM_DEPRECATION_MSG,
    )


def backtest_get_system_tool(system_id: str) -> ToolResult:
    """
    REMOVED: SystemConfig is no longer supported. Use Play YAML format instead.
    """
    return ToolResult(
        success=False,
        error=_SYSTEM_DEPRECATION_MSG,
    )

# =============================================================================
# Phase -1: Preflight Data Health Gate (DEPRECATED)
# =============================================================================

def backtest_preflight_check_tool(
    system_id: str,
    window_name: str = "hygiene",
    heal_if_needed: bool = True,
    max_heal_attempts: int = MAX_HEAL_ATTEMPTS,
    auto_bootstrap: bool = True,
) -> ToolResult:
    """
    REMOVED: SystemConfig is no longer supported. Use Play-based preflight instead.

    The Play-based runner (run_backtest_with_gates) handles preflight automatically.
    """
    return ToolResult(
        success=False,
        error=_SYSTEM_DEPRECATION_MSG,
    )


# =============================================================================
# Backtest Run Tool
# =============================================================================

# =============================================================================
# Data Preparation Tools (DEPRECATED - Use Play-based tools)
# =============================================================================

def backtest_prepare_data_tool(
    system_id: str,
    fresh_db: bool = False,
) -> ToolResult:
    """
    REMOVED: SystemConfig is no longer supported. Use sync_tool directly.

    For data preparation, use the data tools directly:
      - sync_tool(symbols=[...], period="1Y", timeframes=[...])
      - sync_range_tool(symbols=[...], start=..., end=..., timeframes=[...])
    """
    return ToolResult(
        success=False,
        error=_SYSTEM_DEPRECATION_MSG,
    )


def backtest_verify_data_tool(
    system_id: str,
    window_name: str = "hygiene",
    heal_gaps: bool = True,
) -> ToolResult:
    """
    REMOVED: SystemConfig is no longer supported. Use Play-based tools instead.

    The Play-based runner handles data verification automatically.
    """
    return ToolResult(
        success=False,
        error=_SYSTEM_DEPRECATION_MSG,
    )

