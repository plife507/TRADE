"""
Backtest metrics calculation.

Pure math functions for computing backtest performance metrics.
No I/O operations - takes data and returns computed values.

Main function: compute_backtest_metrics() -> BacktestMetrics
"""

import math
from typing import List, Tuple, Optional

from .types import Trade, EquityPoint, BacktestMetrics


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


def compute_backtest_metrics(
    equity_curve: List[EquityPoint],
    trades: List[Trade],
    tf: str,
    initial_equity: float,
    bars_in_position: int = 0,
) -> BacktestMetrics:
    """
    Compute comprehensive backtest metrics.
    
    This is a pure function - no I/O operations.
    
    Args:
        equity_curve: List of EquityPoint objects (bar-by-bar equity)
        trades: List of Trade objects (completed trades only)
        tf: Timeframe string for annualization (e.g., "1h", "5m")
        initial_equity: Starting equity from risk profile
        bars_in_position: Number of bars with an open position (for time-in-market)
        
    Returns:
        BacktestMetrics with all computed fields
    """
    # Handle empty cases
    if not equity_curve:
        return BacktestMetrics(initial_equity=initial_equity)
    
    total_bars = len(equity_curve)
    
    # Basic equity metrics
    final_equity = equity_curve[-1].equity if equity_curve else initial_equity
    net_profit = final_equity - initial_equity
    net_return_pct = (net_profit / initial_equity * 100) if initial_equity > 0 else 0.0
    
    # Drawdown metrics
    max_dd_abs, max_dd_pct, max_dd_duration = _compute_drawdown_metrics(equity_curve)
    
    # Trade metrics
    total_trades = len(trades)
    win_count = sum(1 for t in trades if t.net_pnl > 0)
    loss_count = sum(1 for t in trades if t.net_pnl < 0)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
    
    # Gross profit/loss
    gross_profit = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    gross_loss = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    
    # Profit factor
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    elif gross_profit > 0:
        profit_factor = 100.0  # Cap at 100 if no losses
    else:
        profit_factor = 0.0
    
    # Average trade return %
    if total_trades > 0:
        avg_trade_return_pct = sum(t.pnl_pct for t in trades) / total_trades
    else:
        avg_trade_return_pct = 0.0
    
    # Total fees
    total_fees = sum(t.fees_paid for t in trades)
    
    # Risk-adjusted metrics
    sharpe = _compute_sharpe(equity_curve, tf)
    sortino = _compute_sortino(equity_curve, tf)
    calmar = _compute_calmar(net_return_pct, max_dd_pct, equity_curve, tf)
    
    # Extended trade analytics
    avg_win_usdt = (gross_profit / win_count) if win_count > 0 else 0.0
    avg_loss_usdt = (gross_loss / loss_count) if loss_count > 0 else 0.0
    
    largest_win_usdt = max((t.net_pnl for t in trades if t.net_pnl > 0), default=0.0)
    largest_loss_usdt = abs(min((t.net_pnl for t in trades if t.net_pnl < 0), default=0.0))
    
    # Average trade duration
    if total_trades > 0:
        avg_trade_duration_bars = sum(t.duration_bars for t in trades) / total_trades
    else:
        avg_trade_duration_bars = 0.0
    
    # Consecutive wins/losses
    max_consecutive_wins, max_consecutive_losses = _compute_consecutive_streaks(trades)
    
    # Expectancy (average PnL per trade)
    expectancy_usdt = (net_profit / total_trades) if total_trades > 0 else 0.0
    
    # Payoff ratio (avg win / avg loss)
    payoff_ratio = (avg_win_usdt / avg_loss_usdt) if avg_loss_usdt > 0 else 0.0
    
    # Recovery factor (net profit / max drawdown)
    recovery_factor = (net_profit / max_dd_abs) if max_dd_abs > 0 else 0.0
    
    # Long/short breakdown
    long_trades_list = [t for t in trades if t.side == "long"]
    short_trades_list = [t for t in trades if t.side == "short"]
    
    long_trades = len(long_trades_list)
    short_trades = len(short_trades_list)
    
    long_wins = sum(1 for t in long_trades_list if t.net_pnl > 0)
    short_wins = sum(1 for t in short_trades_list if t.net_pnl > 0)
    
    long_win_rate = (long_wins / long_trades * 100) if long_trades > 0 else 0.0
    short_win_rate = (short_wins / short_trades * 100) if short_trades > 0 else 0.0
    
    long_pnl = sum(t.net_pnl for t in long_trades_list)
    short_pnl = sum(t.net_pnl for t in short_trades_list)
    
    # Time in market
    time_in_market_pct = (bars_in_position / total_bars * 100) if total_bars > 0 else 0.0
    
    return BacktestMetrics(
        # Equity
        initial_equity=initial_equity,
        final_equity=round(final_equity, 2),
        net_profit=round(net_profit, 2),
        net_return_pct=round(net_return_pct, 2),
        # Drawdown
        max_drawdown_abs=round(max_dd_abs, 2),
        max_drawdown_pct=round(max_dd_pct, 2),
        max_drawdown_duration_bars=max_dd_duration,
        # Trade summary
        total_trades=total_trades,
        win_rate=round(win_rate, 2),
        avg_trade_return_pct=round(avg_trade_return_pct, 2),
        profit_factor=round(profit_factor, 2),
        # Risk-adjusted
        sharpe=round(sharpe, 2),
        sortino=round(sortino, 2),
        calmar=round(calmar, 2),
        # Trade counts
        win_count=win_count,
        loss_count=loss_count,
        gross_profit=round(gross_profit, 2),
        gross_loss=round(gross_loss, 2),
        total_fees=round(total_fees, 2),
        # Extended trade analytics
        avg_win_usdt=round(avg_win_usdt, 2),
        avg_loss_usdt=round(avg_loss_usdt, 2),
        largest_win_usdt=round(largest_win_usdt, 2),
        largest_loss_usdt=round(largest_loss_usdt, 2),
        avg_trade_duration_bars=round(avg_trade_duration_bars, 2),
        max_consecutive_wins=max_consecutive_wins,
        max_consecutive_losses=max_consecutive_losses,
        expectancy_usdt=round(expectancy_usdt, 2),
        payoff_ratio=round(payoff_ratio, 2),
        recovery_factor=round(recovery_factor, 2),
        # Long/short breakdown
        long_trades=long_trades,
        short_trades=short_trades,
        long_win_rate=round(long_win_rate, 2),
        short_win_rate=round(short_win_rate, 2),
        long_pnl=round(long_pnl, 2),
        short_pnl=round(short_pnl, 2),
        # Time metrics
        total_bars=total_bars,
        bars_in_position=bars_in_position,
        time_in_market_pct=round(time_in_market_pct, 2),
    )


