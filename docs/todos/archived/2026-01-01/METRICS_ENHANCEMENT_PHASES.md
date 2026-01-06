# Metrics Enhancement Phases

**Created**: 2025-12-31
**Status**: COMPLETE (All phases ✅)
**Context**: Comparison with industry-standard metrics revealed gaps

---

## Implementation Summary (2025-12-31 to 2026-01-01)

### Completed Phases

**Phase 1**: Benchmark comparison metrics (2 fields) ✅
- `benchmark_return_pct`: Buy-and-hold return over backtest period
- `alpha_pct`: Strategy outperformance vs benchmark

**Phase NEW** (unplanned): High-value leveraged trading metrics (8 fields) ✅
- **Tail Risk** (4): `skewness`, `kurtosis`, `var_95_pct`, `cvar_95_pct`
- **Leverage** (2): `avg_leverage_used`, `max_gross_exposure_pct`
- **Trade Quality** (2): `mae_avg_pct`, `mfe_avg_pct`

### Net Additions
- **Starting**: 49 fields (baseline)
- **Added**: +13 fields (Phase 1: +2, Phase NEW: +8, Phase 3: +2, Phase 4: +1)
- **Current**: **62 fields**

**Phase 3**: Duration breakdown (2 fields) ✅
- `avg_winning_trade_duration_bars`: Avg duration for winning trades
- `avg_losing_trade_duration_bars`: Avg duration for losing trades

**Phase 4**: Omega ratio (1 field) ✅
- `omega_ratio`: Probability-weighted gain/loss ratio (threshold=0)

### Deferred Phases
- Phase 5: Display-time percentage computations (non-stored) - optional

**Reason**: All high-value metrics implemented. Phase 5 deferred as display-time computation (no storage needed).

### All 59 BacktestMetrics Fields (Complete List)

<details>
<summary>Click to expand complete field list</summary>

**Core Performance (6)**
1. initial_equity
2. final_equity
3. net_profit
4. net_return_pct
5. benchmark_return_pct ← Phase 1
6. alpha_pct ← Phase 1

**Drawdown (4)**
7. max_drawdown_abs
8. max_drawdown_pct
9. max_drawdown_duration_bars
44. ulcer_index

**Trade Summary (3)**
10. total_trades
11. win_rate
12. avg_trade_return_pct
13. profit_factor
45. profit_factor_mode

**Risk-Adjusted (3)**
14. sharpe
15. sortino
16. calmar
31. recovery_factor

**Trade Counts (5)**
17. win_count
18. loss_count
19. gross_profit
20. gross_loss
21. total_fees

**Extended Trade Analytics (7)**
22. avg_win_usdt
23. avg_loss_usdt
24. largest_win_usdt
25. largest_loss_usdt
26. avg_trade_duration_bars
27. max_consecutive_wins
28. max_consecutive_losses
29. expectancy_usdt
30. payoff_ratio

**Long/Short Breakdown (6)**
32. long_trades
33. short_trades
34. long_win_rate
35. short_win_rate
36. long_pnl
37. short_pnl

**Time Metrics (3)**
38. total_bars
39. bars_in_position
40. time_in_market_pct

**Funding Metrics (3)**
41. total_funding_paid_usdt
42. total_funding_received_usdt
43. net_funding_usdt

**Entry Friction (3)**
46. entry_attempts
47. entry_rejections
48. entry_rejection_rate

**Margin Stress (3)**
49. min_margin_ratio
50. margin_calls
51. closest_liquidation_pct

**Tail Risk (4) ← Phase NEW**
52. skewness
53. kurtosis
54. var_95_pct
55. cvar_95_pct

**Leverage (2) ← Phase NEW**
56. avg_leverage_used
57. max_gross_exposure_pct

**Trade Quality MAE/MFE (2) ← Phase NEW**
58. mae_avg_pct
59. mfe_avg_pct

</details>

---

## Problem Statement

Code review comparing BacktestMetrics against industry-standard trading platforms revealed:
- Missing benchmark comparison metrics (strategy vs buy-and-hold)
- Missing exposure metrics (max gross exposure)
- Missing percentage variants for trade metrics (we have USDT, need %)
- Missing duration breakdown (avg winning vs losing trade duration)
- Missing advanced risk-adjusted metrics (Omega ratio)

---

## Current State: 59 BacktestMetrics Fields (after all phases)

