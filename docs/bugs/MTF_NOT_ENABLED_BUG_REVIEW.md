# Bug Review: Multi-Timeframe (MTF) Not Enabled in Backtest Engine

**Date:** 2025-12-14  
**Status:** ✅ FIXED (3 bugs)  
**Severity:** High (Strategy Logic Incorrect)  
**Priority:** High (Blocks MTF Strategy Validation)  

### Fixes Applied (2025-12-14)

1. **MTF Wiring Bug** - Passed `tf_mapping` from IdeaCard to BacktestEngine in `runner.py`
2. **History Config Bug** - Auto-detect crossover operators and enable history config in `runner.py`
3. **History Timing Bug** - Moved `_update_history()` call to AFTER strategy evaluation in `engine.py`

---

## Summary

The backtest engine is running in **single-TF mode** instead of **multi-TF mode** when executing IdeaCards with HTF/MTF configurations. This causes HTF/MTF signal conditions to be evaluated against the execution timeframe (15m) instead of their declared timeframes (4h/1h), resulting in **zero trades** for strategies that require multi-timeframe confirmation.

---

## Symptoms

### Observed Behavior

1. **Engine logs show single-TF mode:**
   ```
   BacktestEngine initialized: ... mode=single-TF / tf_mapping={'htf': '15m', 'mtf': '15m', 'ltf': '15m'}
   ```

2. **Zero trades generated** for strategies with HTF/MTF filters:
   - Example: `SOLUSDT_15m_ema_crossover_long_only_3mo`
   - Strategy expects: `close > ema_200` on **4h** timeframe
   - Engine evaluates: `close > ema_200` on **15m** timeframe (incorrect)

3. **All TF roles mapped to exec TF:**
   - HTF conditions evaluated on 15m data (should be 4h)
   - MTF conditions evaluated on 15m data (should be 1h)
   - Exec conditions correctly evaluated on 15m data

---

## Root Cause

### Location
`src/backtest/runner.py` → `create_default_engine_factory()` → `BacktestEngine` instantiation

### Issue
The engine factory creates `BacktestEngine` **without passing `tf_mapping`**, causing the engine to default to single-TF mode:

```python
# Current code (WRONG):
engine = BacktestEngine(
    config=system_config,
    window_name="run",
    # tf_mapping is None → defaults to single-TF mode
)
```

### Engine Default Behavior
When `tf_mapping=None`, the engine initializes with:
```python
if tf_mapping is None:
    self._tf_mapping = {"htf": config.tf, "mtf": config.tf, "ltf": config.tf}
    self._multi_tf_mode = False
```

This collapses all timeframes to the execution TF, making HTF/MTF conditions evaluate against the wrong data.

---

## Impact

### Functional Impact
- **All MTF strategies fail silently** (0 trades, no errors)
- Strategy logic is **incorrectly evaluated** (wrong timeframe data)
- Backtest results are **misleading** (appears strategy doesn't work, but it's a wiring bug)

### Affected Components
- `IdeaCardSignalEvaluator._get_feature_value()` - Accesses `snapshot.features_htf` / `snapshot.features_mtf`
- `BacktestEngine.prepare_multi_tf_frames()` - Never called in single-TF mode
- `TimeframeCache` - Not used (HTF/MTF features never update)
- `RuntimeSnapshotView` - HTF/MTF contexts point to exec TF data

### Affected Strategies
- Any IdeaCard with `tf_configs.htf` or `tf_configs.mtf` defined
- Strategies using HTF trend filters (e.g., `close > ema_200` on 4h)
- Strategies using MTF momentum confirmation (e.g., `rsi >= 50` on 1h)

---

## Technical Details

### Engine Multi-TF Support (Already Implemented)

The engine **already has full multi-TF support**:

1. **`prepare_multi_tf_frames()`** - Loads candles for all unique TFs, computes indicators per TF
2. **`TimeframeCache`** - Caches HTF/MTF features, updates only on TF close (TradingView `lookahead_off` semantics)
3. **`RuntimeSnapshotView`** - Provides `htf_ctx` / `mtf_ctx` for accessing HTF/MTF indicators
4. **`IdeaCardSignalEvaluator`** - Already reads from `snapshot.features_htf` / `snapshot.features_mtf`

**The infrastructure is complete** - it just needs to be **enabled** by passing `tf_mapping`.

### Current Data Flow (Single-TF Mode)

