"""
Proof-grade metrics computation.

Pure functions for computing comprehensive backtest metrics from:
- Account curve (full margin state per bar)
- Equity curve
- Trades list

No I/O operations - takes data and returns computed values.

Main function: compute_proof_metrics() -> BacktestMetricsV2
"""

import math
from datetime import datetime, timedelta
from typing import List, Optional

from .types import Trade, EquityPoint, AccountCurvePoint
from .proof_metrics_types import (
    BacktestMetricsV2,
    PerformanceMetrics,
    DrawdownMetrics,
    TradeQualityMetrics,
    RiskAdjustedMetrics,
    MarginStressMetrics,
    EntryFrictionMetrics,
    LiquidationProximityMetrics,
    ExposureMetrics,
    ProfitFactorResult,
)


# Timeframe to approximate bars per year (crypto markets ~365 days)
TF_BARS_PER_YEAR = {
    "1m": 365 * 24 * 60,      # 525,600
    "5m": 365 * 24 * 12,      # 105,120
    "15m": 365 * 24 * 4,      # 35,040
    "30m": 365 * 24 * 2,      # 17,520
    "1h": 365 * 24,           # 8,760
    "4h": 365 * 6,            # 2,190
    "1d": 365,                # 365
}


def compute_proof_metrics(
    account_curve: List[AccountCurvePoint],
    equity_curve: List[EquityPoint],
    trades: List[Trade],
    *,
    tf: str,
    initial_equity: float,
    entry_attempts: int = 0,
    entry_rejections: int = 0,
    first_starved_ts: Optional[datetime] = None,
    first_starved_bar_index: Optional[int] = None,
    liquidation_thresholds_pct: List[float] = None,
) -> BacktestMetricsV2:
    """
    Compute comprehensive proof-grade backtest metrics.
    
    This is a pure function - no I/O operations.
    
    Args:
        account_curve: List of AccountCurvePoint (margin state per bar)
        equity_curve: List of EquityPoint (bar-by-bar equity)
        trades: List of Trade objects (completed trades only)
        tf: Timeframe string for annualization (e.g., "1h", "5m")
        initial_equity: Starting equity from risk profile
        entry_attempts: Total entry attempts from exchange
        entry_rejections: Total entry rejections from exchange
        first_starved_ts: Timestamp when starvation first occurred
        first_starved_bar_index: Bar index when starvation first occurred
        liquidation_thresholds_pct: Thresholds for proximity checks (default [5, 10, 20])
        
    Returns:
        BacktestMetricsV2 with all computed fields
    """
    if liquidation_thresholds_pct is None:
        liquidation_thresholds_pct = [5.0, 10.0, 20.0]
    
    # =========================================================================
    # Tier 1: Performance
    # =========================================================================
    final_equity = equity_curve[-1].equity if equity_curve else initial_equity
    total_net_pnl = final_equity - initial_equity
    return_pct = (total_net_pnl / initial_equity * 100) if initial_equity > 0 else 0.0
    
    performance = PerformanceMetrics(
        final_equity_usdt=round(final_equity, 2),
        total_net_pnl_usdt=round(total_net_pnl, 2),
        return_pct=round(return_pct, 4),
    )
    
    # =========================================================================
    # Tier 1: Drawdown
    # =========================================================================
    max_dd_usdt, max_dd_pct, max_dd_duration, ulcer_index = _compute_drawdown_with_ulcer(
        equity_curve
    )
    
    drawdown = DrawdownMetrics(
        max_drawdown_usdt=round(max_dd_usdt, 2),
        max_drawdown_pct=round(max_dd_pct, 4),
        max_drawdown_duration_bars=max_dd_duration,
        ulcer_index=round(ulcer_index, 4),
    )
    
    # =========================================================================
    # Tier 1: Trade Quality
    # =========================================================================
    total_trades = len(trades)
    win_count = sum(1 for t in trades if t.net_pnl > 0)
    loss_count = sum(1 for t in trades if t.net_pnl < 0)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
    
    gross_profit = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    gross_loss = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    
    avg_win = (gross_profit / win_count) if win_count > 0 else 0.0
    avg_loss = (gross_loss / loss_count) if loss_count > 0 else 0.0
    
    profit_factor = ProfitFactorResult.compute(gross_profit, gross_loss)
    
    # Expectancy per trade
    expectancy = (total_net_pnl / total_trades) if total_trades > 0 else 0.0
    
    # Streaks
    max_win_streak, max_loss_streak = _compute_streaks(trades)
    
    # Average trade duration (placeholder - trades don't store bar counts)
    avg_duration = None  # Would need bar index on trades to compute
    
    trade_quality = TradeQualityMetrics(
        total_trades=total_trades,
        win_count=win_count,
        loss_count=loss_count,
        win_rate=round(win_rate, 2),
        avg_win_usdt=round(avg_win, 2),
        avg_loss_usdt=round(avg_loss, 2),
        profit_factor=profit_factor,
        expectancy_per_trade=round(expectancy, 4),
        avg_trade_duration_bars=avg_duration,
        max_winning_streak=max_win_streak,
        max_losing_streak=max_loss_streak,
    )
    
    # =========================================================================
    # Tier 2: Risk-Adjusted
    # =========================================================================
    sharpe = _compute_sharpe(equity_curve, tf)
    sortino = _compute_sortino(equity_curve, tf)
    
    # Calmar = annualized return / max drawdown %
    if max_dd_pct > 0:
        # Annualize return based on tf
        bars_per_year = TF_BARS_PER_YEAR.get(tf, 8760)
        n_bars = len(equity_curve)
        years = n_bars / bars_per_year if bars_per_year > 0 else 1.0
        annualized_return = (return_pct / years) if years > 0 else return_pct
        calmar = annualized_return / max_dd_pct
    else:
        calmar = None
    
    risk_adjusted = RiskAdjustedMetrics(
        sharpe_ratio=round(sharpe, 4) if sharpe is not None else None,
        sortino_ratio=round(sortino, 4) if sortino is not None else None,
        calmar_ratio=round(calmar, 4) if calmar is not None else None,
    )
    
    # =========================================================================
    # Tier 3: Margin Stress
    # =========================================================================
    margin_stress = _compute_margin_stress(account_curve)
    
    # =========================================================================
    # Tier 3: Entry Friction
    # =========================================================================
    entry_rejection_rate = (
        (entry_rejections / entry_attempts) if entry_attempts > 0 else 0.0
    )
    
    # Percent time entries disabled
    total_bars = len(account_curve)
    disabled_bars = sum(1 for a in account_curve if a.entries_disabled)
    pct_time_disabled = (disabled_bars / total_bars * 100) if total_bars > 0 else 0.0
    
    entry_friction = EntryFrictionMetrics(
        entry_rejections_count=entry_rejections,
        entry_attempts_count=entry_attempts,
        entry_rejection_rate=round(entry_rejection_rate, 4),
        first_starved_timestamp=first_starved_ts,
        first_starved_bar_index=first_starved_bar_index,
        pct_time_entries_disabled=round(pct_time_disabled, 2),
    )
    
    # =========================================================================
    # Tier 3: Liquidation Proximity
    # =========================================================================
    liquidation_proximity = _compute_liquidation_proximity(
        account_curve, liquidation_thresholds_pct
    )
    
    # =========================================================================
    # Tier 3: Exposure
    # =========================================================================
    exposure = _compute_exposure(account_curve, trades, tf)
    
    return BacktestMetricsV2(
        performance=performance,
        drawdown=drawdown,
        trade_quality=trade_quality,
        risk_adjusted=risk_adjusted,
        margin_stress=margin_stress,
        entry_friction=entry_friction,
        liquidation_proximity=liquidation_proximity,
        exposure=exposure,
    )


