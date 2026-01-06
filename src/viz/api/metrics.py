"""
Metrics API endpoints.

Provides endpoints for retrieving metrics summaries for dashboard display.
"""

from fastapi import APIRouter, HTTPException

from ..data.artifact_loader import find_run_path, load_run_metadata
from ..models.run_metadata import MetricsSummaryResponse, MetricCard

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _format_currency(value: float) -> str:
    """Format currency value with sign and appropriate precision."""
    if abs(value) >= 1000:
        return f"${value:+,.0f}"
    return f"${value:+,.2f}"


def _format_pct(value: float) -> str:
    """Format percentage value."""
    return f"{value:+.2f}%"


def _get_trend(value: float, higher_is_better: bool = True) -> str:
    """Determine trend direction based on value."""
    if abs(value) < 0.001:
        return "neutral"
    if higher_is_better:
        return "up" if value > 0 else "down"
    return "down" if value > 0 else "up"


@router.get("/{run_id}/summary", response_model=MetricsSummaryResponse)
async def get_metrics_summary(run_id: str) -> MetricsSummaryResponse:
    """
    Get metrics summary for dashboard cards.

    Returns key metrics formatted for display in stat cards.
    """
    run_path = find_run_path(run_id)

    if not run_path:
        raise HTTPException(status_code=404, detail=f"Run {run_id} not found")

    data = load_run_metadata(run_path)
    if not data:
        raise HTTPException(status_code=404, detail=f"Could not load run {run_id}")

    # Result.json has metrics at top level (not nested under "metrics")
    # Field mapping: result.json keys differ from expected keys

    # Build metric cards
    cards: list[MetricCard] = []

    # Net PnL (result.json uses net_pnl_usdt)
    net_pnl = data.get("net_pnl_usdt", 0.0) or 0.0
    net_return = data.get("net_return_pct", 0.0) or 0.0
    cards.append(
        MetricCard(
            label="Net PnL",
            value=_format_currency(net_pnl),
            change=_format_pct(net_return),
            trend=_get_trend(net_pnl),
            tooltip="Net profit/loss after fees",
        )
    )

    # Win Rate (result.json has win_rate as decimal 0.037, need to convert to %)
    win_rate_decimal = data.get("win_rate", 0.0) or 0.0
    win_rate = win_rate_decimal * 100  # Convert to percentage
    win_count = data.get("winning_trades", 0) or 0
    loss_count = data.get("losing_trades", 0) or 0
    cards.append(
        MetricCard(
            label="Win Rate",
            value=f"{win_rate:.1f}%",
            change=f"{win_count}W / {loss_count}L",
            trend="up" if win_rate >= 50 else "down",
            tooltip="Percentage of winning trades",
        )
    )

    # Sharpe Ratio
    sharpe = data.get("sharpe", 0.0) or 0.0
    cards.append(
        MetricCard(
            label="Sharpe",
            value=f"{sharpe:.2f}",
            trend=_get_trend(sharpe),
            tooltip="Risk-adjusted return (>1 is good, >2 is excellent)",
        )
    )

    # Max Drawdown
    max_dd_pct = data.get("max_drawdown_pct", 0.0) or 0.0
    max_dd_abs = data.get("max_drawdown_usdt", 0.0) or 0.0
    cards.append(
        MetricCard(
            label="Max DD",
            value=f"{max_dd_pct:.1f}%",
            change=_format_currency(-max_dd_abs),
            trend=_get_trend(-max_dd_pct, higher_is_better=False),
            tooltip="Maximum drawdown from peak equity",
        )
    )

    # Total Trades
    total_trades = (data.get("winning_trades", 0) or 0) + (data.get("losing_trades", 0) or 0)
    cards.append(
        MetricCard(
            label="Trades",
            value=str(total_trades),
            trend="neutral",
            tooltip="Total number of trades executed",
        )
    )

    # Profit Factor
    profit_factor = data.get("profit_factor", 0.0) or 0.0
    cards.append(
        MetricCard(
            label="Profit Factor",
            value=f"{profit_factor:.2f}",
            trend="up" if profit_factor >= 1.0 else "down",
            tooltip="Gross profit / gross loss (>1.5 is good)",
        )
    )

    # Sortino (optional second row)
    sortino = data.get("sortino", 0.0) or 0.0
    cards.append(
        MetricCard(
            label="Sortino",
            value=f"{sortino:.2f}",
            trend=_get_trend(sortino),
            tooltip="Downside risk-adjusted return",
        )
    )

    # Expectancy
    expectancy = data.get("expectancy_usdt", 0.0) or 0.0
    cards.append(
        MetricCard(
            label="Expectancy",
            value=_format_currency(expectancy),
            change="/trade",
            trend=_get_trend(expectancy),
            tooltip="Expected value per trade",
        )
    )

    return MetricsSummaryResponse(run_id=run_id, cards=cards)
