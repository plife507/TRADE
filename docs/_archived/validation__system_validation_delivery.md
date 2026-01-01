# System Validation IdeaCard - Delivery Package

**Objective:** TEST-ONLY IdeaCard to validate architectural changes over 1-year horizons

---

## 📦 What Was Delivered

### 1. **IdeaCard** (Main Artifact)
```
configs/idea_cards/BTCUSDT_1h_system_validation_1year.yml
```

A diagnostic backtest IdeaCard that:
- Runs 1-year backtests on BTCUSDT perpetual
- Exercises array-backed engine, RuntimeSnapshotView, MTF routing, Parquet artifacts
- Uses simple trend-following logic (intentionally unoptimized)
- Generates ~10-30 trades/year across multiple regimes
- **Requires NO code changes** (uses existing features only)

### 2. **Full Documentation**
```
docs/guides/SYSTEM_VALIDATION_LONG_HORIZON_TEST.md
```

Comprehensive guide covering:
- What components are tested
- Success/failure criteria
- Troubleshooting guide
- Artifact interpretation
- Baseline regression testing workflow

### 3. **Quick Start Guide**
```
docs/guides/SYSTEM_VALIDATION_QUICKSTART.md
```

Three-command validation workflow for rapid testing.

### 4. **Delivery Summary**
```
docs/project/SYSTEM_VALIDATION_IDEACARD_DELIVERY.md
```

Technical design documentation and integration guidance.

---

## 🚀 Quick Start (3 Commands)

### Prerequisites
Ensure you have BTCUSDT data for 2024:
```bash
python trade_cli.py
# Data Builder → Sync BTCUSDT OHLCV for 2024-01-01 to 2024-12-31
# Ensure 15m, 1h, and 4h timeframes are synced
```

### Run Test

```bash
# 1. Validate IdeaCard structure
python trade_cli.py backtest indicators \
    --idea BTCUSDT_1h_system_validation_1year \
    --print-keys

# 2. Check data coverage
python trade_cli.py backtest preflight \
    --idea BTCUSDT_1h_system_validation_1year

# 3. Run 1-year backtest
python trade_cli.py backtest run \
    --idea BTCUSDT_1h_system_validation_1year \
    --start 2024-01-01 \
    --end 2024-12-31 \
    --env live
```

**Expected:** Completes in < 5 minutes, generates 10-30 trades, no crashes.

---

## ✅ Success Criteria

### Pass Conditions
- ✅ Completes without errors over 8,760+ hours
- ✅ Memory usage stays flat (no leaks)
- ✅ All Parquet artifacts written correctly
- ✅ MTF values forward-fill correctly
- ✅ Results are deterministic (repeated runs match)
- ✅ No alignment errors between exec/HTF/MTF

### Fail Indicators
- ❌ Crashes or OOM errors → Memory leak
- ❌ Zero trades → MTF alignment broken
- ❌ Non-deterministic results → Random state bug
- ❌ Missing artifacts → Parquet writer failure
- ❌ MTF value errors → Forward-fill logic broken

---

## 🎯 What This Test Validates

| Component | What's Tested |
|-----------|---------------|
| **Array-backed engine** | Stability over 8,760+ hours |
| **RuntimeSnapshotView** | O(1) access with deep history lookbacks |
| **MTF routing** | 15m/1h/4h alignment and forward-fill |
| **Parquet artifacts** | trades/equity/result.json generation |
| **Memory stability** | No leaks over long runs |
| **Determinism** | Same inputs → same outputs |

---

## 🔧 Technical Details

### Strategy (Intentionally Simple)

**Entry:**
- **LONG:** Fast EMA crosses above slow EMA + price above HTF trend + MTF RSI > 40
- **SHORT:** Fast EMA crosses below slow EMA + price below HTF trend + MTF RSI < 60

**Exit:**
- Opposite signal (EMA crossover reversal)

**Risk:**
- 2x ATR stop loss
- 2:1 R:R take profit
- 1% equity risk per trade
- Max 2x leverage

**Timeframes:**
- Exec: 1h (entry/exit signals)
- HTF: 4h (trend filter)
- MTF: 15m (momentum confirmation)

### Why This Design?

This simple strategy:
- Generates trades across multiple regimes
- Holds positions long enough to test long-run behavior
- Avoids edge-case complexity
- **May lose money** (profitability is irrelevant)

