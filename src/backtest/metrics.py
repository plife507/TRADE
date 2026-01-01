"""
Backtest metrics calculation.

Pure math functions for computing backtest performance metrics.
No I/O operations - takes data and returns computed values.

Main function: compute_backtest_metrics() -> BacktestMetrics

Metric Definitions (Canonical):
-------------------------------
- Equity (MTM): cash_balance_usdt + unrealized_pnl_usdt
- Per-bar return: r_t = (E_t / E_{t-1}) - 1 (simple return)
- Drawdown (absolute): dd_abs = peak_equity - current_equity
- Drawdown (percent): dd_pct = dd_abs / peak_equity (DECIMAL, not 0-100)
- CAGR: (E_final / E_initial)^(1/years) - 1, where years = bars / bars_per_year
- Calmar: CAGR / max_dd_decimal
- Funding: periodic cashflow at funding event timestamps

UNIT RULE (HARD):
- Store decimals internally (0.25 = 25%)
- Convert to % only for display (multiply by 100)
"""

import math
import warnings
from typing import List, Tuple, Optional

from .types import Trade, EquityPoint, BacktestMetrics


# =============================================================================
# Timeframe Normalization and Bars Per Year
# =============================================================================

# Timeframe to approximate bars per year (crypto markets ~365 days)
# Extended to support all common timeframes
TF_BARS_PER_YEAR = {
    # Minutes
    "1m": 365 * 24 * 60,      # 525,600
    "3m": 365 * 24 * 20,      # 175,200
    "5m": 365 * 24 * 12,      # 105,120
    "15m": 365 * 24 * 4,      # 35,040
    "30m": 365 * 24 * 2,      # 17,520
    # Hours
    "1h": 365 * 24,           # 8,760
    "2h": 365 * 12,           # 4,380
    "4h": 365 * 6,            # 2,190
    "6h": 365 * 4,            # 1,460
    "8h": 365 * 3,            # 1,095
    "12h": 365 * 2,           # 730
    # Days/Weeks/Months
    "1d": 365,                # 365
    "1D": 365,                # 365 (uppercase variant)
    "D": 365,                 # 365 (Bybit format)
    "1w": 52,                 # 52
    "1W": 52,                 # 52 (uppercase variant)
    "W": 52,                  # 52 (Bybit format)
    "1M": 12,                 # 12
    "M": 12,                  # 12 (Bybit format)
}


def normalize_tf_string(tf: str) -> str:
    """
    Normalize timeframe string to canonical format.
    
    Handles common variations:
    - "60" -> "1h" (Bybit API format)
    - "240" -> "4h"
    - "D" -> "1d"
    
    Args:
        tf: Timeframe string in any format
        
    Returns:
        Normalized timeframe string (e.g., "1h", "4h", "1d")
    """
    # Handle Bybit numeric formats (minutes)
    tf_numeric_map = {
        "1": "1m",
        "3": "3m",
        "5": "5m",
        "15": "15m",
        "30": "30m",
        "60": "1h",
        "120": "2h",
        "240": "4h",
        "360": "6h",
        "480": "8h",
        "720": "12h",
    }
    if tf in tf_numeric_map:
        return tf_numeric_map[tf]
    
    # Handle uppercase variants
    tf_upper_map = {
        "1D": "1d",
        "D": "1d",
        "1W": "1w",
        "W": "1w",
        "1M": "1M",  # Keep month as-is
        "M": "1M",
    }
    if tf in tf_upper_map:
        return tf_upper_map[tf]
    
    # Already normalized or unknown
    return tf