def _compute_drawdown_with_ulcer(
    equity_curve: List[EquityPoint],
) -> tuple[float, float, int, float]:
    """
    Compute drawdown metrics including ulcer index.
    
    Ulcer index = sqrt(mean of squared drawdown percentages)
    Measures the depth and duration of drawdowns.
    
    Returns:
        Tuple of (max_dd_usdt, max_dd_pct, max_dd_duration_bars, ulcer_index)
    """
    if not equity_curve:
        return 0.0, 0.0, 0, 0.0
    
    peak = equity_curve[0].equity
    max_dd_usdt = 0.0
    max_dd_pct = 0.0
    
    # Track duration
    current_dd_start = None
    current_dd_bars = 0
    max_dd_duration = 0
    
    # For ulcer index
    dd_pcts_squared = []
    
    for i, point in enumerate(equity_curve):
        equity = point.equity
        
        if equity > peak:
            peak = equity
            if current_dd_start is not None:
                if current_dd_bars > max_dd_duration:
                    max_dd_duration = current_dd_bars
                current_dd_start = None
                current_dd_bars = 0
            dd_pcts_squared.append(0.0)
        else:
            if current_dd_start is None:
                current_dd_start = i
            current_dd_bars = i - current_dd_start + 1
            
            dd_usdt = peak - equity
            dd_pct = (dd_usdt / peak * 100) if peak > 0 else 0.0
            dd_pcts_squared.append(dd_pct ** 2)
            
            if dd_usdt > max_dd_usdt:
                max_dd_usdt = dd_usdt
                max_dd_pct = dd_pct
    
    # Check if still in drawdown at end
    if current_dd_start is not None and current_dd_bars > max_dd_duration:
        max_dd_duration = current_dd_bars
    
    # Ulcer index
    if dd_pcts_squared:
        ulcer_index = math.sqrt(sum(dd_pcts_squared) / len(dd_pcts_squared))
    else:
        ulcer_index = 0.0
    
    return max_dd_usdt, max_dd_pct, max_dd_duration, ulcer_index


