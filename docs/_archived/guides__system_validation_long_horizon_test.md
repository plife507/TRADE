# System Validation: Long-Horizon Test Guide

**IdeaCard:** `BTCUSDT_1h_system_validation_1year.yml`  
**Purpose:** Regression test for architectural changes over extended time horizons  
**Domain:** SIMULATOR (Backtest)

---

## Overview

This guide explains how to use the system validation IdeaCard as a **canary test** after making architectural changes to the backtest engine, snapshot layer, MTF routing, or artifact generation.

### What This Test Validates

| Component | What's Tested |
|-----------|---------------|
| **Array-backed engine** | Stability over 8,760+ hours (~1 year of 1h bars) |
| **RuntimeSnapshotView** | O(1) access correctness with deep history lookbacks |
| **MTF routing** | 15m/1h/4h alignment and forward-fill behavior |
| **Parquet artifacts** | trades.parquet, equity.parquet, result.json generation |
| **Memory stability** | No leaks or degradation over long runs |
| **Determinism** | Same inputs → same outputs across repeated runs |

### What This Test Does NOT Validate

- Strategy profitability (this is a diagnostic, not a trading strategy)
- Funding cashflow PnL (funding is NOT applied in current iteration)
- Parameter optimization or sensitivity
- Live trading execution paths

---

## Test Strategy (Intentionally Simple)

The IdeaCard uses a basic trend-following pattern:

**Entry Logic:**
- **LONG:** Exec TF fast EMA crosses above slow EMA + price above HTF trend + MTF RSI > 40
- **SHORT:** Exec TF fast EMA crosses below slow EMA + price below HTF trend + MTF RSI < 60

**Exit Logic:**
- Opposite signal (EMA crossover in reverse direction)

**Risk Management:**
- 2x ATR stop loss
- 2:1 R:R take profit
- 1% equity risk per trade
- Max 2x leverage

**Timeframes:**
- Exec: 1h (generates ~10-30 trades/year)
- HTF: 4h (trend filter)
- MTF: 15m (momentum confirmation)

---

## How to Run

### Step 1: Validate Data Coverage

```bash
python trade_cli.py backtest preflight --idea BTCUSDT_1h_system_validation_1year
```

**Expected output:**
- ✅ All timeframes (15m, 1h, 4h) have sufficient data
- ✅ Warmup requirements met (250 exec bars, 150 HTF bars, 100 MTF bars)
- ✅ No gaps in the requested date range

**If preflight fails:**
- Run data sync for BTCUSDT: `python trade_cli.py` → Data Builder → sync OHLCV

---

### Step 2: Run 1-Year Backtest

```bash
python trade_cli.py backtest run \
    --idea BTCUSDT_1h_system_validation_1year \
    --start 2024-01-01 \
    --end 2024-12-31 \
    --env live
```

**Expected behavior:**
- Completes in < 5 minutes on modern hardware
- Generates 10-30 trades (approximate, regime-dependent)
- No crashes, OOM errors, or alignment failures
- Memory usage stays flat (no growth over time)

**Artifacts generated:**
```
backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-001/
├── trades.parquet          # All trade records
├── equity.parquet          # Equity curve over time
├── result.json             # Metrics summary
├── preflight_report.json   # Data coverage validation
└── pipeline_signature.json # Reproducibility metadata
```

---

### Step 3: Verify Determinism

Run the backtest **twice** with identical parameters and compare results:

```bash
# Run 1
python trade_cli.py backtest run \
    --idea BTCUSDT_1h_system_validation_1year \
    --start 2024-01-01 \
    --end 2024-12-31 \
    --env live

# Run 2 (same command)
python trade_cli.py backtest run \
    --idea BTCUSDT_1h_system_validation_1year \
    --start 2024-01-01 \
    --end 2024-12-31 \
    --env live

# Compare artifacts
diff backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-001/result.json \
     backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-002/result.json
```