def get_bars_per_year(tf: str, strict: bool = True) -> int:
    """
    Get the number of bars per year for a given timeframe.
    
    Args:
        tf: Timeframe string (e.g., "1h", "5m", "1d")
        strict: If True, raise ValueError for unknown TF.
                If False, warn and use 1h default (8760).
    
    Returns:
        Number of bars per year
        
    Raises:
        ValueError: If strict=True and TF is not recognized
    """
    normalized = normalize_tf_string(tf)
    
    if normalized in TF_BARS_PER_YEAR:
        return TF_BARS_PER_YEAR[normalized]
    
    if strict:
        raise ValueError(
            f"Unknown timeframe '{tf}' (normalized: '{normalized}'). "
            f"Supported timeframes: {sorted(TF_BARS_PER_YEAR.keys())}. "
            "Cannot compute annualized metrics without known TF."
        )
    
    # Non-strict mode: warn and use default
    warnings.warn(
        f"Unknown timeframe '{tf}', using 1h default (8760 bars/year). "
        f"This may produce incorrect annualized metrics.",
        UserWarning
    )
    return 8760  # 1h default


def compute_backtest_metrics(
    equity_curve: List[EquityPoint],
    trades: List[Trade],
    tf: str,
    initial_equity: float,
    bars_in_position: int = 0,
    total_funding_paid_usdt: float = 0.0,
    total_funding_received_usdt: float = 0.0,
    strict_tf: bool = True,
    # Entry friction metrics (from exchange)
    entry_attempts: int = 0,
    entry_rejections: int = 0,
    # Margin stress metrics (from exchange)
    min_margin_ratio: float = 1.0,
    margin_calls: int = 0,
    # Liquidation proximity (from exchange)
    closest_liquidation_pct: float = 100.0,
    # Benchmark comparison (from exec_feed first/last close)
    first_price: float = 0.0,
    last_price: float = 0.0,
    # Leverage metrics (from engine account_curve)
    avg_leverage_used: float = 0.0,
    max_gross_exposure_pct: float = 0.0,
    # Trade quality MAE/MFE (from trades)
    mae_avg_pct: float = 0.0,
    mfe_avg_pct: float = 0.0,
) -> BacktestMetrics:
    """
    Compute comprehensive backtest metrics.

    This is a pure function - no I/O operations.

    **CRITICAL FIXES (Dec 2025)**:
    - max_drawdown_pct tracked independently from max_drawdown_abs
    - Calmar uses geometric CAGR, not arithmetic annualized return
    - TF validation is strict by default (raises on unknown TF)
    - expectancy_usdt uses realized trade PnL, not MTM equity delta
    - Funding tracked separately from trading fees

    **LEVERAGED TRADING METRICS**:
    - ulcer_index, profit_factor_mode for risk analysis
    - Entry friction: entry_attempts, entry_rejections (margin-based rejections)
    - Margin stress: min_margin_ratio, margin_calls
    - Liquidation proximity: closest_liquidation_pct

    Args:
        equity_curve: List of EquityPoint objects (bar-by-bar equity)
        trades: List of Trade objects (completed trades only)
        tf: Timeframe string for annualization (e.g., "1h", "5m")
        initial_equity: Starting equity from risk profile
        bars_in_position: Number of bars with an open position (for time-in-market)
        total_funding_paid_usdt: Total funding paid (positive = outflow)
        total_funding_received_usdt: Total funding received (positive = inflow)
        strict_tf: If True, raise on unknown TF. If False, warn and use default.
        entry_attempts: Total entry signal attempts
        entry_rejections: Entries rejected (margin, size, etc.)
        min_margin_ratio: Lowest margin ratio during backtest
        margin_calls: Number of margin warning events
        closest_liquidation_pct: Closest approach to liquidation (100 = never close)
        first_price: First bar close price (for benchmark calculation)
        last_price: Last bar close price (for benchmark calculation)
        avg_leverage_used: Average leverage from account_curve
        max_gross_exposure_pct: Peak position_value / equity * 100
        mae_avg_pct: Average Maximum Adverse Excursion per trade
        mfe_avg_pct: Average Maximum Favorable Excursion per trade

    Returns:
        BacktestMetrics with all computed fields

    Raises:
        ValueError: If strict_tf=True and tf is not recognized
    """
    # Handle empty cases
    if not equity_curve:
        return BacktestMetrics(initial_equity=initial_equity)
    
    total_bars = len(equity_curve)
    
    # Basic equity metrics
    final_equity = equity_curve[-1].equity if equity_curve else initial_equity
    net_profit = final_equity - initial_equity
    net_return_pct = (net_profit / initial_equity * 100) if initial_equity > 0 else 0.0

    # Benchmark comparison: Buy-and-hold return over same period
    if first_price > 0:
        benchmark_return_pct = ((last_price - first_price) / first_price) * 100
    else:
        benchmark_return_pct = 0.0
    alpha_pct = net_return_pct - benchmark_return_pct

    # Drawdown metrics
    # NOTE: max_dd_pct is now DECIMAL (0.10 = 10%), convert for display later
    max_dd_abs, max_dd_pct_decimal, max_dd_duration = _compute_drawdown_metrics(equity_curve)

    # Convert to percentage for display (0.10 -> 10.0)
    max_dd_pct_display = max_dd_pct_decimal * 100

    # Ulcer index: sqrt(mean of squared drawdown percentages)
    # Measures the depth and duration of drawdowns
    ulcer_index = _compute_ulcer_index(equity_curve)

    # Entry rejection rate
    entry_rejection_rate = (
        (entry_rejections / entry_attempts) if entry_attempts > 0 else 0.0
    )
    
    # Trade metrics
    total_trades = len(trades)
    win_count = sum(1 for t in trades if t.net_pnl > 0)
    loss_count = sum(1 for t in trades if t.net_pnl < 0)
    win_rate = (win_count / total_trades * 100) if total_trades > 0 else 0.0
    
    # Gross profit/loss
    gross_profit = sum(t.net_pnl for t in trades if t.net_pnl > 0)
    gross_loss = abs(sum(t.net_pnl for t in trades if t.net_pnl < 0))
    
    # Profit factor with mode for edge cases
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
        profit_factor_mode = "finite"
    elif gross_profit > 0:
        profit_factor = 100.0  # Cap at 100 if no losses
        profit_factor_mode = "infinite"  # Actually infinite, capped for display
    else:
        profit_factor = 0.0
        profit_factor_mode = "undefined"  # No profit, no loss
    
    # Average trade return %
    if total_trades > 0:
        avg_trade_return_pct = sum(t.pnl_pct for t in trades) / total_trades
    else:
        avg_trade_return_pct = 0.0
    
    # Total trading fees (excludes funding)
    total_fees = sum(t.fees_paid for t in trades)
    
    # Risk-adjusted metrics
    sharpe = _compute_sharpe(equity_curve, tf, strict_tf=strict_tf)
    sortino = _compute_sortino(equity_curve, tf, strict_tf=strict_tf)
    
    # Calmar uses CAGR and DECIMAL max_dd_pct
    calmar = _compute_calmar(
        initial_equity=initial_equity,
        final_equity=final_equity,
        max_dd_pct_decimal=max_dd_pct_decimal,
        total_bars=total_bars,
        tf=tf,
        strict_tf=strict_tf,
    )
    
    # Extended trade analytics
    avg_win_usdt = (gross_profit / win_count) if win_count > 0 else 0.0
    avg_loss_usdt = (gross_loss / loss_count) if loss_count > 0 else 0.0
    
    largest_win_usdt = max((t.net_pnl for t in trades if t.net_pnl > 0), default=0.0)
    largest_loss_usdt = abs(min((t.net_pnl for t in trades if t.net_pnl < 0), default=0.0))
    
    # Average trade duration (handle None values for open trades)
    trade_durations = [t.duration_bars for t in trades if t.duration_bars is not None]
    if trade_durations:
        avg_trade_duration_bars = sum(trade_durations) / len(trade_durations)
    else:
        avg_trade_duration_bars = 0.0

    # Duration breakdown by win/loss
    winning_durations = [t.duration_bars for t in trades if t.duration_bars is not None and t.net_pnl > 0]
    losing_durations = [t.duration_bars for t in trades if t.duration_bars is not None and t.net_pnl < 0]
    avg_winning_trade_duration_bars = sum(winning_durations) / len(winning_durations) if winning_durations else 0.0
    avg_losing_trade_duration_bars = sum(losing_durations) / len(losing_durations) if losing_durations else 0.0

    # Consecutive wins/losses
    max_consecutive_wins, max_consecutive_losses = _compute_consecutive_streaks(trades)
    
    # Expectancy: average REALIZED PnL per trade (not MTM equity delta)
    # This uses trade.net_pnl which is realized_pnl - fees for closed trades
    if total_trades > 0:
        expectancy_usdt = sum(t.net_pnl for t in trades) / total_trades
    else:
        expectancy_usdt = 0.0
    
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

    # Funding totals
    net_funding = total_funding_received_usdt - total_funding_paid_usdt

    # Tail risk metrics (skewness, kurtosis, VaR, CVaR)
    skewness, kurtosis, var_95_pct, cvar_95_pct = _compute_tail_risk(equity_curve)

    # Omega ratio (probability-weighted gain/loss, threshold=0)
    omega_ratio = _compute_omega(equity_curve)

    return BacktestMetrics(
        # Equity
        initial_equity=initial_equity,
        final_equity=round(final_equity, 2),
        net_profit=round(net_profit, 2),
        net_return_pct=round(net_return_pct, 2),
        benchmark_return_pct=round(benchmark_return_pct, 2),
        alpha_pct=round(alpha_pct, 2),
        # Drawdown (display as percentage, stored as % not decimal)
        max_drawdown_abs=round(max_dd_abs, 2),
        max_drawdown_pct=round(max_dd_pct_display, 2),  # Now in % (10.0 = 10%)
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
        avg_winning_trade_duration_bars=round(avg_winning_trade_duration_bars, 2),
        avg_losing_trade_duration_bars=round(avg_losing_trade_duration_bars, 2),
        max_consecutive_wins=max_consecutive_wins,
        max_consecutive_losses=max_consecutive_losses,
        expectancy_usdt=round(expectancy_usdt, 2),
        payoff_ratio=round(payoff_ratio, 2),
        recovery_factor=round(recovery_factor, 2),
        omega_ratio=round(omega_ratio, 2),
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
        # Funding metrics
        total_funding_paid_usdt=round(total_funding_paid_usdt, 2),
        total_funding_received_usdt=round(total_funding_received_usdt, 2),
        net_funding_usdt=round(net_funding, 2),
        # Extended drawdown
        ulcer_index=round(ulcer_index, 4),
        # Profit factor mode
        profit_factor_mode=profit_factor_mode,
        # Entry friction (leveraged trading)
        entry_attempts=entry_attempts,
        entry_rejections=entry_rejections,
        entry_rejection_rate=round(entry_rejection_rate, 4),
        # Margin stress (leveraged trading)
        min_margin_ratio=round(min_margin_ratio, 4),
        margin_calls=margin_calls,
        # Liquidation proximity (leveraged trading)
        closest_liquidation_pct=round(closest_liquidation_pct, 2),
        # Tail risk metrics
        skewness=skewness,
        kurtosis=kurtosis,
        var_95_pct=var_95_pct,
        cvar_95_pct=cvar_95_pct,
        # Leverage metrics (passed from engine)
        avg_leverage_used=round(avg_leverage_used, 2),
        max_gross_exposure_pct=round(max_gross_exposure_pct, 2),
        # Trade quality MAE/MFE (passed from engine)
        mae_avg_pct=round(mae_avg_pct, 2),
        mfe_avg_pct=round(mfe_avg_pct, 2),
    )


