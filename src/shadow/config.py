"""
Shadow Exchange configuration.

Loaded from config/shadow.yml or constructed programmatically.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True, frozen=True)
class ShadowPlayConfig:
    """Per-play configuration for shadow mode."""
    initial_equity_usdt: float = 10_000.0
    max_drawdown_pct: float = 25.0
    auto_stop_on_drawdown: bool = False   # Log warning vs stop engine


@dataclass(slots=True, frozen=True)
class ShadowConfig:
    """Global shadow orchestrator configuration."""
    # Engine limits
    max_engines: int = 50
    max_engines_per_symbol: int = 10

    # Snapshot intervals
    snapshot_interval_seconds: int = 3600      # Hourly snapshots to DB
    health_check_interval_seconds: int = 60
    stale_threshold_seconds: int = 300         # Engine considered stale after 5min no candle

    # Auto-recovery
    auto_restart_on_stale: bool = True
    max_restart_attempts: int = 3

    # DB batch write
    db_flush_interval_seconds: int = 60        # Flush accumulated writes to DuckDB

    # Default play config
    default_play_config: ShadowPlayConfig = ShadowPlayConfig()