def _compute_drawdown_metrics(
    equity_curve: List[EquityPoint],
) -> Tuple[float, float, int]:
    """
    Compute drawdown metrics from equity curve.
    
    Walks forward through equity, tracking peak and computing drawdowns.
    
    Returns:
        Tuple of (max_drawdown_abs, max_drawdown_pct, max_drawdown_duration_bars)
    """
    if not equity_curve:
        return 0.0, 0.0, 0
    
    peak = equity_curve[0].equity
    max_dd_abs = 0.0
    max_dd_pct = 0.0
    
    # Track duration
    current_dd_start = None
    current_dd_bars = 0
    max_dd_duration = 0
    
    for i, point in enumerate(equity_curve):
        equity = point.equity
        
        if equity > peak:
            # New peak - end current drawdown
            peak = equity
            if current_dd_start is not None:
                # Record duration of this drawdown
                if current_dd_bars > max_dd_duration:
                    max_dd_duration = current_dd_bars
                current_dd_start = None
                current_dd_bars = 0
        else:
            # In drawdown
            if current_dd_start is None:
                current_dd_start = i
            current_dd_bars = i - current_dd_start + 1
            
            dd_abs = peak - equity
            dd_pct = (dd_abs / peak * 100) if peak > 0 else 0.0
            
            if dd_abs > max_dd_abs:
                max_dd_abs = dd_abs
                max_dd_pct = dd_pct
    
    # Check if still in drawdown at end
    if current_dd_start is not None and current_dd_bars > max_dd_duration:
        max_dd_duration = current_dd_bars
    
    return max_dd_abs, max_dd_pct, max_dd_duration


def _compute_returns(equity_curve: List[EquityPoint]) -> List[float]:
    """Compute per-bar returns from equity curve."""
    if len(equity_curve) < 2:
        return []
    
    returns = []
    for i in range(1, len(equity_curve)):
        prev_equity = equity_curve[i - 1].equity
        curr_equity = equity_curve[i].equity
        
        if prev_equity > 0:
            ret = (curr_equity / prev_equity) - 1.0
            returns.append(ret)
    
    return returns


