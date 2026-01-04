"""
CLI Wrapper for Play-based backtests.

This module re-exports all backtest tools from their focused modules
for backward compatibility. New code should import directly from:
- backtest_play_tools.py: Play execution tools
- backtest_audit_tools.py: Audit and verification tools

This is the GOLDEN PATH for backtest execution:
CLI (trade_cli.py subcommands) → this wrapper → domain (engine/data)

All backtest validation, including smoke tests, should call these tools.
No ad-hoc test harnesses that re-implement pipeline logic.
"""

# =============================================================================
# Re-exports from backtest_play_tools.py
# =============================================================================

from .backtest_play_tools import (
    # Constants
    CANONICAL_TIMEFRAMES,
    BYBIT_API_INTERVALS,
    BYBIT_TO_CANONICAL,
    # Utilities
    validate_canonical_tf,
    normalize_timestamp,
    # Play Tools
    backtest_preflight_play_tool,
    backtest_run_play_tool,
    backtest_indicators_tool,
    backtest_data_fix_tool,
    backtest_list_plays_tool,
    backtest_play_normalize_tool,
    backtest_play_normalize_batch_tool,
)


# =============================================================================
# Re-exports from backtest_audit_tools.py
# =============================================================================

from .backtest_audit_tools import (
    # Audit Tools
    backtest_audit_math_from_snapshots_tool,
    backtest_audit_toolkit_tool,
    backtest_audit_in_memory_parity_tool,
    backtest_math_parity_tool,
    verify_artifact_parity_tool,
    backtest_audit_snapshot_plumbing_tool,
    backtest_audit_rollup_parity_tool,
)


# =============================================================================
# __all__ for explicit exports
# =============================================================================

__all__ = [
    # Constants
    "CANONICAL_TIMEFRAMES",
    "BYBIT_API_INTERVALS",
    "BYBIT_TO_CANONICAL",
    # Utilities
    "validate_canonical_tf",
    "normalize_timestamp",
    # Play Tools
    "backtest_preflight_play_tool",
    "backtest_run_play_tool",
    "backtest_indicators_tool",
    "backtest_data_fix_tool",
    "backtest_list_plays_tool",
    "backtest_play_normalize_tool",
    "backtest_play_normalize_batch_tool",
    # Audit Tools
    "backtest_audit_math_from_snapshots_tool",
    "backtest_audit_toolkit_tool",
    "backtest_audit_in_memory_parity_tool",
    "backtest_math_parity_tool",
    "verify_artifact_parity_tool",
    "backtest_audit_snapshot_plumbing_tool",
    "backtest_audit_rollup_parity_tool",
]
