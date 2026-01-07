"""
Metrics API endpoints.

Provides endpoints for retrieving metrics summaries for dashboard display.
"""

from fastapi import APIRouter, HTTPException

from ..data.artifact_loader import find_run_path, load_run_metadata
from ..models.run_metadata import MetricsSummaryResponse, MetricCard, MetricsCategory

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

    # Build comprehensive categories with ALL metrics
    categories: list[MetricsCategory] = []

    # 1. Performance
    performance_cards = [
        MetricCard(
            label="Net PnL",
            value=_format_currency(net_pnl),
            change=_format_pct(net_return),
            trend=_get_trend(net_pnl),
            tooltip="Net profit/loss after fees",
        ),
        MetricCard(
            label="Return %",
            value=_format_pct(net_return),
            trend=_get_trend(net_return),
            tooltip="Net return percentage",
        ),
        MetricCard(
            label="Gross Profit",
            value=_format_currency(data.get("gross_profit_usdt", 0.0) or 0.0),
            trend="up",
            tooltip="Total profit from winning trades",
        ),
        MetricCard(
            label="Gross Loss",
            value=_format_currency(data.get("gross_loss_usdt", 0.0) or 0.0),
            trend="down",
            tooltip="Total loss from losing trades",
        ),
        MetricCard(
            label="Total Fees",
            value=_format_currency(-(data.get("total_fees_usdt", 0.0) or 0.0)),
            trend="neutral",
            tooltip="Total trading fees paid",
        ),
    ]
    categories.append(MetricsCategory(name="Performance", icon="profit", cards=performance_cards))

    # 2. Risk
    calmar = data.get("calmar", 0.0) or 0.0
    recovery = data.get("recovery_factor", 0.0) or 0.0
    risk_cards = [
        MetricCard(
            label="Max DD %",
            value=f"{max_dd_pct:.2f}%",
            change=_format_currency(-max_dd_abs),
            trend=_get_trend(-max_dd_pct, higher_is_better=False),
            tooltip="Maximum drawdown from peak equity",
        ),
        MetricCard(
            label="DD Duration",
            value=f"{data.get('max_drawdown_duration_bars', 0) or 0:,} bars",
            trend="neutral",
            tooltip="Longest drawdown period in bars",
        ),
        MetricCard(
            label="Sharpe",
            value=f"{sharpe:.2f}",
            trend=_get_trend(sharpe),
            tooltip="Risk-adjusted return (>1 good, >2 excellent)",
        ),
        MetricCard(
            label="Sortino",
            value=f"{sortino:.2f}",
            trend=_get_trend(sortino),
            tooltip="Downside risk-adjusted return",
        ),
        MetricCard(
            label="Calmar",
            value=f"{calmar:.2f}",
            trend=_get_trend(calmar),
            tooltip="Return / Max Drawdown",
        ),
        MetricCard(
            label="Recovery",
            value=f"{recovery:.2f}",
            trend=_get_trend(recovery),
            tooltip="Net Profit / Max Drawdown",
        ),
    ]
    categories.append(MetricsCategory(name="Risk", icon="risk", cards=risk_cards))

    # 3. Trade Quality
    payoff = data.get("payoff_ratio", 0.0) or 0.0
    quality_cards = [
        MetricCard(
            label="Expectancy",
            value=_format_currency(expectancy),
            change="/trade",
            trend=_get_trend(expectancy),
            tooltip="Expected value per trade",
        ),
        MetricCard(
            label="Payoff Ratio",
            value=f"{payoff:.2f}",
            trend=_get_trend(payoff - 1.0),
            tooltip="Avg Win / Avg Loss",
        ),
        MetricCard(
            label="Profit Factor",
            value=f"{profit_factor:.2f}",
            trend="up" if profit_factor >= 1.0 else "down",
            tooltip="Gross Profit / Gross Loss (>1.5 good)",
        ),
        MetricCard(
            label="Avg Trade Duration",
            value=f"{data.get('avg_trade_duration_bars', 0.0) or 0.0:.1f} bars",
            trend="neutral",
            tooltip="Average trade duration in bars",
        ),
    ]
    categories.append(MetricsCategory(name="Trade Quality", icon="ratio", cards=quality_cards))

    # 4. Win/Loss
    avg_win = data.get("avg_win_usdt", 0.0) or 0.0
    avg_loss = data.get("avg_loss_usdt", 0.0) or 0.0
    largest_win = data.get("largest_win_usdt", 0.0) or 0.0
    largest_loss = data.get("largest_loss_usdt", 0.0) or 0.0
    max_consec_wins = data.get("max_consecutive_wins", 0) or 0
    max_consec_losses = data.get("max_consecutive_losses", 0) or 0
    winloss_cards = [
        MetricCard(
            label="Win Rate",
            value=f"{win_rate:.1f}%",
            change=f"{win_count}W / {loss_count}L",
            trend="up" if win_rate >= 50 else "down",
            tooltip="Percentage of winning trades",
        ),
        MetricCard(
            label="Avg Win",
            value=_format_currency(avg_win),
            trend="up",
            tooltip="Average winning trade",
        ),
        MetricCard(
            label="Avg Loss",
            value=_format_currency(-avg_loss),
            trend="down",
            tooltip="Average losing trade",
        ),
        MetricCard(
            label="Largest Win",
            value=_format_currency(largest_win),
            trend="up",
            tooltip="Best single trade",
        ),
        MetricCard(
            label="Largest Loss",
            value=_format_currency(-largest_loss),
            trend="down",
            tooltip="Worst single trade",
        ),
        MetricCard(
            label="Consecutive",
            value=f"{max_consec_wins}W / {max_consec_losses}L",
            trend="neutral",
            tooltip="Max consecutive wins/losses",
        ),
    ]
    categories.append(MetricsCategory(name="Win/Loss", icon="trades", cards=winloss_cards))

    # 5. Long/Short
    long_trades = data.get("long_trades", 0) or 0
    short_trades = data.get("short_trades", 0) or 0
    long_wr = data.get("long_win_rate", 0.0) or 0.0
    short_wr = data.get("short_win_rate", 0.0) or 0.0
    long_pnl = data.get("long_pnl", 0.0) or 0.0
    short_pnl = data.get("short_pnl", 0.0) or 0.0
    longshort_cards = [
        MetricCard(
            label="Long Trades",
            value=str(long_trades),
            trend="neutral",
            tooltip="Number of long trades",
        ),
        MetricCard(
            label="Short Trades",
            value=str(short_trades),
            trend="neutral",
            tooltip="Number of short trades",
        ),
        MetricCard(
            label="Long Win Rate",
            value=f"{long_wr:.1f}%",
            trend="up" if long_wr >= 50 else "down",
            tooltip="Win rate for long trades",
        ),
        MetricCard(
            label="Short Win Rate",
            value=f"{short_wr:.1f}%",
            trend="up" if short_wr >= 50 else "down",
            tooltip="Win rate for short trades",
        ),
        MetricCard(
            label="Long PnL",
            value=_format_currency(long_pnl),
            trend=_get_trend(long_pnl),
            tooltip="Total PnL from long trades",
        ),
        MetricCard(
            label="Short PnL",
            value=_format_currency(short_pnl),
            trend=_get_trend(short_pnl),
            tooltip="Total PnL from short trades",
        ),
    ]
    categories.append(MetricsCategory(name="Long/Short", icon="percentage", cards=longshort_cards))

    # 6. Time
    total_bars = data.get("total_bars", 0) or 0
    bars_in_pos = data.get("bars_in_position", 0) or 0
    time_in_market = data.get("time_in_market_pct", 0.0) or 0.0
    time_cards = [
        MetricCard(
            label="Total Bars",
            value=f"{total_bars:,}",
            trend="neutral",
            tooltip="Total number of bars in backtest",
        ),
        MetricCard(
            label="Bars in Position",
            value=f"{bars_in_pos:,}",
            trend="neutral",
            tooltip="Number of bars with open position",
        ),
        MetricCard(
            label="Time in Market",
            value=f"{time_in_market:.1f}%",
            trend="neutral",
            tooltip="Percentage of time with open position",
        ),
        MetricCard(
            label="Total Trades",
            value=str(total_trades),
            trend="neutral",
            tooltip="Total trades executed",
        ),
    ]
    categories.append(MetricsCategory(name="Time", icon="time", cards=time_cards))

    return MetricsSummaryResponse(run_id=run_id, cards=cards, categories=categories)
