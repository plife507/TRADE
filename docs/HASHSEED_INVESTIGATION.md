# PYTHONHASHSEED Non-Determinism Investigation

## Problem Statement

Backtest results are **non-deterministic** across runs when `PYTHONHASHSEED` is not pinned to 0.
Python 3.12 randomizes `hash()` seeds per-process for security. This means `set` iteration
order varies between invocations. Somewhere in the backtest engine pipeline, code depends on
set iteration order, causing different trade sequences and trade hashes between runs.

## Evidence (Before Fix)

With `PYTHONHASHSEED` unset (random), the same play produces different results:
```
Run 1: 312 trades, hash 599ed4e9, PnL -703.75
Run 2: 299 trades, hash 8225f576, PnL -659.75
Run 3: 311 trades, hash ce8b058e, PnL -682.00
```

With `PYTHONHASHSEED=0` (fixed), results are perfectly stable:
```
Run 1: 299 trades, hash 8225f576, PnL -659.75
Run 2: 299 trades, hash 8225f576, PnL -659.75
Run 3: 299 trades, hash 8225f576, PnL -659.75
```

## Band-Aid Fix (Now Removable)

`PYTHONHASHSEED=0` and `PYTHONDONTWRITEBYTECODE=1` added to `.venv-linux/bin/activate`.

---

## Root Cause Analysis (2026-02-25)

The root cause was `set` → `list()` conversions being passed to `generate_synthetic_candles()`.
The synthetic data generator uses a **shared RNG** (seeded with `seed=42`) that processes
timeframes sequentially. When the TF order changed due to set iteration randomization,
each TF consumed different random draws, producing different price data.

### Fix 1 (CRITICAL): `FeatureRegistry.get_all_tfs()` — set → sorted list

- **File**: `src/backtest/feature_registry.py:311-313`
- **Before**: `return set(self._by_tf.keys())`
- **After**: `return sorted(self._by_tf.keys())`
- **Also**: Updated return type annotation `set[str]` → `list[str]`
- **Also**: Updated `Play.get_all_tfs()` wrapper in `play.py` to match
- **Also**: Fixed `preflight.py` caller that used `.add()` on the result (converted to `set()` wrapper with `sorted()` iteration)

### Fix 2 (CRITICAL): `runner.py` — `list(required_tfs)` → `sorted(required_tfs)`

- **File**: `src/backtest/runner.py:185`
- **Before**: `timeframes=list(required_tfs)` where `required_tfs` is a `set`
- **After**: `timeframes=sorted(required_tfs)`

### Fix 3 (CRITICAL — actual CLI root cause): `backtest.py` CLI handler

- **File**: `src/cli/subcommands/backtest.py:88`
- **Before**: `timeframes=list(required_tfs)` where `required_tfs` is a `set`
- **After**: `timeframes=sorted(required_tfs)`
- **Note**: The CLI handler builds its own synthetic data *before* passing to the runner.
  The investigation doc originally missed this as a separate call site.

### Fix 4 (DEFENSIVE): `backtest_play_tools.py` — same pattern

- **File**: `src/tools/backtest_play_tools.py:530`
- **Before**: `timeframes=list(required_tfs)`
- **After**: `timeframes=sorted(required_tfs)`

### Fix 5 (DEFENSIVE): `forge_menu.py` — same pattern

- **File**: `src/cli/menus/forge_menu.py:292`
- **Before**: `timeframes=list(required_tfs)`
- **After**: `timeframes=sorted(required_tfs)`

### Verified Safe (No Fix Needed)

- `play_engine.py` indicator dict iteration (lines 937, 974, 1003, 1014) — dicts are built
  from deterministic `indicator_columns` list, so insertion order is stable
- `cache.py` close timestamp sets — only used for `in` membership tests, never iterated
- `engine_data_prep.py` tf_mapping — built from YAML (deterministic), `close_ts_maps` values
  are `set[datetime]` but only used for membership tests
- `engine_factory.py:273` — already used `sorted(required_tfs)` before this fix
- All other `generate_synthetic_candles` call sites use literal lists or `sorted()`

---

## Verification (After Fix)

5 runs with different PYTHONHASHSEED values, all produce identical results:
```
SEED=1: 312 trades, hash 599ed4e9, PnL -703.75
SEED=2: 312 trades, hash 599ed4e9, PnL -703.75
SEED=3: 312 trades, hash 599ed4e9, PnL -703.75
SEED=4: 312 trades, hash 599ed4e9, PnL -703.75
SEED=5: 312 trades, hash 599ed4e9, PnL -703.75
```

---

## Fix Plan Status

### Phase 1: Critical Fixes ✅ COMPLETE
- [x] `feature_registry.py:311` — `return set(...)` → `return sorted(self._by_tf.keys())`
- [x] `play.py:565` — Updated return type `set[str]` → `list[str]`
- [x] `preflight.py:886` — Fixed `.add()` call on list (converted to set wrapper)
- [x] `runner.py:185` — `list(required_tfs)` → `sorted(required_tfs)`
- [x] `backtest.py:88` — `list(required_tfs)` → `sorted(required_tfs)` (CLI handler)
- [x] **GATE**: 5x identical runs WITHOUT `PYTHONHASHSEED=0` ✅

### Phase 2: Defensive Hardening ✅ COMPLETE
- [x] `backtest_play_tools.py:530` — `list(required_tfs)` → `sorted(required_tfs)`
- [x] `forge_menu.py:292` — `list(required_tfs)` → `sorted(required_tfs)`
- [x] Audited `feed_store.indicators` population — deterministic (built from ordered list)
- [x] Audited `play_engine.py` indicator dict construction — deterministic (dict insertion order)
- [x] Audited `set[datetime]` usages — all membership-test only, safe
- [x] **GATE**: `validate standard` ALL 13 GATES PASSED (417.9s) + 3x determinism ✅

### Phase 3: Remove Band-Aid ✅ COMPLETE
- [x] Remove `PYTHONHASHSEED=0` from `.venv-linux/bin/activate`
- [x] Keep `PYTHONDONTWRITEBYTECODE=1` (WSL2 performance benefit)
- [x] **GATE**: `validate full` 14/15 gates passed (1 pre-existing VWAP failure, unrelated)
- [x] **GATE**: 5x determinism check on 5 different plays ✅
  ```
  AT_001_ema_cross_basic:  599ed4e9 599ed4e9 599ed4e9
  OP_001_gt:               eb850d2d eb850d2d eb850d2d
  OP_010_near_pct:         9a9677da 9a9677da 9a9677da
  STR_001_swing_basic:     d6e0253e d6e0253e d6e0253e
  CL_001:                  cdf5bdf4 cdf5bdf4 cdf5bdf4
  ```
