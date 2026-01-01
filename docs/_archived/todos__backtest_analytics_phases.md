# Backtest Analytics Implementation

**Status**: Phases 1-3 ✅ COMPLETE; Phases 4-6 📋 PENDING (Future Work)  
**Created**: 2025-12-14  
**Updated**: 2025-12-17 (governance cleanup)  
**Goal**: Comprehensive backtest analytics with all industry-standard metrics

## Current State

**Completed (Phases 1-3)**:
- All core analytics implemented and persisted to `result.json`
- Risk-adjusted metrics: Sharpe, Sortino, Calmar, Recovery Factor
- Detailed trade statistics: win/loss sizes, durations, consecutive runs, expectancy, payoff ratio
- Long/short breakdown, time in market, total fees
- Basic CLI display

**Pending (Phases 4-6)** — Future enhancements, not blocking:
- Time-based analytics (daily/weekly/monthly returns)
- Benchmark comparison (buy-and-hold, alpha, beta)
- Enhanced CLI display (color-coded, compare runs)

---

## Phase 1: Wire Existing Metrics to Output ✅

**Goal**: Ensure all computed metrics appear in `result.json`

- [x] 1.1 Update `result.json` writer to include all `BacktestMetrics` fields
- [x] 1.2 Add Sharpe to CLI output summary
- [x] 1.3 Add profit factor to CLI output summary

**Acceptance**: `result.json` contains all fields from `BacktestMetrics.to_dict()` ✅

---

## Phase 2: Additional Risk-Adjusted Metrics ✅

**Goal**: Add Sortino, Calmar, and other risk-adjusted ratios

- [x] 2.1 Sortino ratio (downside deviation only)
- [x] 2.2 Calmar ratio (return / max drawdown)
- [x] 2.3 Recovery factor (net profit / max drawdown)
- [ ] 2.4 Ulcer index (RMS of drawdown) - deferred
- [x] 2.5 Add to `BacktestMetrics` dataclass
- [x] 2.6 Add to result.json output

**Acceptance**: All ratios computed and persisted ✅

---

## Phase 3: Trade Statistics ✅

**Goal**: Detailed trade-level analytics

- [x] 3.1 Average win size (USDT and %)
- [x] 3.2 Average loss size (USDT and %)
- [x] 3.3 Largest win / largest loss
- [x] 3.4 Average trade duration (bars)
- [x] 3.5 Max consecutive wins / losses
- [x] 3.6 Expectancy (avg PnL per trade)
- [x] 3.7 Payoff ratio (avg win / avg loss)
- [x] 3.8 Long vs short breakdown (count, win rate, PnL)
- [x] 3.9 Time in market (% of bars with position)
- [x] 3.10 Total fees

**Acceptance**: All trade stats in result.json ✅

---

## Phase 4: Time-Based Analytics [ ] (Future)

**Goal**: Returns broken down by time period

- [ ] 4.1 Daily returns series
- [ ] 4.2 Weekly returns series
- [ ] 4.3 Monthly returns series
- [ ] 4.4 Best/worst day/week/month
- [ ] 4.5 Output to separate `returns.json` artifact

**Acceptance**: Time-based returns available for charting

---

## Phase 5: Benchmark Comparison [ ] (Future)

**Goal**: Compare strategy to buy-and-hold

- [ ] 5.1 Buy-and-hold return for same period
- [ ] 5.2 Alpha (strategy return - benchmark return)
- [ ] 5.3 Beta (correlation to benchmark)
- [ ] 5.4 Information ratio

**Acceptance**: Benchmark metrics in result.json

---

## Phase 6: CLI Analytics Display ✅ (Partial)

**Goal**: Rich CLI output with full analytics

- [x] 6.1 Formatted metrics table in CLI
- [ ] 6.2 Color-coded good/bad metrics
- [ ] 6.3 `backtest analyze --run-id X` command to show full report
- [ ] 6.4 Compare two runs side-by-side

**Acceptance**: CLI shows comprehensive analytics ✅ (basic)

---

## Metrics Reference

### Must-Have (Phase 1-3)
| Metric | Formula | Status |
|--------|---------|--------|
| Net Return % | (final - initial) / initial | ✅ |
| Sharpe | mean(returns) / std(returns) * sqrt(periods) | ✅ computed |
| Sortino | mean(returns) / downside_std * sqrt(periods) | ❌ |
| Profit Factor | gross_profit / gross_loss | ✅ |
| Calmar | annualized_return / max_dd | ❌ |
| Win Rate | wins / total | ✅ |
| Expectancy | avg PnL per trade | ❌ |
| Payoff Ratio | avg_win / avg_loss | ❌ |
| Max Drawdown | peak_to_trough / peak | ✅ |
| Max DD Duration | bars in drawdown | ✅ |
| Recovery Factor | net_profit / max_dd | ❌ |

### Nice-to-Have (Phase 4-5)
| Metric | Description |
|--------|-------------|
| Monthly Returns | PnL per calendar month |
| Time in Market | % of bars with open position |
| Alpha | Return above buy-and-hold |
| Beta | Correlation to underlying |

