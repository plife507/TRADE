# MTF History Warmup Bug Fix

## Status: ✅ COMPLETE

## Bug Description

**Symptom**: MTF backtests generated 0 trades while identical single-TF strategies generated 69 trades.

**Root Cause**: In `src/backtest/engine.py`, the warmup loop (lines 1020-1026) was NOT calling `_update_history()`, so history windows were never populated during warmup. When simulation started, `_is_history_ready()` returned `False`, causing `snapshot.ready` to be `False` for every bar. The readiness gate blocked all trading.

## Investigation Path

1. Verified MTF data loading worked (close_ts maps populated correctly)
2. Verified TimeframeCache populated correctly during warmup
3. Found `snapshot.ready` was `False` with reason: "History: required windows not yet filled"
4. Traced to `_update_history()` not being called during warmup
5. Crossover conditions (`cross_above`, `cross_below`) trigger history requirements in `runner.py`

## Fix Applied

**File**: `src/backtest/engine.py`
**Location**: Warmup loop (around line 1020)

**Before**:
```python
if i < sim_start_idx:
    if self._multi_tf_mode:
        self._refresh_tf_caches(bar.ts_close, bar)
    prev_bar = bar
    continue
```

**After**:
```python
if i < sim_start_idx:
    # Refresh TF caches
    htf_updated_warmup = False
    mtf_updated_warmup = False
    if self._multi_tf_mode:
        htf_updated_warmup, mtf_updated_warmup = self._refresh_tf_caches(bar.ts_close, bar)
    
    # Also update history during warmup (for crossover detection)
    warmup_features = {}
    ohlcv_cols = {"timestamp", "open", "high", "low", "close", "volume"}
    for col in row.index:
        if col not in ohlcv_cols and pd.notna(row[col]):
            try:
                warmup_features[col] = float(row[col])
            except (ValueError, TypeError):
                pass
    
    warmup_features_exec = FeatureSnapshot(...)
    
    self._update_history(
        bar=bar,
        features_exec=warmup_features_exec,
        htf_updated=htf_updated_warmup,
        mtf_updated=mtf_updated_warmup,
        features_htf=self._tf_cache.get_htf() if self._multi_tf_mode else None,
        features_mtf=self._tf_cache.get_mtf() if self._multi_tf_mode else None,
    )
    
    prev_bar = bar
    continue
```

## Verification

**Test Command**:
```bash
python trade_cli.py backtest run --idea-card BTCUSDT_1h_ema_crossover_mtf --start 2024-12-01 --end 2025-12-14
```

**Results**:
- MTF without HTF filter: 69 trades (same as single-TF)
- MTF with HTF filter: 44 trades (HTF trend filter working)

## Impact

- All MTF backtests now generate trades correctly
- History windows populated during warmup
- Crossover detection works from sim_start
- No changes to single-TF backtests (behavior preserved)

## Date: 2025-12-14

