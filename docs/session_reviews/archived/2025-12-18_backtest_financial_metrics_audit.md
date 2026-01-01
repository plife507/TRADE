# Backtest Financial Metrics & Audit Review

**Date**: December 18, 2025  
**Objective**: Document the mathematical logic and implementation details for backtest financial reporting.  
**Status**: ✅ COMPLETE

---

## 1. Overview

The TRADE backtest engine uses a standardized metrics collection system that ensures consistency between the simulated exchange (`src/backtest/sim/`) and the final results reporting (`src/backtest/artifacts/`). All core performance calculations are centralized in `src/backtest/metrics.py`.

---

## 2. Core Performance Metrics

These metrics represent the raw PnL and account growth of the strategy.

| Metric | Formula | Implementation Logic |
| :--- | :--- | :--- |
| **Net Profit** | $FinalEquity - InitialEquity$ | Simple absolute USDT change. |
| **Net Return %** | $(NetProfit / InitialEquity) * 100$ | Percentage gain/loss on starting capital. |
| **Win Rate** | $(WinCount / TotalTrades) * 100$ | Percentage of trades with `net_pnl > 0`. |
| **Total Fees** | $\sum(EntryFees + ExitFees)$ | Total cost paid for execution. |

### Code Example:
```python
# From src/backtest/metrics.py
final_equity = equity_curve[-1].equity if equity_curve else initial_equity
net_profit = final_equity - initial_equity
net_return_pct = (net_profit / initial_equity * 100) if initial_equity > 0 else 0.0
```

---

## 3. Drawdown & Risk

Drawdown measures the "pain" of the strategy by tracking declines from previous peaks.

### Max Drawdown (MDD)
- **Logic**: The engine walks the equity curve bar-by-bar, updating the `peak` whenever a new high is hit. 
- **Drawdown Calculation**: Whenever equity is below the peak, $DD = Peak - Current$.
- **Max DD**: The largest observed $DD$ (both in absolute USDT and percentage).

### Code Example:
```python
# From src/backtest/metrics.py (_compute_drawdown_metrics)
peak = equity_curve[0].equity
max_dd_abs = 0.0
max_dd_pct = 0.0

for point in equity_curve:
    equity = point.equity
    if equity > peak:
        peak = equity
    else:
        dd_abs = peak - equity
        dd_pct = (dd_abs / peak * 100) if peak > 0 else 0.0
        if dd_abs > max_dd_abs:
            max_dd_abs, max_dd_pct = dd_abs, dd_pct
```

---

## 4. Risk-Adjusted Metrics

Used to normalize returns against the risk or volatility required to achieve them.

### Sharpe Ratio (Annualized)
- **Definition**: Reward per unit of total risk (standard deviation of returns).
- **Annualization**: Multiplied by $\sqrt{BarsPerYear}$ (e.g., $\sqrt{105,120}$ for 5m).

### Sortino Ratio (Annualized)
- **Definition**: Reward per unit of **downside** risk only.
- **Logic**: Only returns below zero are used in the denominator (the downside deviation).

### Calmar Ratio
- **Definition**: Annualized return divided by maximum percentage drawdown.

### Code Example:
```python
# Annualization Factor logic
bars_per_year = TF_BARS_PER_YEAR.get(tf, 8760) 
annualization = math.sqrt(bars_per_year)

# Sharpe = (mean_return / std_return) * annualization
sharpe = (mean_return / std_return) * annualization
```

---

## 5. Trade Analytics

Detailed metrics for evaluating the "behavior" of the strategy.

| Metric | Formula | Logic |
| :--- | :--- | :--- |
| **Expectancy** | $NetProfit / TotalTrades$ | Average dollar amount expected per trade. |
| **Profit Factor** | $\sum GrossProfits / \sum |GrossLosses|$ | Efficiency of winning trades vs losing trades. |
| **Payoff Ratio** | $AvgWinUSDT / AvgLossUSDT$ | Reward-to-Risk realization. |
| **Recovery Factor**| $NetProfit / MaxDrawdownAbs$ | How many times the profit "covered" the max loss. |

### Code Example:
```python
# Expectancy implementation
expectancy_usdt = (net_profit / total_trades) if total_trades > 0 else 0.0

# Payoff Ratio implementation
payoff_ratio = (avg_win_usdt / avg_loss_usdt) if avg_loss_usdt > 0 else 0.0
```

---

## 6. Time & Exposure Metrics

| Metric | Formula | Logic |
| :--- | :--- | :--- |
| **Time in Market %** | $(BarsInPosition / TotalBars) * 100$ | Percentage of time holding a position. |
| **Avg Duration** | $\sum(ExitIdx - EntryIdx) / Trades$ | Mean holding period in bars. |

---

## 7. Conclusions & Audit Trail

- ✅ **Mathematical Parity**: All metrics are calculated from a single source of truth (`BacktestMetrics`).
- ✅ **Deterministic**: Identical trade/equity inputs always yield identical financial results.
- ✅ **Bybit Alignment**: Fee and PnL calculations match Bybit USDT-margin semantics.

**Reviewer**: Claude (AI Assistant)  
**Status**: Verified implementation in `src/backtest/metrics.py`

