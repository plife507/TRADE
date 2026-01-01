# System Validation: Low-TF Indicator Stress Test

**IdeaCard:** `BTCUSDT_5m_stress_test_indicator_dense.yml`  
**Purpose:** Stress-test engine performance and snapshot plumbing at low timeframe with dense indicators  
**Domain:** SIMULATOR (Backtest)

---

## Overview

This guide explains how to use the low-TF stress test IdeaCard as a **performance canary** after making changes to the array-backed hot loop, indicator computation, or snapshot layer.

### What This Test Validates

| Component | What's Tested |
|-----------|---------------|
| **Array-backed hot loop** | Performance over 17K+ bars (5m * 60 days) |
| **RuntimeSnapshotView** | Frequent indicator access under load |
| **Dense indicators** | 6 indicators, 9 output columns simultaneously |
| **Multi-output indicators** | MACD expansion (macd, signal, histogram) |
| **Rolling windows** | Fast updates every 5 minutes |
| **NaN propagation** | Warmup and missing value handling |
| **Memory efficiency** | Stability under dense indicator sets |
| **Determinism** | Identical results across repeated runs |

### What This Test Does NOT Validate

- Strategy profitability (intentionally high-churn, lossy strategy)
- Funding cashflow PnL (not modeled)
- Live trading execution paths
- Multi-symbol backtesting

---

## Test Strategy (Intentionally High-Churn)

The IdeaCard uses a momentum strategy designed to generate frequent trades:

**Entry Logic:**

**LONG:**
1. Exec TF: EMA(9) > EMA(26) (trend)
2. Exec TF: RSI(14) > 50 (momentum)
3. Exec TF: MACD histogram > 0 (confirmation)
4. Exec TF: Volume > SMA(20) (volume filter)
5. HTF: Always true (permissive)

**SHORT:**
1. Exec TF: EMA(9) < EMA(26) (trend)
2. Exec TF: RSI(14) < 50 (momentum)
3. Exec TF: MACD histogram < 0 (confirmation)
4. Exec TF: Volume > SMA(20) (volume filter)
5. HTF: Always true (permissive)

**Exit Logic:**
- Opposite signal (EMA crossover reversal)

**Risk Management:**
- 2x ATR stop loss
- 2:1 R:R take profit
- 0.5% equity risk per trade
- Max 2x leverage

**Timeframes:**
- Exec: 5m (high bar count)
- HTF: 1h (light context)

---

## How to Run

### Step 1: Validate Data Coverage

```bash
python trade_cli.py backtest preflight \
    --idea-card BTCUSDT_5m_stress_test_indicator_dense
```

**Expected output:**
- ✅ 5m and 1h timeframes have sufficient data
- ✅ Warmup requirements met (200 exec bars, 100 HTF bars)
- ✅ No gaps in 60-day range

**If preflight fails:**
- Sync BTCUSDT 5m data via Data Builder

---

### Step 2: Run 60-Day Stress Test

```bash
python trade_cli.py backtest run \
    --idea-card BTCUSDT_5m_stress_test_indicator_dense \
    --start 2024-10-01 \
    --end 2024-11-30 \
    --data-env live
```

**Expected behavior:**
- Completes in < 10 seconds on modern hardware
- Processes ~17,280 bars (5m * 60 days)
- Generates 50-150 trades (high churn)
- No crashes, OOM errors, or performance degradation
- Memory usage stays flat

**Artifacts generated:**
```
backtests/BTCUSDT_5m_stress_test_indicator_dense/BTCUSDT/run-001/
├── trades.parquet          # All trade records
├── equity.parquet          # Equity curve (dense, 5m resolution)
├── result.json             # Metrics summary
├── preflight_report.json   # Data coverage validation
└── pipeline_signature.json # Reproducibility metadata
```

---

### Step 3: Verify Determinism

Run twice and compare:

```bash
# Run 1
python trade_cli.py backtest run \
    --idea-card BTCUSDT_5m_stress_test_indicator_dense \
    --start 2024-10-01 \
    --end 2024-11-30 \
    --data-env live

# Run 2
python trade_cli.py backtest run \
    --idea-card BTCUSDT_5m_stress_test_indicator_dense \
    --start 2024-10-01 \
    --end 2024-11-30 \
    --data-env live

# Compare
diff backtests/BTCUSDT_5m_stress_test_indicator_dense/BTCUSDT/run-001/result.json \
     backtests/BTCUSDT_5m_stress_test_indicator_dense/BTCUSDT/run-002/result.json
```