def _compute_drawdown_metrics(
    equity_curve: List[EquityPoint],
) -> Tuple[float, float, int]:
    """
    Compute drawdown metrics from equity curve.
    
    Walks forward through equity, tracking peak and computing drawdowns.
    
    **CRITICAL FIX (Dec 2025)**: max_dd_abs and max_dd_pct are tracked INDEPENDENTLY.
    The max absolute drawdown and max percentage drawdown may occur at different peaks.
    
    Example:
        - Peak 10 → equity 1: dd_abs=9, dd_pct=0.90
        - Peak 1000 → equity 900: dd_abs=100, dd_pct=0.10
        - Result: max_dd_abs=100, max_dd_pct=0.90 (independent maxima)
    
    Definitions:
        - dd_abs = peak_equity - current_equity (in USDT)
        - dd_pct = dd_abs / peak_equity (decimal, NOT percentage; 0.10 = 10%)
    
    Returns:
        Tuple of (max_drawdown_abs, max_drawdown_pct_decimal, max_drawdown_duration_bars)
        
    Raises:
        ValueError: If peak_equity <= 0 (should never happen in valid simulation)
    """
    if not equity_curve:
        return 0.0, 0.0, 0
    
    peak = equity_curve[0].equity
    max_dd_abs = 0.0
    max_dd_pct = 0.0  # Decimal (0.10 = 10%), NOT percentage
    
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
            
            # Guard: peak should never be <= 0 in valid simulation
            if peak <= 0:
                raise ValueError(
                    f"Invalid peak_equity={peak} at bar {i}. "
                    "Equity should never reach zero or negative in valid simulation."
                )
            
            dd_pct = dd_abs / peak  # Decimal (0.10 = 10%)
            
            # CRITICAL: Track maxima INDEPENDENTLY
            # The max absolute drawdown and max percentage drawdown may occur at different peaks
            if dd_abs > max_dd_abs:
                max_dd_abs = dd_abs
            if dd_pct > max_dd_pct:
                max_dd_pct = dd_pct
    
    # Check if still in drawdown at end
    if current_dd_start is not None and current_dd_bars > max_dd_duration:
        max_dd_duration = current_dd_bars
    
    return max_dd_abs, max_dd_pct, max_dd_duration