def _compute_sharpe(
    equity_curve: List[EquityPoint],
    tf: str,
    risk_free_rate: float = 0.0,
) -> float:
    """
    Compute annualized Sharpe ratio from per-bar equity returns.
    
    Uses simple returns: (equity_t / equity_{t-1}) - 1
    Annualizes using bars_per_year for the tf.
    RF = 0 by default.
    
    Args:
        equity_curve: List of EquityPoint objects
        tf: Timeframe for annualization
        risk_free_rate: Risk-free rate (default 0)
        
    Returns:
        Annualized Sharpe ratio (0 if insufficient data or zero volatility)
    """
    returns = _compute_returns(equity_curve)
    
    if len(returns) < 2:
        return 0.0
    
    # Mean and std of returns
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_return = math.sqrt(variance)
    
    if std_return == 0:
        return 0.0
    
    # Annualization factor
    bars_per_year = TF_BARS_PER_YEAR.get(tf, 8760)  # Default to 1h
    annualization = math.sqrt(bars_per_year)
    
    # Sharpe = (mean - rf) / std * sqrt(periods_per_year)
    sharpe = (mean_return - risk_free_rate) / std_return * annualization
    
    return sharpe


def _compute_sortino(
    equity_curve: List[EquityPoint],
    tf: str,
    risk_free_rate: float = 0.0,
) -> float:
    """
    Compute annualized Sortino ratio (uses downside deviation only).
    
    Similar to Sharpe but only penalizes downside volatility.
    
    Args:
        equity_curve: List of EquityPoint objects
        tf: Timeframe for annualization
        risk_free_rate: Risk-free rate (default 0)
        
    Returns:
        Annualized Sortino ratio (0 if insufficient data)
    """
    returns = _compute_returns(equity_curve)
    
    if len(returns) < 2:
        return 0.0
    
    mean_return = sum(returns) / len(returns)
    
    # Downside deviation: only negative returns
    negative_returns = [r for r in returns if r < 0]
    
    if not negative_returns:
        # No negative returns = infinite Sortino, cap at 100
        return 100.0 if mean_return > 0 else 0.0
    
    downside_variance = sum(r ** 2 for r in negative_returns) / len(returns)
    downside_std = math.sqrt(downside_variance)
    
    if downside_std == 0:
        return 0.0
    
    # Annualization
    bars_per_year = TF_BARS_PER_YEAR.get(tf, 8760)
    annualization = math.sqrt(bars_per_year)
    
    sortino = (mean_return - risk_free_rate) / downside_std * annualization
    
    return sortino


def _compute_calmar(
    net_return_pct: float,
    max_dd_pct: float,
    equity_curve: List[EquityPoint],
    tf: str,
) -> float:
    """
    Compute Calmar ratio (annualized return / max drawdown).
    
    Args:
        net_return_pct: Net return as percentage
        max_dd_pct: Max drawdown as percentage
        equity_curve: For computing time period
        tf: Timeframe for annualization
        
    Returns:
        Calmar ratio (0 if no drawdown)
    """
    if max_dd_pct == 0:
        return 0.0
    
    # Annualize the return
    bars_per_year = TF_BARS_PER_YEAR.get(tf, 8760)
    total_bars = len(equity_curve)
    
    if total_bars == 0:
        return 0.0
    
    # Periods in this backtest
    years = total_bars / bars_per_year
    
    if years == 0:
        return 0.0
    
    # Annualized return
    annualized_return_pct = net_return_pct / years
    
    # Calmar = annualized return / max drawdown
    calmar = annualized_return_pct / max_dd_pct
    
    return calmar


def _compute_consecutive_streaks(trades: List[Trade]) -> Tuple[int, int]:
    """
    Compute max consecutive wins and losses.
    
    Returns:
        Tuple of (max_consecutive_wins, max_consecutive_losses)
    """
    if not trades:
        return 0, 0
    
    max_wins = 0
    max_losses = 0
    current_wins = 0
    current_losses = 0
    
    for trade in trades:
        if trade.net_pnl > 0:
            current_wins += 1
            current_losses = 0
            if current_wins > max_wins:
                max_wins = current_wins
        elif trade.net_pnl < 0:
            current_losses += 1
            current_wins = 0
            if current_losses > max_losses:
                max_losses = current_losses
        else:
            # Breakeven trade - reset both
            current_wins = 0
            current_losses = 0
    
    return max_wins, max_losses