**Expected output:**
- ✅ No differences
- ✅ Identical trade counts, PnL, timestamps

---

## Success Criteria

### ✅ Pass Conditions

| Check | Expected Result |
|-------|-----------------|
| **Completion** | Finishes without crashes or errors |
| **Bar count** | ~17,280 bars processed (5m * 60 days) |
| **Trade count** | 50-150 trades (high churn) |
| **Memory** | Flat usage throughout run (no leaks) |
| **Artifacts** | All Parquet files written and readable |
| **Determinism** | Repeated runs produce identical results |
| **Indicators** | No NaN errors in trade logs |
| **Performance** | Completes in < 10 seconds |
| **Multi-output** | MACD columns accessible (macd_macd, macd_signal, macd_histogram) |

### ❌ Failure Indicators

| Symptom | Likely Cause | Where to Investigate |
|---------|--------------|----------------------|
| **Crash/OOM** | Memory leak | Array allocation, indicator computation |
| **Zero trades** | Indicator NaN propagation | Warmup settings, rolling window logic |
| **Non-deterministic** | Random state | Indicator computation, array indexing |
| **Missing artifacts** | Parquet writer failure | ArtifactStore, serialization |
| **Indicator NaN errors** | Warmup insufficient | Feature computation, rolling windows |
| **Performance > 10s** | O(n²) hot loop | Snapshot access, indicator computation |
| **MACD column errors** | Multi-output expansion broken | Column naming, FeatureSpec expansion |

---

## What to Check in Artifacts

### 1. result.json

```json
{
  "total_trades": 85,              // Should be 50-150 (high churn)
  "win_rate_pct": 42.0,            // Not relevant (not optimized)
  "max_drawdown_pct": 8.5,         // Should be reasonable (< 30%)
  "final_equity_usdt": 9750.0,     // May be lower (that's OK)
  "runtime_seconds": 4.2,          // MUST be < 10 seconds
  "total_bars": 17280,             // Should be ~17K (60 days * 5m)
  "completed": true                // MUST be true
}
```

### 2. trades.parquet

Check that trades have:
- Valid entry/exit timestamps (5m intervals)
- All indicator values populated (no NaN)
- MACD values present (validates multi-output)
- Short hold durations (minutes to hours, not days)
- Reasonable PnL per trade

```python
import pandas as pd
trades = pd.read_parquet('backtests/.../trades.parquet')
print(trades[['entry_time', 'exit_time', 'direction', 'pnl_usdt', 'hold_duration_minutes']].head(10))
# Check for NaN in indicator columns
print(trades[['rsi', 'atr', 'macd_histogram']].isna().sum())
```

### 3. equity.parquet

Check equity curve:
- Dense resolution (5m intervals)
- Starts at 10,000 USDT
- No sudden jumps or NaN values
- More data points than 1h test (12x more)

---

## When to Run This Test

### Required (Before Merging)

Run this test **before merging** any changes to:
- `src/backtest/engine.py` (hot loop performance)
- `src/backtest/runtime/snapshot.py` (RuntimeSnapshotView)
- `src/backtest/runtime/feed.py` (FeedStore array operations)
- `src/backtest/features/` (indicator computation)
- Array indexing or offset logic

### Optional (Good Practice)

Run this test after:
- Numpy/pandas version updates
- Performance optimizations
- Indicator registry changes
- Memory allocation changes

---

## Interpreting Results

### Expected Trade Characteristics

| Metric | Expected Range | Interpretation |
|--------|----------------|----------------|
| **Total trades** | 50-150 | High churn; < 50 = filters too strict |
| **Avg hold duration** | 10-50 bars (50-250 min) | Short holds validate frequent entry/exit |
| **Win rate** | 30-60% | Not optimized; < 20% = potential bug |
| **Max drawdown** | 5-30% | Unoptimized; > 50% = potential risk bug |
| **Runtime** | < 10 seconds | Performance acceptable |

### Bar Count Validation

```
Expected bars: 60 days * 24 hours/day * 12 bars/hour (5m) = 17,280 bars
Comparison:
- 5m test: 17,280 bars (THIS TEST)
- 15m test: 5,760 bars (3x fewer)
- 1h test: 1,440 bars (12x fewer)
```

This test processes **12x more bars** than the 1h validation test, stressing array operations and snapshot access.

### Trade Frequency Validation

```
Expected: 50-150 trades over 60 days
- ~1-2 trades per day (high churn)
- Avg duration: 10-50 bars (50-250 minutes)
- Much higher frequency than 1h test
```

This validates:
- Frequent indicator evaluation
- Snapshot access under load
- Position management at high frequency