def _compute_ulcer_index(equity_curve: List[EquityPoint]) -> float:
    """
    Compute ulcer index from equity curve.

    Ulcer index = sqrt(mean of squared drawdown percentages)
    Measures the depth and duration of drawdowns.
    Lower is better (0 = no drawdowns).

    Returns:
        Ulcer index value (0.0 if no equity curve)
    """
    if not equity_curve:
        return 0.0

    peak = equity_curve[0].equity
    dd_pcts_squared = []

    for point in equity_curve:
        equity = point.equity

        if equity > peak:
            peak = equity
            dd_pcts_squared.append(0.0)
        else:
            dd_pct = ((peak - equity) / peak * 100) if peak > 0 else 0.0
            dd_pcts_squared.append(dd_pct ** 2)

    if dd_pcts_squared:
        return math.sqrt(sum(dd_pcts_squared) / len(dd_pcts_squared))
    return 0.0


def _compute_tail_risk(
    equity_curve: List[EquityPoint],
) -> Tuple[float, float, float, float]:
    """
    Compute tail risk metrics from equity curve.

    Returns:
        Tuple of (skewness, kurtosis, var_95_pct, cvar_95_pct)
        - skewness: 0 = symmetric, negative = left skew (blowup risk)
        - kurtosis: 3 = normal, >3 = fat tails
        - var_95_pct: 95th percentile loss (worst 5% of returns)
        - cvar_95_pct: Expected shortfall (avg of worst 5%)
    """
    returns = _compute_returns_for_tail_risk(equity_curve)

    if len(returns) < 10:  # Need enough data for meaningful stats
        return 0.0, 0.0, 0.0, 0.0

    n = len(returns)
    mean_r = sum(returns) / n

    # Variance, skewness, kurtosis
    m2 = sum((r - mean_r) ** 2 for r in returns) / n  # variance
    m3 = sum((r - mean_r) ** 3 for r in returns) / n  # 3rd moment
    m4 = sum((r - mean_r) ** 4 for r in returns) / n  # 4th moment

    std_r = math.sqrt(m2) if m2 > 0 else 0.0

    if std_r > 0:
        skewness = m3 / (std_r ** 3)
        kurtosis = m4 / (std_r ** 4)  # Excess kurtosis would subtract 3
    else:
        skewness = 0.0
        kurtosis = 0.0

    # VaR and CVaR (as percentages)
    sorted_returns = sorted(returns)
    var_idx = int(n * 0.05)  # Worst 5%
    var_idx = max(1, var_idx)  # At least 1

    # VaR: 5th percentile return (negative = loss)
    var_95 = sorted_returns[var_idx - 1]
    var_95_pct = abs(var_95) * 100  # Convert to positive percentage

    # CVaR: Average of returns worse than VaR
    worst_returns = sorted_returns[:var_idx]
    cvar_95 = sum(worst_returns) / len(worst_returns) if worst_returns else 0.0
    cvar_95_pct = abs(cvar_95) * 100  # Convert to positive percentage

    return round(skewness, 4), round(kurtosis, 4), round(var_95_pct, 4), round(cvar_95_pct, 4)