### Core Performance
- `initial_equity`, `final_equity`, `net_profit`, `net_return_pct`
- `benchmark_return_pct`, `alpha_pct` ← **NEW in Phase 1**
- `gross_profit`, `gross_loss`, `profit_factor`, `profit_factor_mode`

### Trade Statistics
- `total_trades`, `win_count`, `loss_count`, `win_rate`
- `long_trades`, `short_trades`, `long_win_rate`, `short_win_rate`
- `long_pnl`, `short_pnl`

### Trade Size (USDT only - missing %)
- `avg_win_usdt`, `avg_loss_usdt`, `expectancy_usdt`
- `largest_win_usdt`, `largest_loss_usdt`
- `payoff_ratio` (avg_win / avg_loss)

### Duration
- `avg_trade_duration_bars`, `total_bars`, `bars_in_position`
- `time_in_market_pct`, `max_drawdown_duration_bars`

### Drawdown
- `max_drawdown_pct`, `max_drawdown_abs`, `ulcer_index`

### Risk-Adjusted
- `sharpe`, `sortino`, `calmar`, `recovery_factor`

### Streaks
- `max_consecutive_wins`, `max_consecutive_losses`

### Fees/Funding
- `total_fees`, `net_funding_usdt`
- `total_funding_paid_usdt`, `total_funding_received_usdt`

### Margin/Risk
- `min_margin_ratio`, `margin_calls`, `closest_liquidation_pct`
- `entry_attempts`, `entry_rejections`, `entry_rejection_rate`

### Tail Risk Metrics ← **NEW (Phase NEW - unplanned)**
- `skewness`, `kurtosis`, `var_95_pct`, `cvar_95_pct`

### Leverage Metrics ← **NEW (Phase NEW - unplanned)**
- `avg_leverage_used`, `max_gross_exposure_pct`

### Trade Quality (MAE/MFE) ← **NEW (Phase NEW - unplanned)**
- `mae_avg_pct`, `mfe_avg_pct`

---

## Gap Analysis: Original Missing Metrics

| Metric | Priority | Complexity | Status | Notes |
|--------|----------|------------|--------|-------|
| **Benchmark Return %** | HIGH | Medium | ✅ COMPLETE | Buy-and-hold comparison (Phase 1) |
| **Alpha (vs benchmark)** | HIGH | Low | ✅ COMPLETE | net_return - benchmark_return (Phase 1) |
| **Max Gross Exposure %** | MEDIUM | Low | ✅ COMPLETE | Peak position size / equity (Phase NEW) |
| **Best Trade %** | LOW | Trivial | 📋 DEFERRED | Display-time computation (Phase 5) |
| **Worst Trade %** | LOW | Trivial | 📋 DEFERRED | Display-time computation (Phase 5) |
| **Avg Win %** | LOW | Trivial | 📋 DEFERRED | Display-time computation (Phase 5) |
| **Avg Loss %** | LOW | Trivial | 📋 DEFERRED | Display-time computation (Phase 5) |
| **Avg Winning Trade Duration** | MEDIUM | Low | 📋 PENDING | Separate from losing (Phase 3) |
| **Avg Losing Trade Duration** | MEDIUM | Low | 📋 PENDING | Separate from winning (Phase 3) |
| **Omega Ratio** | LOW | Medium | 📋 PENDING | Threshold-based gain/loss (Phase 4) |

---

## Design Decision: Stored vs Display-Time Computation

**Problem**: Some percentage metrics can be computed from existing fields at display time.

**Options**:
1. **Store all computed values**: Same inputs = same outputs (determinism)
2. **Compute at display time**: Avoid field bloat, but requires entry_equity context

**Decision**: **Hybrid approach**
- **Store benchmark/alpha**: These are core strategy evaluation metrics
- **Store duration breakdown**: Critical for strategy analysis
- **Compute trade percentages at display time**: `best_trade_pct` = `largest_win_usdt / initial_equity * 100`
  - Using `initial_equity` as base (consistent, always available)
  - Avoids adding `entry_equity` field to every Trade
  - Display layer can compute: `metrics.largest_win_usdt / metrics.initial_equity * 100`

This keeps BacktestMetrics focused while allowing rich display formatting.

---

## Phase 1: Benchmark Comparison Metrics ✅ COMPLETE

**Goal**: Add buy-and-hold comparison for alpha calculation

### Design

Benchmark return measures what a passive buy-and-hold strategy would have returned:
- **Buy**: At first simulation bar's close price
- **Hold**: Through entire simulation period
- **Sell**: At last simulation bar's close price

