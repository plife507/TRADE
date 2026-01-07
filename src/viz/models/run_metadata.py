"""
Pydantic models for run metadata and API responses.
"""

from datetime import datetime
from pydantic import BaseModel, Field


class RunSummary(BaseModel):
    """Summary of a backtest run for list display."""

    run_id: str
    play_id: str
    symbol: str
    tf_exec: str
    category: str
    window_start: str
    window_end: str
    created_at: str | None = None

    # Key metrics for quick view
    trades_count: int = 0
    net_pnl_usdt: float = 0.0
    net_return_pct: float = 0.0
    win_rate: float = 0.0
    sharpe: float = 0.0
    max_drawdown_pct: float = 0.0

    # Path info
    artifact_path: str = ""
    has_snapshots: bool = False

    # Play description
    description: str = ""


class RunListResponse(BaseModel):
    """Response for GET /api/runs."""

    runs: list[RunSummary]
    total: int
    offset: int = 0
    limit: int = 50


class MetricCard(BaseModel):
    """Single metric card for dashboard display."""

    label: str
    value: str
    change: str | None = None
    trend: str = "neutral"  # "up", "down", "neutral"
    tooltip: str | None = None


class MetricsCategory(BaseModel):
    """Category grouping for metrics."""

    name: str
    icon: str  # Icon identifier (e.g., "profit", "risk", "trades")
    cards: list[MetricCard]


class MetricsSummaryResponse(BaseModel):
    """Response for GET /api/metrics/{run_id}/summary."""

    run_id: str
    cards: list[MetricCard]  # Primary 8 for backward compat
    categories: list[MetricsCategory] = []  # All by category


class RunDetailResponse(BaseModel):
    """Response for GET /api/runs/{run_id}."""

    run_id: str
    play_id: str
    symbol: str
    tf_exec: str
    category: str
    window_start: str
    window_end: str
    created_at: str | None = None

    # Full metrics
    initial_equity: float = 0.0
    final_equity: float = 0.0
    net_profit: float = 0.0
    net_return_pct: float = 0.0
    benchmark_return_pct: float = 0.0
    alpha_pct: float = 0.0

    # Drawdown
    max_drawdown_abs: float = 0.0
    max_drawdown_pct: float = 0.0
    max_drawdown_duration_bars: int = 0

    # Trade stats
    total_trades: int = 0
    win_count: int = 0
    loss_count: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0

    # Risk-adjusted
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0

    # Extended
    avg_win_usdt: float = 0.0
    avg_loss_usdt: float = 0.0
    largest_win_usdt: float = 0.0
    largest_loss_usdt: float = 0.0
    avg_trade_duration_bars: float = 0.0
    expectancy_usdt: float = 0.0
    payoff_ratio: float = 0.0

    # Long/short
    long_trades: int = 0
    short_trades: int = 0
    long_win_rate: float = 0.0
    short_win_rate: float = 0.0
    long_pnl: float = 0.0
    short_pnl: float = 0.0

    # Time
    total_bars: int = 0
    bars_in_position: int = 0
    time_in_market_pct: float = 0.0

    # Tail risk
    var_95_pct: float = 0.0
    cvar_95_pct: float = 0.0

    # Trade quality
    mae_avg_pct: float = 0.0
    mfe_avg_pct: float = 0.0

    # Path info
    artifact_path: str = ""
    has_snapshots: bool = False