---

## 🧪 When to Run This Test

### Required (Pre-Merge)

Run before merging changes to:
- `src/backtest/engine.py` (orchestrator)
- `src/backtest/runtime/` (snapshot/feed/TFContext)
- `src/backtest/sim/` (simulated exchange)
- `src/backtest/features/` (indicators)
- Artifact serialization (Parquet writers)
- Timeframe alignment logic

### Optional (Good Practice)

Run after:
- Major refactors in shared utilities
- DuckDB schema changes
- Dependency updates (pandas, numpy, polars)
- Performance optimizations

---

## 📊 Expected Results

### Trade Characteristics

| Metric | Expected Range |
|--------|----------------|
| **Total trades** | 10-30 |
| **Avg hold duration** | 2-10 days |
| **Win rate** | 30-60% (not optimized) |
| **Max drawdown** | 5-30% (not optimized) |
| **Runtime** | < 5 minutes |

### Key Points

- **Profitability doesn't matter** (this is a diagnostic, not a trading strategy)
- **Trade count > 0** (signals work)
- **Deterministic results** (no random state)
- **Valid artifacts** (Parquet writers work)

---

## 🔍 Verify Determinism

Run twice and compare:

```bash
# Run 1
python trade_cli.py backtest run \
    --idea BTCUSDT_1h_system_validation_1year \
    --start 2024-01-01 --end 2024-12-31 --env live

# Run 2
python trade_cli.py backtest run \
    --idea BTCUSDT_1h_system_validation_1year \
    --start 2024-01-01 --end 2024-12-31 --env live

# Compare artifacts (should be identical)
diff backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-001/result.json \
     backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-002/result.json
```

**Expected:** No differences.

---

## 📝 Check Artifacts

```bash
ls -lh backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-001/

# Expected files:
# - trades.parquet          (all trade records)
# - equity.parquet          (equity curve over time)
# - result.json             (metrics summary)
# - preflight_report.json   (data coverage validation)
# - pipeline_signature.json (reproducibility metadata)
```

Inspect trades:
```python
import pandas as pd
trades = pd.read_parquet('backtests/BTCUSDT_1h_system_validation_1year/BTCUSDT/run-001/trades.parquet')
print(trades[['entry_time', 'exit_time', 'direction', 'pnl_usdt']].head(10))
```

---

## 🚨 Important Notes

### This is NOT a Trading Strategy

- **DO NOT** use this IdeaCard for live trading
- **DO NOT** optimize parameters
- **DO NOT** expect profitability

### This is a Canary Test

If this test breaks:
1. **DO NOT** modify the IdeaCard to make it pass
2. **DO** investigate the root cause
3. **FIX** the underlying bug, not the test

### No Code Changes Required

This IdeaCard uses:
- ✅ Existing RuntimeSnapshotView features
- ✅ Existing indicators in IndicatorRegistry
- ✅ Existing signal operators
- ✅ Existing Parquet artifact format

**No engine, schema, or validator changes needed.**

---

## 📚 Documentation Index

| File | Purpose |
|------|---------|
| `configs/idea_cards/BTCUSDT_1h_system_validation_1year.yml` | IdeaCard definition |
| `docs/guides/SYSTEM_VALIDATION_LONG_HORIZON_TEST.md` | Full guide |
| `docs/guides/SYSTEM_VALIDATION_QUICKSTART.md` | Quick start commands |
| `docs/project/SYSTEM_VALIDATION_IDEACARD_DELIVERY.md` | Technical delivery summary |

---

## 🎉 Summary

You now have a **diagnostic backtest IdeaCard** that validates:
- Array-backed engine stability over 1-year horizons
- RuntimeSnapshotView correctness with deep history lookbacks
- MTF routing and forward-fill behavior
- Parquet artifact generation
- Memory stability and determinism

**Run this test before merging architectural changes to catch bugs early.**

---

## Questions?

See full documentation in:
- `docs/guides/SYSTEM_VALIDATION_LONG_HORIZON_TEST.md` (comprehensive guide)
- `docs/guides/SYSTEM_VALIDATION_QUICKSTART.md` (quick reference)

---

**Delivered:** 2025-12-16  
**IdeaCard ID:** `BTCUSDT_1h_system_validation_1year`  
**Version:** 1.0.0