This is the standard comparison for evaluating active strategy performance.

### Data Flow

```
exec_feed.close[sim_start_idx] -> first_price
exec_feed.close[last_idx]      -> last_price
benchmark_return_pct = (last_price - first_price) / first_price * 100
alpha_pct = net_return_pct - benchmark_return_pct
```

The engine already has access to `exec_feed` with all close prices. The key is capturing
`first_price` and `last_price` from the correct indices.

### Tasks

- [x] 1.1 Add `benchmark_return_pct: float = 0.0` to BacktestMetrics (types.py)
- [x] 1.2 Add `alpha_pct: float = 0.0` to BacktestMetrics (types.py)
- [x] 1.3 Add parameters to `compute_backtest_metrics()` for first/last price (metrics.py)
- [x] 1.4 Compute benchmark in `compute_backtest_metrics()` (metrics.py)
- [x] 1.5 Pass first/last price from engine.run() to metrics (engine.py)
- [x] 1.6 Update BacktestMetrics.to_dict() with new fields (types.py)

### Implementation Details

**File: `src/backtest/types.py`**

Add after `net_return_pct`:
```python
# Benchmark comparison
benchmark_return_pct: float = 0.0  # Buy-and-hold return over same period
alpha_pct: float = 0.0             # Strategy return - benchmark return
```

Add to `to_dict()`:
```python
"benchmark_return_pct": self.benchmark_return_pct,
"alpha_pct": self.alpha_pct,
```

**File: `src/backtest/metrics.py`**

Add parameters to `compute_backtest_metrics()`:
```python
def compute_backtest_metrics(
    equity_curve: List[EquityPoint],
    trades: List[Trade],
    tf: str,
    initial_equity: float,
    bars_in_position: int = 0,
    # ... existing params ...
    # NEW: Benchmark calculation
    first_price: float = 0.0,
    last_price: float = 0.0,
) -> BacktestMetrics:
```

Add benchmark computation (after net_return_pct calculation):
```python
# Benchmark return: buy-and-hold from first to last price
if first_price > 0:
    benchmark_return_pct = ((last_price - first_price) / first_price) * 100
else:
    benchmark_return_pct = 0.0

# Alpha: strategy outperformance vs benchmark
alpha_pct = net_return_pct - benchmark_return_pct
```

**File: `src/backtest/engine.py`**

In `run()` method, capture prices from exec_feed:
```python
# Benchmark prices (from simulation start to end)
first_price = float(exec_feed.close[sim_start_idx])
last_price = float(exec_feed.close[exec_feed.length - 1])
```

Pass to metrics computation:
```python
metrics = compute_backtest_metrics(
    # ... existing params ...
    first_price=first_price,
    last_price=last_price,
)
```

### Gate 1.1

```bash
# Verify field exists
python -c "from src.backtest.types import BacktestMetrics; m = BacktestMetrics(); print(f'benchmark={m.benchmark_return_pct}, alpha={m.alpha_pct}')"
# Expected: benchmark=0.0, alpha=0.0
```

### Gate 1.2

```bash
# Run smoke test and verify benchmark is computed
python trade_cli.py backtest run --idea-card strategies/idea_cards/validation/BTCUSDT_15m_simple.yml --json | python -c "import sys, json; d=json.load(sys.stdin); m=d['metrics']; print(f'benchmark={m[\"benchmark_return_pct\"]}, alpha={m[\"alpha_pct\"]}')"
# Expected: benchmark and alpha should be non-zero for any price movement
```

---

## Phase 2: Exposure Metrics ✅ COMPLETE (merged into Phase NEW)

**Status**: ✅ COMPLETE - Implemented as part of Phase NEW leverage metrics

**Goal**: Track maximum position exposure relative to equity

### Design

Max gross exposure measures the highest leverage actually used during the simulation:
- **Gross Exposure** = |position_value| / equity * 100
- Track peak value across all bars with open positions

This differs from `risk_max_leverage_used` (the configured limit) - exposure shows actual usage.

### Implementation Summary

- ✅ Added `max_gross_exposure_pct: float = 0.0` to BacktestMetrics
- ✅ Added `avg_leverage_used: float = 0.0` to BacktestMetrics (bonus metric)
- ✅ Computed in `engine.run()` from account curve
- ✅ Passed to `compute_backtest_metrics()`
- ✅ Updated `BacktestMetrics.to_dict()`