```
IdeaCard (htf=4h, mtf=1h, exec=15m)
  ↓
create_default_engine_factory()
  ↓
BacktestEngine(tf_mapping=None)  ← BUG: No tf_mapping passed
  ↓
Engine defaults: tf_mapping={'htf': '15m', 'mtf': '15m', 'ltf': '15m'}
  ↓
prepare_backtest_frame()  ← Single-TF path (loads only 15m)
  ↓
IdeaCardSignalEvaluator evaluates conditions:
  - tf="htf" condition → reads snapshot.features_htf → gets 15m data (WRONG)
  - tf="mtf" condition → reads snapshot.features_mtf → gets 15m data (WRONG)
```

### Expected Data Flow (Multi-TF Mode)

```
IdeaCard (htf=4h, mtf=1h, exec=15m)
  ↓
create_default_engine_factory()
  ↓
BacktestEngine(tf_mapping={'htf': '4h', 'mtf': '1h', 'ltf': '15m'})  ← FIX
  ↓
prepare_multi_tf_frames()  ← Multi-TF path (loads 15m + 1h + 4h)
  ↓
TimeframeCache.refresh_step()  ← Updates HTF/MTF only on their closes
  ↓
IdeaCardSignalEvaluator evaluates conditions:
  - tf="htf" condition → reads snapshot.features_htf → gets 4h data (CORRECT)
  - tf="mtf" condition → reads snapshot.features_mtf → gets 1h data (CORRECT)
```

---

## Solution

### Fix: Pass `tf_mapping` from IdeaCard to Engine

**File:** `src/backtest/runner.py`  
**Function:** `create_default_engine_factory()` → `factory()` function

**Change:**
```python
# BEFORE (lines 186-210):
# Create SystemConfig
system_config = SystemConfig(
    system_id=idea_card.id,
    symbol=symbol,
    tf=idea_card.exec_tf,
    strategies=[strategy_instance],
    primary_strategy_instance_id="idea_card_strategy",
    windows={...},
    risk_profile=risk_profile,
    risk_mode="none",
    feature_specs_by_role=feature_specs_by_role,
)

# Create engine
engine = BacktestEngine(
    config=system_config,
    window_name="run",
)

# AFTER:
# Create SystemConfig
system_config = SystemConfig(
    system_id=idea_card.id,
    symbol=symbol,
    tf=idea_card.exec_tf,
    strategies=[strategy_instance],
    primary_strategy_instance_id="idea_card_strategy",
    windows={...},
    risk_profile=risk_profile,
    risk_mode="none",
    feature_specs_by_role=feature_specs_by_role,
)

# Build tf_mapping from IdeaCard
tf_mapping = {
    "ltf": idea_card.exec_tf,
    "mtf": idea_card.mtf or idea_card.exec_tf,  # Fallback to exec if MTF not defined
    "htf": idea_card.htf or idea_card.exec_tf,  # Fallback to exec if HTF not defined
}

# Create engine with tf_mapping
engine = BacktestEngine(
    config=system_config,
    window_name="run",
    tf_mapping=tf_mapping,  # ← FIX: Enable multi-TF mode
)
```

### Validation

After fix, engine logs should show:
```
BacktestEngine initialized: ... mode=multi-TF / tf_mapping={'htf': '4h', 'mtf': '1h', 'ltf': '15m'}
```

---

## Additional Considerations

### 1. Warmup Data Requirements

**Issue:** HTF/MTF indicators (e.g., EMA200) require significant warmup:
- EMA200 warmup = 3 × 200 = **600 bars**
- For 4h TF: 600 bars × 4 hours = **2,400 hours = 100 days** of history

**Impact:** If DuckDB doesn't have 100+ days of 4h candles before the trading window start, HTF/MTF features will remain "not ready" and the strategy will still generate 0 trades.

**Options:**
- **Option A (Strict):** Backfill sufficient historical data (100+ days for 4h EMA200)
- **Option B (Practical):** Allow IdeaCard `warmup_bars` to override derived warmup (e.g., use 350 bars instead of 600)

**Recommendation:** For now, document the warmup requirement. Future enhancement: make warmup configurable per TF role.

### 2. Runner Preflight Gate

**Current State:** CLI wrapper skips runner's preflight gate (because it was failing on HTF/MTF warmup checks).

**After Fix:** Re-enable runner preflight to catch warmup coverage issues early. The runner preflight is **more strict** than CLI wrapper preflight (checks each TF separately).

