# Low-TF Stress Test IdeaCard - Delivery Summary

**Date:** 2025-12-16  
**Objective:** Create a TEST-ONLY IdeaCard to stress-test engine and snapshot plumbing at low timeframe

---

## 📦 Deliverables

### 1. **IdeaCard** (Main Artifact)
```
configs/idea_cards/BTCUSDT_5m_stress_test_indicator_dense.yml
```

A diagnostic stress test IdeaCard that:
- Runs 60-day backtests on BTCUSDT perpetual at **5m timeframe**
- Exercises array-backed hot loop with **~17K+ bars** (12x more than 1h test)
- Tests **6 indicators** (9 output columns including MACD multi-output)
- Uses **high-churn strategy** to maximize indicator evaluation frequency
- **Requires NO code changes** (uses existing features only)

### 2. **Full Documentation**
```
docs/guides/SYSTEM_VALIDATION_LOW_TF_STRESS_TEST.md
```

Comprehensive guide covering:
- What components are stress-tested
- Performance benchmarks (< 10 second target)
- Troubleshooting guide
- Multi-output indicator validation
- Comparison with long-horizon test

---

## 🎯 What This Test Validates

| Component | Test Coverage | Stress Factor |
|-----------|---------------|---------------|
| **Array-backed hot loop** | 17,280 bars (5m * 60 days) | 12x more than 1h test |
| **RuntimeSnapshotView** | Frequent indicator access | High-churn strategy |
| **Dense indicators** | 6 indicators, 9 output columns | 2x more than baseline |
| **Multi-output expansion** | MACD → 3 columns | Column naming & access |
| **Rolling windows** | Updates every 5 minutes | 12x faster than 1h |
| **Memory efficiency** | Dense indicator sets | Allocation patterns |
| **Determinism** | Identical results | Floating-point stability |

---

## 🔧 Technical Specifications

### Timeframe Configuration

| Role | TF | Bars (60d) | Purpose |
|------|----|-----------| --------|
| **Exec** | 5m | 17,280 | Entry/exit signals (stress test) |
| **HTF** | 1h | 1,440 | Light trend context |

**Hierarchy:** HTF (1h) > Exec (5m) ✅

### Indicator Set (Dense)

**Exec TF (5m):**
1. EMA(9) - Fast trend
2. EMA(26) - Slow trend
3. RSI(14) - Momentum
4. ATR(14) - Volatility
5. MACD(12,26,9) → 3 columns:
   - `macd_macd`
   - `macd_signal`
   - `macd_histogram`
6. Volume SMA(20) - Volume filter

**HTF (1h):**
1. EMA(50) - Trend bias

**Total:** 6 indicators, 9 output columns

### Strategy Logic (High-Churn)

**Entry:**
- **LONG:** `ema_fast > ema_slow` AND `rsi > 50` AND `macd_histogram > 0` AND `volume > volume_sma`
- **SHORT:** `ema_fast < ema_slow` AND `rsi < 50` AND `macd_histogram < 0` AND `volume > volume_sma`

**Exit:**
- Opposite signal (frequent reversals)

**Expected Behavior:**
- 50-150 trades over 60 days (~1-2 per day)
- Short hold durations (10-50 bars = 50-250 minutes)
- Maximize indicator evaluation frequency

---

## 🚀 How to Use

### Step 1: Sync 5m Data (First Time Only)

```bash
python trade_cli.py
# Select: Data Builder
# Sync BTCUSDT OHLCV for 5m timeframe
# Date range: 2024-10-01 to 2024-11-30 (or later)
```

### Step 2: Validate IdeaCard Structure

```bash
python trade_cli.py backtest indicators \
    --idea-card BTCUSDT_5m_stress_test_indicator_dense \
    --print-keys
```

**Expected output:**
```
Expanded Keys:
  exec: ['atr', 'ema_fast', 'ema_slow', 'macd_histogram', 
         'macd_macd', 'macd_signal', 'rsi', 'volume_sma']
  htf: ['ema_trend']

OK Found 9 indicator keys across 2 TF roles
```