**See**: Phase NEW below for full implementation details

---

## Phase 3: Duration Breakdown ✅ COMPLETE

**Goal**: Separate avg duration for winning vs losing trades

### Design

Different duration profiles for wins vs losses indicate strategy characteristics:
- **Winning trades held longer**: May indicate trend-following (letting profits run)
- **Losing trades held longer**: May indicate holding losers too long

The Trade dataclass already has `duration_bars` property computed from bar indices.

### Tasks

- [ ] 3.1 Add `avg_winning_trade_duration_bars: float = 0.0` to BacktestMetrics
- [ ] 3.2 Add `avg_losing_trade_duration_bars: float = 0.0` to BacktestMetrics
- [ ] 3.3 Compute separately in compute_backtest_metrics from trades list
- [ ] 3.4 Update BacktestMetrics.to_dict() with new fields

### Implementation Details

**File: `src/backtest/types.py`**

Add after `avg_trade_duration_bars`:
```python
avg_winning_trade_duration_bars: float = 0.0  # Avg duration for winning trades
avg_losing_trade_duration_bars: float = 0.0   # Avg duration for losing trades
```

**File: `src/backtest/metrics.py`**

Add after `avg_trade_duration_bars` calculation (around line 287):
```python
# Duration breakdown by win/loss
winning_durations = [
    t.duration_bars for t in trades
    if t.duration_bars is not None and t.net_pnl > 0
]
losing_durations = [
    t.duration_bars for t in trades
    if t.duration_bars is not None and t.net_pnl < 0
]

if winning_durations:
    avg_winning_trade_duration_bars = sum(winning_durations) / len(winning_durations)
else:
    avg_winning_trade_duration_bars = 0.0

if losing_durations:
    avg_losing_trade_duration_bars = sum(losing_durations) / len(losing_durations)
else:
    avg_losing_trade_duration_bars = 0.0
```

### Gate 3.1

```bash
# Verify fields exist
python -c "from src.backtest.types import BacktestMetrics; m = BacktestMetrics(); print(f'win_dur={m.avg_winning_trade_duration_bars}, loss_dur={m.avg_losing_trade_duration_bars}')"
```

### Gate 3.2

```bash
# Run backtest with trades and verify duration split
python trade_cli.py backtest run --idea-card strategies/idea_cards/validation/BTCUSDT_15m_simple.yml --json | python -c "import sys, json; d=json.load(sys.stdin); m=d['metrics']; print(f'win_dur={m[\"avg_winning_trade_duration_bars\"]}, loss_dur={m[\"avg_losing_trade_duration_bars\"]}')"
```

---

## Phase 4: Omega Ratio (LOW PRIORITY)

**Goal**: Add threshold-based gain/loss ratio

### Design

Omega ratio captures the probability-weighted gain/loss ratio:
- **Omega > 1**: More probability-weighted gains than losses
- Uses a threshold (typically 0 for risk-free rate)

Formula:
```
Omega = (Sum of returns above threshold) / |Sum of returns below threshold|
```

For threshold = 0:
- Numerator = sum of all positive per-bar returns
- Denominator = abs(sum of all negative per-bar returns)

### Tasks

- [ ] 4.1 Add `omega_ratio: float = 0.0` to BacktestMetrics
- [ ] 4.2 Add `_compute_omega()` helper function in metrics.py
- [ ] 4.3 Call from compute_backtest_metrics()
- [ ] 4.4 Update BacktestMetrics.to_dict()

### Implementation Details

**File: `src/backtest/types.py`**

Add after `recovery_factor`:
```python
omega_ratio: float = 0.0  # Probability-weighted gain/loss ratio (threshold=0)
```

**File: `src/backtest/metrics.py`**

Add helper function after `_compute_consecutive_streaks()`:
```python
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
```

Call from `compute_backtest_metrics()`:
```python
omega_ratio = _compute_omega(equity_curve)
```

### Gate 4.1

```bash
# Verify field exists
python -c "from src.backtest.types import BacktestMetrics; m = BacktestMetrics(); print(f'omega={m.omega_ratio}')"
```

---

## Phase 5: Display-Time Percentage Computations (OPTIONAL)

**Goal**: Document display-time percentage calculations

### Design Decision

Rather than storing percentage variants in BacktestMetrics (field bloat), these are
computed at display time using `initial_equity` as the base:

| Display Metric | Computation |
|----------------|-------------|
| Best Trade % | `largest_win_usdt / initial_equity * 100` |
| Worst Trade % | `largest_loss_usdt / initial_equity * 100` |
| Avg Win % | `avg_win_usdt / initial_equity * 100` |
| Avg Loss % | `avg_loss_usdt / initial_equity * 100` |

**Rationale**:
- `initial_equity` is always available and consistent
- Avoids needing per-trade `entry_equity` (which varies per trade)
- Display layer already has access to all BacktestMetrics fields
- Keeps BacktestMetrics focused on computed/stored values

### Implementation Location

Display-time computations belong in:
- CLI formatters (`src/cli/formatters.py` or similar)
- Report generators
- Dashboard/UI components

Example (CLI formatter):
```python
def format_trade_percentages(metrics: BacktestMetrics) -> dict:
    """Compute percentage trade metrics for display."""
    if metrics.initial_equity <= 0:
        return {}

    return {
        "best_trade_pct": round(metrics.largest_win_usdt / metrics.initial_equity * 100, 2),
        "worst_trade_pct": round(metrics.largest_loss_usdt / metrics.initial_equity * 100, 2),
        "avg_win_pct": round(metrics.avg_win_usdt / metrics.initial_equity * 100, 2),
        "avg_loss_pct": round(metrics.avg_loss_usdt / metrics.initial_equity * 100, 2),
    }
```

### Tasks

- [ ] 5.1 Add `format_trade_percentages()` to display layer (if needed)
- [ ] 5.2 Document display-time computation pattern in code comments

---

## Phase NEW: Tail Risk, Leverage, and Trade Quality Metrics ✅ COMPLETE

**Status**: ✅ COMPLETE (implemented 2026-01-01)
**Context**: Unplanned enhancement - added 8 high-value metrics for leveraged trading

### Added Metrics

#### Tail Risk (4 metrics)
Critical for understanding blowup risk in leveraged trading:
- `skewness`: Return distribution asymmetry (negative = fat left tail = blowup risk)
- `kurtosis`: Fat tails measure (>3 = fatter tails than normal distribution)
- `var_95_pct`: 95% Value at Risk (worst 5% daily loss threshold)
- `cvar_95_pct`: Conditional VaR / Expected Shortfall (average loss beyond VaR)

#### Leverage Metrics (2 metrics)
Track actual leverage usage vs configured limits:
- `avg_leverage_used`: Average leverage across all bars with positions
- `max_gross_exposure_pct`: Peak position_value / equity * 100 (Phase 2 merged here)

#### Trade Quality - MAE/MFE (2 metrics)
Maximum Adverse/Favorable Excursion per trade:
- `mae_avg_pct`: Average worst drawdown within each trade before exit
- `mfe_avg_pct`: Average best profit within each trade before exit

**Use Case**: Identify if exits are too early (high MFE) or stops too wide (high MAE)

### Implementation Files

**Modified**:
- `src/backtest/types.py` - Added 8 fields to BacktestMetrics + to_dict()
- `src/backtest/types.py` - Added `mae_pct`, `mfe_pct` to Trade dataclass
- `src/backtest/metrics.py` - Added tail risk, leverage, MAE/MFE computations
- `src/backtest/engine.py` - Track MAE/MFE during position lifecycle
- `src/backtest/engine.py` - Compute leverage metrics from account curve

### Key Design Decisions

1. **Tail Risk**: Computed from per-bar equity returns (not trade returns)
   - Uses daily/bar-level returns for VaR/CVaR (standard risk management)
   - Skewness/kurtosis detect non-normal return distributions

2. **Leverage**: Two complementary metrics
   - `avg_leverage_used`: Mean exposure over time (position bars only)
   - `max_gross_exposure_pct`: Peak exposure (worst-case stress)

3. **MAE/MFE**: Trade-level tracking
   - Added `mae_pct`, `mfe_pct` to Trade dataclass
   - Tracked during position lifecycle in engine hot loop
   - Averaged across all closed trades in metrics computation

### Validation

All 8 metrics verified through:
- Field existence checks (Python import)
- Backtest runs with validation idea cards
- JSON export verification
- Display in CLI output

---

## Summary: New Fields Per Phase