---

## Performance Benchmarks

### Expected Performance (Modern Hardware)

| Hardware | Expected Runtime |
|----------|------------------|
| **i7/Ryzen 7 + 16GB RAM** | < 5 seconds |
| **i5/Ryzen 5 + 8GB RAM** | < 10 seconds |
| **Older hardware** | < 15 seconds |

**If runtime exceeds 10 seconds, investigate:**

1. **DataFrame operations in hot loop** (should be array-only)
   - Check: `RuntimeSnapshotView.get_feature()` implementation
   - Check: `FeedStore` array access patterns

2. **Excessive logging** (should be minimal in hot loop)
   - Check: `BacktestEngine.run()` logging frequency
   - Check: Trade log verbosity

3. **Inefficient indicator computation**
   - Check: Indicator implementation (should use vectorized numpy)
   - Check: Warmup window sizes (excessive warmup = wasted computation)

4. **Snapshot access regression**
   - Check: Caching behavior in RuntimeSnapshotView
   - Check: Array indexing performance

---

## Troubleshooting

### Problem: Zero Trades

**Cause:** Indicator NaN propagation or conditions too strict

**Debug steps:**
1. Check indicator keys are correct:
   ```bash
   python trade_cli.py backtest indicators \
       --idea-card BTCUSDT_5m_stress_test_indicator_dense \
       --print-keys
   ```
2. Verify MACD multi-output expansion:
   - Expected keys: `macd_macd`, `macd_signal`, `macd_histogram`
3. Check logs for indicator NaN warnings
4. Increase warmup bars if indicators not stabilizing

---

### Problem: MACD Column Errors

**Cause:** Multi-output expansion broken or incorrect key names

**Debug steps:**
1. Verify expanded keys in preflight:
   ```bash
   python trade_cli.py backtest preflight \
       --idea-card BTCUSDT_5m_stress_test_indicator_dense
   ```
   Expected output should show:
   - `macd_macd`
   - `macd_signal`
   - `macd_histogram`

2. Check signal rules reference correct keys (e.g., `macd_histogram`, not `macd`)

---

### Problem: Performance > 10 Seconds

**Cause:** O(n²) behavior in hot loop or excessive overhead

**Debug steps:**
1. Profile with `cProfile`:
   ```python
   python -m cProfile -o backtest.prof trade_cli.py backtest run ...
   ```
2. Analyze hotspots:
   ```python
   import pstats
   stats = pstats.Stats('backtest.prof')
   stats.sort_stats('cumulative')
   stats.print_stats(20)
   ```
3. Look for:
   - DataFrame operations in hot loop
   - Repeated indicator recomputation
   - Inefficient array indexing

---

## Comparison: Low-TF vs Long-Horizon Tests

| Aspect | Long-Horizon Test (1y) | Low-TF Stress Test (60d) |
|--------|------------------------|---------------------------|
| **Exec TF** | 15m | 5m |
| **Duration** | 365 days | 60 days |
| **Bar count** | ~35K bars | ~17K bars |
| **Indicators** | 3 (EMA, ATR, RSI) | 6 (EMA, ATR, RSI, MACD, Vol SMA) |
| **Trade freq** | Low (~50/year) | High (~100/60d) |
| **Purpose** | Long-run stability | High-frequency stress |
| **Runtime** | < 5 min | < 10 sec |

**Use both tests:**
- **Long-horizon:** Validates stability over time
- **Low-TF:** Validates performance under load

---

## Related Documentation

- **Long-horizon test:** `docs/guides/SYSTEM_VALIDATION_LONG_HORIZON_TEST.md`
- **IdeaCard YAML Structure:** `docs/reviews/IDEACARD_YAML_STRUCTURE_REVIEW.md`
- **Backtest Engine Architecture:** `docs/architecture/BACKTEST_MODULE_OVERVIEW.md`
- **Array-backed hot loop:** `docs/todos/ARRAY_BACKED_HOT_LOOP_PHASES.md`

---

## Summary

The `BTCUSDT_5m_stress_test_indicator_dense` IdeaCard validates engine performance under:
- **High bar counts** (17K+ bars)
- **Dense indicators** (6 indicators, 9 columns)
- **Frequent access** (high-churn strategy)
- **Multi-output indicators** (MACD expansion)

Run this test before merging hot loop or snapshot changes. If it passes, you have high confidence that performance remains acceptable under load.

**Remember:** This is NOT a trading strategy. It's a performance diagnostic. Profitability is irrelevant; speed and correctness are everything.