**Expected output:**
- ✅ No differences in result.json
- ✅ Identical trade counts, equity curves, and metrics
- ✅ Same timestamps and prices for all entries/exits

**If results differ:**
- ❌ Non-deterministic behavior detected (investigate random state, timestamps, or floating-point drift)

---

## Success Criteria

### ✅ Pass Conditions

| Check | Expected Result |
|-------|-----------------|
| **Completion** | Backtest finishes without crashes or errors |
| **Trade count** | ~10-30 trades (approximate, regime-dependent) |
| **Memory** | Flat usage throughout run (no leaks) |
| **Artifacts** | All Parquet files written and readable |
| **Determinism** | Repeated runs produce identical results |
| **MTF values** | No "key not found" or alignment errors in logs |
| **Performance** | Completes in < 5 minutes |

### ❌ Failure Indicators

| Symptom | Likely Cause | Where to Investigate |
|---------|--------------|----------------------|
| **Crash/OOM** | Memory leak | RuntimeSnapshotView, FeedStore, array caching |
| **Zero trades** | MTF alignment broken | TFContext, signal condition evaluation |
| **Non-deterministic** | Random state dependency | Indicator computation, snapshot indexing |
| **Missing artifacts** | Parquet writer failure | ArtifactStore, Parquet serialization |
| **MTF value errors** | Forward-fill broken | TFContext.get_feature(), MTF caching |
| **Performance degradation** | O(n²) hot loop | Snapshot access, array operations |
| **Alignment errors** | TF conversion bug | TimeframeUtils, bar indexing |

---

## What to Check in Artifacts

### 1. result.json

```json
{
  "total_trades": 15,              // Should be > 0 (typically 10-30)
  "win_rate_pct": 40.0,            // Not relevant (not optimized for profit)
  "max_drawdown_pct": 12.5,        // Should be reasonable (< 50%)
  "final_equity_usdt": 9850.0,     // May be lower than starting (that's OK)
  "sharpe_ratio": 0.35,            // Not relevant (diagnostic test)
  "completed": true,               // MUST be true
  "runtime_seconds": 180.5         // Should be < 300 (5 minutes)
}
```

### 2. trades.parquet

Check that trades have:
- Valid entry/exit timestamps
- Correct direction (long/short)
- Reasonable hold durations (hours to days)
- SL/TP prices populated
- Fee calculations present

```python
import pandas as pd
trades = pd.read_parquet('backtests/.../trades.parquet')
print(trades[['entry_time', 'exit_time', 'direction', 'pnl_usdt', 'hold_duration_hours']].head(10))
```

### 3. equity.parquet

Check equity curve:
- Starts at 10,000 USDT
- Smooth progression (no sudden jumps)
- Timestamps align with exec TF (1h intervals)

```python
import pandas as pd
equity = pd.read_parquet('backtests/.../equity.parquet')
print(equity[['timestamp', 'equity_usdt', 'unrealized_pnl_usdt']].head(20))
```

---

## When to Run This Test

### Required (Before Merging)

Run this test **before merging** any changes to:
- `src/backtest/engine.py` (backtest orchestrator)
- `src/backtest/runtime/` (RuntimeSnapshotView, FeedStore, TFContext)
- `src/backtest/sim/` (SimulatedExchange, pricing, ledger)
- `src/backtest/features/` (FeatureSpec, FeatureFrameBuilder)
- Artifact serialization (Parquet writers)
- Timeframe alignment logic

### Optional (Good Practice)

Run this test after:
- Major refactors in shared utilities
- DuckDB schema changes
- Dependency updates (pandas, numpy, polars)
- Performance optimizations in hot loops

---

## Interpreting Results

### Expected Trade Characteristics

| Metric | Expected Range | Interpretation |
|--------|----------------|----------------|
| **Total trades** | 10-30 | Regime-dependent; zero trades = broken signals |
| **Avg hold duration** | 2-10 days | Trend-following holds positions across regime shifts |
| **Win rate** | 30-60% | Not optimized; < 20% = potential bug |
| **Max drawdown** | 5-30% | Unoptimized; > 50% = potential risk bug |