def _compute_returns_for_tail_risk(equity_curve: List[EquityPoint]) -> List[float]:
    """Compute per-bar returns from equity curve (for tail risk)."""
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
    strict_tf: bool = True,
) -> float:
    """
    Compute annualized Sharpe ratio from per-bar equity returns.
    
    Formula:
        returns: r_t = (E_t / E_{t-1}) - 1 (simple per-bar return)
        Sharpe = (mean(returns) - rf) / std(returns) * sqrt(bars_per_year)
    
    Args:
        equity_curve: List of EquityPoint objects
        tf: Timeframe for annualization
        risk_free_rate: Risk-free rate as decimal (default 0)
        strict_tf: If True, raise on unknown TF
        
    Returns:
        Annualized Sharpe ratio
        - Returns 0.0 if len(equity_curve) < 2
        - Returns 0.0 if std(returns) == 0 (no volatility = undefined)
    """
    returns = _compute_returns(equity_curve)
    
    if len(returns) < 2:
        return 0.0
    
    # Mean and std of returns
    mean_return = sum(returns) / len(returns)
    variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
    std_return = math.sqrt(variance)
    
    if std_return == 0:
        # No volatility - Sharpe is undefined, return 0
        return 0.0
    
    # Annualization factor
    bars_per_year = get_bars_per_year(tf, strict=strict_tf)
    annualization = math.sqrt(bars_per_year)
    
    # Sharpe = (mean - rf) / std * sqrt(periods_per_year)
    sharpe = (mean_return - risk_free_rate) / std_return * annualization
    
    return sharpe