def _compute_streaks(trades: List[Trade]) -> tuple[int, int]:
    """
    Compute max winning and losing streaks.
    
    Returns:
        Tuple of (max_win_streak, max_loss_streak)
    """
    if not trades:
        return 0, 0
    
    max_win = 0
    max_loss = 0
    current_win = 0
    current_loss = 0
    
    for trade in trades:
        if trade.net_pnl > 0:
            current_win += 1
            current_loss = 0
            max_win = max(max_win, current_win)
        elif trade.net_pnl < 0:
            current_loss += 1
            current_win = 0
            max_loss = max(max_loss, current_loss)
        else:
            # Breakeven resets both streaks
            current_win = 0
            current_loss = 0
    
    return max_win, max_loss


def _compute_sharpe(
    equity_curve: List[EquityPoint],
    tf: str,
    risk_free_rate: float = 0.0,
) -> Optional[float]:
    """
    Compute annualized Sharpe ratio from per-bar equity returns.
    
    Returns None if insufficient data or zero variance.
    """
    if len(equity_curve) < 2:
        return None
    
    returns = []
    for i in range(1, len(equity_curve)):
        prev_equity = equity_curve[i - 1].equity
        curr_equity = equity_curve[i].equity
        
        if prev_equity > 0:
            ret = (curr_equity / prev_equity) - 1.0
            returns.append(ret)
    
    if len(returns) < 2:
        return None
    
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_return = math.sqrt(variance)
    
    if std_return == 0:
        return None
    
    bars_per_year = TF_BARS_PER_YEAR.get(tf, 8760)
    annualization = math.sqrt(bars_per_year)
    
    return (mean_return - risk_free_rate) / std_return * annualization


def _compute_sortino(
    equity_curve: List[EquityPoint],
    tf: str,
    risk_free_rate: float = 0.0,
) -> Optional[float]:
    """
    Compute annualized Sortino ratio (using downside deviation).
    
    Like Sharpe but only considers negative returns for volatility.
    Returns None if insufficient data or zero downside deviation.
    """
    if len(equity_curve) < 2:
        return None
    
    returns = []
    for i in range(1, len(equity_curve)):
        prev_equity = equity_curve[i - 1].equity
        curr_equity = equity_curve[i].equity
        
        if prev_equity > 0:
            ret = (curr_equity / prev_equity) - 1.0
            returns.append(ret)
    
    if len(returns) < 2:
        return None
    
    mean_return = sum(returns) / len(returns)
    
    # Downside deviation (only negative returns)
    negative_returns = [r for r in returns if r < 0]
    if not negative_returns:
        # No negative returns = infinite Sortino, return None
        return None
    
    downside_variance = sum(r ** 2 for r in negative_returns) / len(returns)
    downside_std = math.sqrt(downside_variance)
    
    if downside_std == 0:
        return None
    
    bars_per_year = TF_BARS_PER_YEAR.get(tf, 8760)
    annualization = math.sqrt(bars_per_year)
    
    return (mean_return - risk_free_rate) / downside_std * annualization