✅ **MACD multi-output expansion verified:** `macd` → 3 columns

### Step 3: Check Data Coverage

```bash
python trade_cli.py backtest preflight \
    --idea-card BTCUSDT_5m_stress_test_indicator_dense
```

**Expected output:**
- ✅ 5m and 1h timeframes have sufficient data
- ✅ Warmup requirements met (200 exec bars, 100 HTF bars)

### Step 4: Run Stress Test

```bash
python trade_cli.py backtest run \
    --idea-card BTCUSDT_5m_stress_test_indicator_dense \
    --start 2024-10-01 \
    --end 2024-11-30 \
    --data-env live
```

**Expected results:**
- ✅ Completes in < 10 seconds
- ✅ Processes ~17,280 bars
- ✅ Generates 50-150 trades
- ✅ No crashes or memory leaks
- ✅ All Parquet artifacts written

---

## ✅ Success Criteria

### Pass Conditions

| Check | Expected Result |
|-------|-----------------|
| **Completion** | No crashes over 17K+ bars |
| **Trade count** | 50-150 trades (high churn) |
| **Memory** | Flat usage (no leaks) |
| **Artifacts** | All Parquet files written |
| **Determinism** | Repeated runs match exactly |
| **Indicators** | No NaN errors in trade logs |
| **Performance** | Runtime < 10 seconds |
| **MACD columns** | All 3 columns accessible |

### Fail Indicators

| Symptom | Likely Cause |
|---------|--------------|
| **Crash/OOM** | Memory leak in array/indicator layer |
| **Zero trades** | Indicator NaN propagation issue |
| **Non-deterministic** | Floating-point instability |
| **Missing artifacts** | Parquet writer failure |
| **Performance > 10s** | O(n²) hot loop behavior |
| **MACD errors** | Multi-output expansion broken |

---

## 📊 Expected Results

### Performance Benchmarks

| Hardware | Expected Runtime |
|----------|------------------|
| **Modern (i7, 16GB)** | < 5 seconds ⚡ |
| **Mid-range (i5, 8GB)** | < 10 seconds |
| **Older hardware** | < 15 seconds |

### Trade Characteristics

| Metric | Expected Range |
|--------|----------------|
| **Total trades** | 50-150 |
| **Trade frequency** | 1-2 per day |
| **Avg hold** | 10-50 bars (50-250 min) |
| **Win rate** | 30-60% (not optimized) |
| **Max DD** | 5-30% (diagnostic test) |

### Bar Count Validation

```
60 days * 24 hours * 12 bars/hour (5m) = 17,280 bars

Comparison:
- 5m stress test: 17,280 bars (THIS TEST)
- 15m validation: 5,760 bars (3x fewer)
- 1h validation: 1,440 bars (12x fewer)
```

**Stress factor:** 12x more bars than 1h test

---

## 🧪 When to Run This Test

### Required (Before Merging)

Run before merging changes to:
- `src/backtest/engine.py` (hot loop performance)
- `src/backtest/runtime/snapshot.py` (RuntimeSnapshotView)
- `src/backtest/runtime/feed.py` (FeedStore arrays)
- `src/backtest/features/` (indicator computation)
- Array indexing or offset logic

### Optional (Good Practice)

Run after:
- Numpy/pandas version updates
- Performance optimizations
- Memory allocation changes
- Indicator registry changes

---

## 📝 Validation Status

### IdeaCard Structure: ✅ VALIDATED

```bash
# Ran: python trade_cli.py backtest indicators --print-keys
# Result: ✅ PASS
# - 9 indicator keys discovered (6 indicators, MACD multi-output = 3 columns)
# - All required keys present in expanded list
# - MACD expansion correct: macd_macd, macd_signal, macd_histogram
```

### Data Availability: ⚠️ NEEDS SYNC

```
Status: 5m data not yet synced
Action: User must sync BTCUSDT 5m data via Data Builder
Command: python trade_cli.py → Data Builder → Sync OHLCV 5m
```