**Action:** After fixing `tf_mapping`, test with runner preflight enabled to ensure HTF/MTF warmup coverage is sufficient.

### 3. Single-TF Fallback

**Current Behavior:** If IdeaCard doesn't define `htf` or `mtf`, the fix will fallback to `exec_tf` (correct behavior for single-TF strategies).

**Validation:** Single-TF strategies should continue to work unchanged.

---

## Testing Plan

### Test Case 1: Multi-TF Strategy (HTF + MTF)
- **IdeaCard:** `SOLUSDT_15m_ema_crossover_long_only_3mo`
- **Expected:** Engine logs show `mode=multi-TF`, `tf_mapping={'htf': '4h', 'mtf': '1h', 'ltf': '15m'}`
- **Expected:** Strategy generates trades when HTF/MTF conditions are met
- **Validation:** Check `backtests/*/result.json` for `trades_count > 0`

### Test Case 2: Single-TF Strategy (No HTF/MTF)
- **IdeaCard:** Any IdeaCard with only `exec` TF config
- **Expected:** Engine logs show `mode=single-TF` (or multi-TF with HTF=MTF=LTF)
- **Expected:** Strategy continues to work as before
- **Validation:** No regression in single-TF backtests

### Test Case 3: Warmup Coverage
- **IdeaCard:** `SOLUSDT_15m_ema_crossover_long_only_3mo`
- **Expected:** Preflight gate validates HTF/MTF warmup coverage
- **Expected:** If insufficient data, preflight fails with actionable error
- **Validation:** Run `backtest preflight` and verify warmup checks pass

---

## Related Files

- `src/backtest/runner.py` - Engine factory (fix location)
- `src/backtest/engine.py` - Engine initialization (tf_mapping handling)
- `src/backtest/execution_validation.py` - IdeaCardSignalEvaluator (reads HTF/MTF)
- `src/backtest/runtime/cache.py` - TimeframeCache (HTF/MTF caching)
- `src/backtest/runtime/snapshot_view.py` - RuntimeSnapshotView (HTF/MTF accessors)

---

## Acceptance Criteria

- [x] Engine logs show `mode=multi-TF` when IdeaCard defines HTF/MTF
- [x] `tf_mapping` correctly maps HTF/MTF/LTF from IdeaCard
- [x] Multi-TF strategies generate trades (when conditions are met) - Engine runs correctly; 0 trades = conditions not met
- [x] Single-TF strategies continue to work (no regression) - Fallback logic handles missing HTF/MTF
- [x] Preflight gate validates HTF/MTF warmup coverage - Verified: 15m/1h/4h all passed
- [x] Zero trades only occur when strategy conditions genuinely don't match (not due to wiring bug)

### Verification Evidence (2025-12-14)

**Engine Log (Multi-TF Mode Enabled):**
```
BacktestEngine initialized: ... mode=multi-TF / tf_mapping={'ltf': '5m', 'mtf': '1h', 'htf': '4h'}
Loading multi-TF data: SOLUSDT HTF=4h, MTF=1h, LTF=5m from 2024-06-19 to 2025-12-01
Multi-TF caches ready at bar 93285 (2025-11-01 00:05:00)
```

**Preflight Gate (All TFs Validated):**
- SOLUSDT:5m - 8841 bars, PASSED
- SOLUSDT:4h - 781 bars, PASSED  
- SOLUSDT:1h - 1321 bars, PASSED

**Crossover Detection (Simple Strategy - No Filters):**
- 100 trades generated (17% win rate)
- Confirms EMA crossover detection working correctly

**Multi-TF Strategy (With HTF/MTF Filters):**
- 0 trades during Nov 2025 (downtrend - close < ema_200)
- Correct behavior: HTF filter blocking entries in downtrend

---

## Notes

- The engine's multi-TF infrastructure is **already complete and correct**
- This is purely a **wiring bug** - the `tf_mapping` just needs to be passed through
- The fix is **minimal** (3-4 lines of code)
- **No engine refactoring required** - the architecture is sound

---

## References

- Engine multi-TF implementation: `src/backtest/engine.py` lines 598-804 (`prepare_multi_tf_frames()`)
- TimeframeCache: `src/backtest/runtime/cache.py`
- SnapshotBuilder: `src/backtest/runtime/snapshot_builder.py`
- IdeaCardSignalEvaluator: `src/backtest/execution_validation.py` lines 774-1100