def _compute_margin_stress(
    account_curve: List[AccountCurvePoint],
) -> MarginStressMetrics:
    """
    Compute margin stress metrics from account curve.
    """
    if not account_curve:
        return MarginStressMetrics(
            max_used_margin_usdt=0.0,
            max_used_margin_pct_of_equity=0.0,
            min_free_margin_usdt=0.0,
            min_available_balance_usdt=0.0,
        )
    
    max_used = 0.0
    max_used_pct = 0.0
    min_free = float("inf")
    min_available = float("inf")
    
    for point in account_curve:
        if point.used_margin_usdt > max_used:
            max_used = point.used_margin_usdt
        
        if point.equity_usdt > 0 and point.used_margin_usdt > 0:
            used_pct = (point.used_margin_usdt / point.equity_usdt) * 100
            if used_pct > max_used_pct:
                max_used_pct = used_pct
        
        if point.free_margin_usdt < min_free:
            min_free = point.free_margin_usdt
        
        if point.available_balance_usdt < min_available:
            min_available = point.available_balance_usdt
    
    # Handle case where values were never updated
    if min_free == float("inf"):
        min_free = 0.0
    if min_available == float("inf"):
        min_available = 0.0
    
    return MarginStressMetrics(
        max_used_margin_usdt=round(max_used, 2),
        max_used_margin_pct_of_equity=round(max_used_pct, 2),
        min_free_margin_usdt=round(min_free, 2),
        min_available_balance_usdt=round(min_available, 2),
    )


def _compute_liquidation_proximity(
    account_curve: List[AccountCurvePoint],
    thresholds_pct: List[float],
) -> LiquidationProximityMetrics:
    """
    Compute how close we came to liquidation.
    
    Equity - Maintenance Margin is the buffer before liquidation.
    """
    if not account_curve:
        return LiquidationProximityMetrics(
            min_equity_minus_mm_usdt=0.0,
            bars_within_5pct_of_mm=0,
            bars_within_10pct_of_mm=0,
            bars_within_20pct_of_mm=0,
        )
    
    min_buffer = float("inf")
    bars_5pct = 0
    bars_10pct = 0
    bars_20pct = 0
    
    for point in account_curve:
        buffer = point.equity_usdt - point.maintenance_margin_usdt
        
        if buffer < min_buffer:
            min_buffer = buffer
        
        # Check proximity as % of equity
        if point.equity_usdt > 0:
            margin_ratio = (point.maintenance_margin_usdt / point.equity_usdt) * 100
            
            if margin_ratio >= 95:  # Within 5% of liquidation
                bars_5pct += 1
            if margin_ratio >= 90:  # Within 10%
                bars_10pct += 1
            if margin_ratio >= 80:  # Within 20%
                bars_20pct += 1
    
    if min_buffer == float("inf"):
        min_buffer = 0.0
    
    return LiquidationProximityMetrics(
        min_equity_minus_mm_usdt=round(min_buffer, 2),
        bars_within_5pct_of_mm=bars_5pct,
        bars_within_10pct_of_mm=bars_10pct,
        bars_within_20pct_of_mm=bars_20pct,
    )


def _compute_exposure(
    account_curve: List[AccountCurvePoint],
    trades: List[Trade],
    tf: str,
) -> ExposureMetrics:
    """
    Compute market exposure metrics.
    """
    if not account_curve:
        return ExposureMetrics(
            time_in_market_pct=0.0,
            trades_per_day=None,
        )
    
    # Time in market
    total_bars = len(account_curve)
    bars_with_position = sum(1 for a in account_curve if a.has_position)
    time_in_market = (bars_with_position / total_bars * 100) if total_bars > 0 else 0.0
    
    # Trades per day
    trades_per_day = None
    if len(account_curve) >= 2 and trades:
        start_ts = account_curve[0].timestamp
        end_ts = account_curve[-1].timestamp
        delta = end_ts - start_ts
        days = delta.total_seconds() / (24 * 3600)
        if days > 0:
            trades_per_day = len(trades) / days
    
    return ExposureMetrics(
        time_in_market_pct=round(time_in_market, 2),
        trades_per_day=round(trades_per_day, 4) if trades_per_day is not None else None,
    )