### This is NOT a Profitability Test

**Key point:** The strategy may lose money. That's OK.

What matters:
- ✅ Backtest completes without errors
- ✅ Trades are generated (signals work)
- ✅ Results are deterministic
- ✅ Artifacts are valid

What doesn't matter:
- ❌ Sharpe ratio
- ❌ Total return
- ❌ Win rate

---

## Troubleshooting

### Problem: Zero Trades

**Cause:** Signal conditions too strict or MTF alignment broken

**Debug steps:**
1. Check indicator values are populated:
   ```bash
   python trade_cli.py backtest indicators --idea BTCUSDT_1h_system_validation_1year --print-keys
   ```
2. Check signal conditions in IdeaCard YAML
3. Check logs for "MTF value not found" errors

---

### Problem: Non-Deterministic Results

**Cause:** Random state, floating-point instability, or timestamp dependency

**Debug steps:**
1. Check for `np.random` calls without seed
2. Check for datetime.now() calls in hot loop
3. Check for unordered dict iteration in signal evaluation

---

### Problem: Slow Performance (> 5 minutes)

**Cause:** O(n²) behavior or excessive DataFrame operations

**Debug steps:**
1. Profile with `cProfile`:
   ```bash
   python -m cProfile -o backtest.prof trade_cli.py backtest run ...
   ```
2. Check for DataFrame operations in hot loop
3. Check for repeated disk I/O

---

## Regression Test Baseline

After architectural changes stabilize, establish a **baseline run** to compare against:

```bash
# Create baseline
python trade_cli.py backtest run \
    --idea BTCUSDT_1h_system_validation_1year \
    --start 2024-01-01 \
    --end 2024-12-31 \
    --env live

# Save baseline artifacts
cp backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-001/result.json \
   docs/baselines/system_validation_1year_baseline.json
```

After future changes, compare new runs against the baseline:
- Trade count should match exactly
- Equity curve should match exactly
- Timestamps should match exactly

---

## FAQ

### Q: Can I use a different symbol?

**A:** Yes, but BTCUSDT is recommended for consistency. If using another symbol:
- Must end in "USDT"
- Must have 1+ year of clean data
- Update IdeaCard ID and filename accordingly

### Q: Can I use a different date range?

**A:** Yes. The 1-year range is recommended for long-horizon validation, but you can test with:
- 3 months (shorter, faster)
- 2 years (longer, more comprehensive)

### Q: Why does this strategy lose money?

**A:** It's intentionally unoptimized. The goal is to validate **plumbing correctness**, not profitability. A profitable strategy would mask subtle bugs.

### Q: Should I optimize the parameters?

**A:** No. This is a diagnostic test with fixed parameters. Optimization would defeat the purpose (deterministic regression testing).

---

## Related Documentation

- **IdeaCard YAML Structure:** `docs/reviews/IDEACARD_YAML_STRUCTURE_REVIEW.md`
- **Backtest Engine Architecture:** `docs/architecture/BACKTEST_MODULE_OVERVIEW.md`
- **MTF Snapshot Alignment:** `docs/todos/archived/SNAPSHOT_HISTORY_MTF_ALIGNMENT_PHASES.md`
- **Artifact Storage Format:** `docs/architecture/ARTIFACT_STORAGE_FORMAT.md`

---

## Summary

The `BTCUSDT_1h_system_validation_1year` IdeaCard is a **canary test** for long-horizon stability. It's designed to break if architectural changes introduce bugs in:

1. Memory management
2. MTF alignment
3. Snapshot plumbing
4. Artifact generation
5. Determinism

Run this test before merging architectural changes. If it passes, you have high confidence that the system remains stable over extended time horizons.

**Remember:** This is NOT a trading strategy. It's a diagnostic tool. Profitability is irrelevant; correctness is everything.