| Phase | New Fields | Total Fields |
|-------|------------|--------------|
| Current | - | 49 |
| Phase 1 | +2 (benchmark_return_pct, alpha_pct) | 51 |
| Phase 2 | +1 (max_gross_exposure_pct) - merged into Phase NEW | - |
| Phase 3 | +2 (avg_winning/losing_trade_duration_bars) | 📋 PENDING |
| Phase 4 | +1 (omega_ratio) | 📋 PENDING |
| Phase 5 | +0 (display-time only) | 📋 DEFERRED |
| **Phase NEW** | **+8 (tail risk + leverage + MAE/MFE)** | **59** |

**Current count**: 59 fields (net +10 stored fields from baseline 49)

---

## Validation Matrix

| Phase | Gate | Command | Pass Criteria | Status |
|-------|------|---------|---------------|--------|
| 1 | Field exists | Python import test | benchmark/alpha fields exist | ✅ PASSED |
| 1 | Computed | Backtest run | benchmark/alpha correctly computed | ✅ PASSED |
| 2 | Field exists | Python import test | max_gross_exposure_pct exists | ✅ PASSED (Phase NEW) |
| 2 | Computed | Backtest run | exposure > 0 if trades exist | ✅ PASSED (Phase NEW) |
| 3 | Field exists | Python import test | win/loss duration fields exist | ✅ PASSED |
| 3 | Computed | Backtest run | durations computed separately | ✅ PASSED |
| 4 | Field exists | Python import test | omega_ratio exists | ✅ PASSED |
| 4 | Computed | Backtest run | omega > 0 for profitable runs | ✅ PASSED |
| **NEW** | **Tail risk** | **Python import test** | **skewness/kurtosis/var/cvar exist** | ✅ **PASSED** |
| **NEW** | **Leverage** | **Backtest run** | **avg_leverage_used computed** | ✅ **PASSED** |
| **NEW** | **MAE/MFE** | **Trade analysis** | **mae_avg_pct/mfe_avg_pct computed** | ✅ **PASSED** |

---

## Acceptance Criteria

- [x] Benchmark comparison metrics (Phase 1) - HIGH PRIORITY ✅
- [x] Max gross exposure tracking (Phase 2) - MEDIUM PRIORITY ✅ (Phase NEW)
- [x] Tail risk metrics (Phase NEW) - HIGH VALUE ✅
- [x] Leverage metrics (Phase NEW) - HIGH VALUE ✅
- [x] MAE/MFE trade quality (Phase NEW) - HIGH VALUE ✅
- [x] Duration breakdown by win/loss (Phase 3) - ✅ COMPLETE
- [x] Omega ratio (Phase 4) - ✅ COMPLETE
- [ ] Display-time percentages documented (Phase 5) - OPTIONAL 📋 DEFERRED
- [x] All smoke tests pass ✅
- [x] BacktestMetrics.to_dict() includes all new fields ✅
- [x] Field count: 62 (from 49) ✅

---

## Files Modified Per Phase

### Phase 1 ✅ COMPLETE
- `src/backtest/types.py` - Add 2 fields (benchmark_return_pct, alpha_pct) + to_dict()
- `src/backtest/metrics.py` - Add params + computation
- `src/backtest/engine.py` - Pass first/last price

### Phase 2 ✅ COMPLETE (merged into Phase NEW)
- See Phase NEW below

### Phase NEW ✅ COMPLETE
**Tail Risk + Leverage + MAE/MFE (8 metrics)**
- `src/backtest/types.py` - Add 8 fields to BacktestMetrics + to_dict()
  - Tail risk: skewness, kurtosis, var_95_pct, cvar_95_pct
  - Leverage: avg_leverage_used, max_gross_exposure_pct
  - Trade quality: mae_avg_pct, mfe_avg_pct
- `src/backtest/types.py` - Add mae_pct, mfe_pct to Trade dataclass + to_dict()
- `src/backtest/metrics.py` - Add tail risk computation functions
- `src/backtest/metrics.py` - Add MAE/MFE averaging from trades
- `src/backtest/engine.py` - Track MAE/MFE during position lifecycle
- `src/backtest/engine.py` - Compute leverage metrics from account curve
- `src/backtest/engine.py` - Pass all new metrics to compute_backtest_metrics()

### Phase 3 ✅ COMPLETE
- `src/backtest/types.py` - Added 2 fields (avg_winning/losing_trade_duration_bars) + to_dict()
- `src/backtest/metrics.py` - Added duration split computation

### Phase 4 ✅ COMPLETE
- `src/backtest/types.py` - Added 1 field (omega_ratio) + to_dict()
- `src/backtest/metrics.py` - Added _compute_omega() helper + call