def _compute_sortino(
    equity_curve: List[EquityPoint],
    tf: str,
    risk_free_rate: float = 0.0,
    strict_tf: bool = True,
) -> float:
    """
    Compute annualized Sortino ratio (uses downside deviation only).
    
    Similar to Sharpe but only penalizes downside volatility.
    
    Formula:
        Sortino = (mean(returns) - rf) / downside_std * sqrt(bars_per_year)
        where downside_std = sqrt(sum(min(r,0)^2) / n)
    
    Args:
        equity_curve: List of EquityPoint objects
        tf: Timeframe for annualization
        risk_free_rate: Risk-free rate as decimal (default 0)
        strict_tf: If True, raise on unknown TF
        
    Returns:
        Annualized Sortino ratio
        - Returns 0.0 if len(equity_curve) < 2
        - Returns 100.0 (capped) if no negative returns and positive mean
        - Returns 0.0 if downside_std == 0
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
    bars_per_year = get_bars_per_year(tf, strict=strict_tf)
    annualization = math.sqrt(bars_per_year)
    
    sortino = (mean_return - risk_free_rate) / downside_std * annualization
    
    return sortino


def _compute_cagr(
    initial_equity: float,
    final_equity: float,
    total_bars: int,
    bars_per_year: int,
) -> float:
    """
    Compute Compound Annual Growth Rate (CAGR).
    
    Formula: CAGR = (E_final / E_initial)^(1/years) - 1
    where years = total_bars / bars_per_year
    
    Args:
        initial_equity: Starting equity (E_initial)
        final_equity: Ending equity (E_final)
        total_bars: Number of bars in the simulation
        bars_per_year: Bars per year for the timeframe
        
    Returns:
        CAGR as decimal (0.21 = 21% annual growth)
        Returns 0.0 if inputs are invalid
    """
    if initial_equity <= 0 or total_bars <= 0 or bars_per_year <= 0:
        return 0.0
    
    years = total_bars / bars_per_year
    
    if years <= 0:
        return 0.0
    
    if final_equity <= 0:
        # Total loss scenario - return -1.0 (100% loss)
        return -1.0
    
    # Geometric CAGR formula
    # CAGR = (E_final / E_initial)^(1/years) - 1
    try:
        cagr = (final_equity / initial_equity) ** (1 / years) - 1
    except (ValueError, OverflowError):
        return 0.0
    
    return cagr


def _compute_calmar(
    initial_equity: float,
    final_equity: float,
    max_dd_pct_decimal: float,
    total_bars: int,
    tf: str,
    strict_tf: bool = True,
) -> float:
    """
    Compute Calmar ratio (CAGR / max drawdown).
    
    **FIXED (Dec 2025)**: Uses geometric CAGR, not arithmetic annualized return.
    
    Formula: Calmar = CAGR / max_dd_decimal
    
    Args:
        initial_equity: Starting equity
        final_equity: Ending equity
        max_dd_pct_decimal: Max drawdown as DECIMAL (0.10 = 10%)
        total_bars: Number of bars in the simulation
        tf: Timeframe for annualization
        strict_tf: If True, raise on unknown TF
        
    Returns:
        Calmar ratio (0.0 if no drawdown or invalid inputs)
        
    Note:
        - max_dd_pct_decimal MUST be decimal (0.10), not percentage (10.0)
        - Returns inf-capped at 100.0 if no drawdown but positive return
    """
    if max_dd_pct_decimal == 0:
        # No drawdown - infinite Calmar, cap at 100
        cagr = _compute_cagr(
            initial_equity, final_equity, total_bars,
            get_bars_per_year(tf, strict=strict_tf)
        )
        return 100.0 if cagr > 0 else 0.0
    
    if max_dd_pct_decimal < 0:
        # Invalid negative drawdown
        return 0.0
    
    bars_per_year = get_bars_per_year(tf, strict=strict_tf)
    
    if total_bars == 0:
        return 0.0
    
    # Compute CAGR
    cagr = _compute_cagr(initial_equity, final_equity, total_bars, bars_per_year)
    
    if cagr == 0:
        return 0.0
    
    # Calmar = CAGR / max_dd_decimal
    # Note: both CAGR and max_dd are in decimal form
    calmar = cagr / max_dd_pct_decimal
    
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


def _compute_omega(
    equity_curve: List[EquityPoint],
    threshold: float = 0.0,
) -> float:
    """
    Compute Omega ratio (probability-weighted gain/loss).

    Formula: Omega = sum(gains above threshold) / |sum(losses below threshold)|

    Args:
        equity_curve: List of EquityPoint objects
        threshold: Minimum return threshold (default 0 = risk-free rate)

    Returns:
        Omega ratio. Returns 0.0 if insufficient data.
        Returns 100.0 (capped) if no losses.
    """
    returns = _compute_returns(equity_curve)

    if len(returns) < 2:
        return 0.0

    gains = sum(r - threshold for r in returns if r > threshold)
    losses = abs(sum(r - threshold for r in returns if r < threshold))

    if losses == 0:
        return 100.0 if gains > 0 else 0.0

    return gains / losses