### Test Execution: ⏳ PENDING

```
Blocked by: 5m data sync
When ready: Run commands in "How to Use" section above
```

---

## 🔄 Comparison: Two Validation Tests

| Aspect | Long-Horizon Test | Low-TF Stress Test |
|--------|-------------------|--------------------|
| **File** | `BTCUSDT_1h_system_validation_1year.yml` | `BTCUSDT_5m_stress_test_indicator_dense.yml` |
| **Exec TF** | 15m | 5m |
| **Duration** | 365 days | 60 days |
| **Bar count** | ~35K | ~17K |
| **Indicators** | 3 (EMA, ATR, RSI) | 6 (EMA, ATR, RSI, MACD, Vol SMA) |
| **Multi-output** | No | Yes (MACD → 3 cols) |
| **Trade freq** | Low (~50/year) | High (~100/60d) |
| **Purpose** | Long-run stability | High-frequency stress |
| **Runtime** | < 5 min | < 10 sec |
| **Stress factor** | Time (1 year) | Frequency (5m updates) |

**Use both tests for comprehensive validation:**
1. **Long-horizon:** Validates stability over extended periods
2. **Low-TF stress:** Validates performance under high bar counts

---

## 🎓 Key Learnings

### Multi-Output Indicator Expansion

The IdeaCard successfully demonstrates multi-output indicator handling:

**Declaration (in YAML):**
```yaml
- indicator_type: "macd"
  output_key: "macd"
  params:
    fast: 12
    slow: 26
    signal: 9
  input_source: "close"
```

**Expansion (by system):**
- `macd` → `macd_macd`, `macd_signal`, `macd_histogram`

**Usage (in signal rules):**
```yaml
- tf: "exec"
  indicator_key: "macd_histogram"  # Use expanded key
  operator: "gt"
  value: 0
```

**Validation:**
```bash
python trade_cli.py backtest indicators --print-keys
# Shows expanded keys: macd_histogram, macd_macd, macd_signal
```

---

## 🚨 Important Notes

1. **This is NOT a trading strategy** - It's a performance diagnostic
2. **Profitability doesn't matter** - Speed and correctness are the only goals
3. **Trade count matters** - Zero trades = broken indicator logic
4. **Performance matters** - Runtime > 10s = hot loop regression
5. **5m data required** - Must sync before running test

---

## 📚 Documentation Package

| File | Purpose |
|------|---------|
| `configs/idea_cards/BTCUSDT_5m_stress_test_indicator_dense.yml` | IdeaCard definition |
| `docs/guides/SYSTEM_VALIDATION_LOW_TF_STRESS_TEST.md` | Full guide |
| `LOW_TF_STRESS_TEST_DELIVERY.md` | This file (delivery summary) |

---

## 🎯 Next Steps

1. **Sync 5m data** via Data Builder for 2024-10-01 to 2024-11-30
2. **Run preflight** to verify data coverage
3. **Run stress test** and verify performance < 10 seconds
4. **Verify determinism** by running twice and comparing
5. **Use as regression test** before merging hot loop changes

---

## 🎉 Summary

The `BTCUSDT_5m_stress_test_indicator_dense` IdeaCard is **READY** and **VALIDATED** (structure).

**What's complete:**
- ✅ IdeaCard YAML structure
- ✅ Multi-output MACD expansion
- ✅ Indicator key validation
- ✅ Signal rule syntax
- ✅ Documentation

**What's pending:**
- ⏳ 5m data sync (user action required)
- ⏳ Test execution (blocked by data)

**When data is ready, this test will:**
- Process 17K+ bars in < 10 seconds
- Stress-test array operations and snapshot access
- Validate 6 indicators (9 columns) under load
- Serve as a performance regression canary

**Use this test alongside the long-horizon test for comprehensive validation of architectural changes.**

---

**Delivered:** 2025-12-16  
**IdeaCard ID:** `BTCUSDT_5m_stress_test_indicator_dense`  
**Version:** 1.0.0  
**Status:** ✅ **READY (pending data sync)**

