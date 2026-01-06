"""
Artifact Schema: Canonical field definitions for backtest artifacts.

This module defines the data contract between:
- Backtest engine (exports artifacts)
- Visualization system (imports artifacts)

Design Principles:
1. Parquet timestamps: epoch_ms (int64) for efficient parsing, ISO for human readability
2. Field names: Follow CLAUDE.md conventions (*_usdt suffix for currency)
3. Nullable fields: Explicitly marked with | None
4. Both sides import from here - single source of truth

Usage:
    from src.viz.schemas import TRADES_SCHEMA, TradeRecord
"""

from dataclasses import dataclass
from typing import Any


# =============================================================================
# TRADES.PARQUET SCHEMA
# =============================================================================

@dataclass(frozen=True)
class TradeRecord:
    """
    Single trade record in trades.parquet.

    Timestamps are stored as BOTH:
    - ISO string (human readable): entry_time, exit_time
    - Epoch seconds (int): entry_ts, exit_ts (for efficient viz parsing)
    """

    # Identity
    trade_id: str
    symbol: str
    side: str  # "long" or "short" (lowercase)

    # Timestamps - dual format for efficiency
    entry_time: str  # ISO8601: "2025-12-03T10:00:00"
    entry_ts: int  # Unix seconds: 1764774000
    exit_time: str | None  # ISO8601, None if open
    exit_ts: int | None  # Unix seconds, None if open

    # Prices
    entry_price: float
    exit_price: float | None

    # Sizing (USDT standard per CLAUDE.md)
    entry_size_usdt: float

    # PnL
    net_pnl: float
    pnl_pct: float

    # Risk levels
    stop_loss: float | None
    take_profit: float | None

    # Exit metadata
    exit_reason: str | None  # "sl", "tp", "signal", "eod", etc.
    exit_price_source: str | None  # "sl_level", "bar_close", etc.

    # Bar indices for chart alignment
    entry_bar_index: int
    exit_bar_index: int | None
    duration_bars: int

    # Trade quality metrics
    mae_pct: float  # Max Adverse Excursion
    mfe_pct: float  # Max Favorable Excursion

    # Funding (perpetuals)
    funding_pnl: float


# Canonical column names for trades.parquet
TRADES_SCHEMA: dict[str, Any] = {
    "columns": [
        # Required columns
        "trade_id",
        "symbol",
        "side",
        "entry_time",  # ISO string
        "entry_ts",  # Epoch seconds (NEW)
        "exit_time",  # ISO string
        "exit_ts",  # Epoch seconds (NEW)
        "entry_price",
        "exit_price",
        "entry_size_usdt",  # Was: qty
        "net_pnl",  # Was: pnl
        "pnl_pct",
        "stop_loss",
        "take_profit",
        "exit_reason",
        "exit_price_source",
        "entry_bar_index",
        "exit_bar_index",
        "duration_bars",
        "mae_pct",
        "mfe_pct",
        "funding_pnl",
    ],
    "required": [
        "trade_id",
        "side",
        "entry_time",
        "entry_ts",
        "entry_price",
        "entry_size_usdt",
        "net_pnl",
    ],
    "timestamp_columns": {
        "entry_time": "entry_ts",  # ISO -> epoch mapping
        "exit_time": "exit_ts",
    },
}


# =============================================================================
# EQUITY.PARQUET SCHEMA
# =============================================================================

@dataclass(frozen=True)
class EquityPoint:
    """
    Single equity point in equity.parquet.

    Timestamps stored as BOTH ISO and epoch for efficiency.
    """

    timestamp: str  # ISO8601: "2025-12-01T00:15:00"
    ts: int  # Unix seconds: 1764548100 (for efficient viz parsing)
    equity: float
    drawdown: float  # Absolute drawdown in USDT
    drawdown_pct: float  # Percentage drawdown (0.0 to 100.0)


# Canonical column names for equity.parquet
EQUITY_SCHEMA: dict[str, Any] = {
    "columns": [
        "timestamp",  # ISO string
        "ts",  # Epoch seconds (primary for viz)
        "equity",
        "drawdown",
        "drawdown_pct",
    ],
    "required": [
        "timestamp",
        "ts",
        "equity",
    ],
    "timestamp_columns": {
        "timestamp": "ts",  # ISO -> epoch mapping
    },
}


# =============================================================================
# RESULT.JSON SCHEMA
# =============================================================================

# Key field mappings for result.json
# These are at the TOP LEVEL (not nested under "metrics")
RESULT_SCHEMA: dict[str, Any] = {
    # Metadata
    "play_id": str,
    "symbol": str,
    "tf_exec": str,

    # Window (ISO timestamps - keep as strings for human readability)
    "window_start": str,  # ISO8601
    "window_end": str,  # ISO8601

    # Core metrics (at top level, not nested)
    "net_pnl_usdt": float,
    "net_return_pct": float,
    "winning_trades": int,
    "losing_trades": int,
    "win_rate": float,  # Decimal 0.0-1.0, NOT percentage

    # Risk metrics
    "sharpe": float,
    "sortino": float,
    "calmar": float,
    "max_drawdown_pct": float,
    "max_drawdown_usdt": float,
    "profit_factor": float,

    # Trade quality
    "expectancy_usdt": float,
    "avg_win_usdt": float,
    "avg_loss_usdt": float,

    # Hashes for verification
    "idea_hash": str,
    "trades_hash": str,
    "equity_hash": str,
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def iso_to_epoch(iso_str: str | None) -> int | None:
    """Convert ISO8601 string to Unix epoch seconds."""
    if iso_str is None:
        return None
    from datetime import datetime
    try:
        return int(datetime.fromisoformat(iso_str).timestamp())
    except (ValueError, TypeError):
        return None


def epoch_to_iso(epoch: int | None) -> str | None:
    """Convert Unix epoch seconds to ISO8601 string."""
    if epoch is None:
        return None
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()
    except (ValueError, TypeError, OSError):
        return None
