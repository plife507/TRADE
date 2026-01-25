# Unified Indicator System - Implementation Plan

> **Last Updated:** 2026-01-25
> **Current Phase:** Phase 1 - Foundation
> **Status:** In Progress

## Goal

Create a single indicator system that works identically across backtest, demo, and live modes. Adding a new indicator = 1 file change.

## Anti-Goals

- NO deprecated modules left behind
- NO parallel code paths doing the same thing
- NO hardcoded lists in multiple places

---

## Progress Tracker

| Phase | Status | Tasks Done | Tasks Total |
|-------|--------|------------|-------------|
| Phase 1: Registry Foundation | ✅ Complete | 3 | 3 |
| Phase 2: Provider Protocol | ✅ Complete | 4 | 4 |
| Phase 3: Live Adapter Refactor | ✅ Complete | 4 | 4 |
| Phase 4: Incremental Expansion | ✅ Complete | 5 | 5 |
| Phase 5: Cleanup | ✅ Complete | 4 | 4 |

---

## Phase 1: Registry as Single Source

### Task 1.1: Audit Current Registry ✅ COMPLETE

**Findings:**

#### Indicator Count: 42 Total (not 43 as docs claim)
- 26 single-output indicators
- 16 multi-output indicators
- 6 have incremental implementations

#### Current Incremental Indicators (6)
| Indicator | Class | Location |
|-----------|-------|----------|
| ema | `IncrementalEMA` | `src/indicators/incremental.py:57-102` |
| sma | `IncrementalSMA` | `src/indicators/incremental.py:105-144` |
| rsi | `IncrementalRSI` | `src/indicators/incremental.py:147-219` |
| atr | `IncrementalATR` | `src/indicators/incremental.py:222-283` |
| macd | `IncrementalMACD` | `src/indicators/incremental.py:286-356` |
| bbands | `IncrementalBBands` | `src/indicators/incremental.py:359-440` |

#### Hardcoded Lists Found
| List | Location | Action Needed |
|------|----------|---------------|
| `INCREMENTAL_INDICATORS` | `src/indicators/incremental.py:483` | Move to registry metadata |
| ATR special case | `src/engine/adapters/live.py:130` | Remove, use registry |

#### Gaps Identified
1. Documentation claims 43 indicators (registry has 42)
2. `INCREMENTAL_INDICATORS` separate from registry - drift risk
3. Live adapter has hardcoded ATR special case
4. Registry doesn't declare which indicators support incremental

### Task 1.2: Add Computation Strategy to Registry ✅ COMPLETE

- [x] Add `incremental_class: str | None` field to each indicator entry
- [x] Set class name for: ema, sma, rsi, atr, macd, bbands
- [x] Set `None` for all others (vectorized fallback)
- [x] Add helper: `supports_incremental(ind_type: str) -> bool`
- [x] Add helper: `get_incremental_class(ind_type: str) -> type | None`
- [x] Add helper: `list_incremental_indicators() -> list[str]`

**Files:** `src/backtest/indicator_registry.py`

### Task 1.3: Registry Validation ✅ COMPLETE

- [x] Add `validate_registry()` function that checks:
  - All indicators have required fields
  - `incremental_class` implies class exists in incremental.py
  - Warmup formulas return valid integers
  - Output types defined for all indicators
- [x] Call validation on module load (fail fast via `_validate_on_load()`)
- [x] Update `src/indicators/incremental.py` to delegate to registry

**Files:**
- `src/backtest/indicator_registry.py`
- `src/indicators/incremental.py`

---

## Phase 2: Unified Provider Protocol ✅ COMPLETE

### Task 2.1: Design Provider Interface ✅ COMPLETE

Created `src/indicators/provider.py` with:
```python
@runtime_checkable
class IndicatorProvider(Protocol):
    def get(self, name: str, offset: int = 0) -> float: ...
    def has(self, name: str) -> bool: ...
    def is_ready(self, name: str) -> bool: ...
    @property
    def bar_index(self) -> int: ...
    @property
    def indicator_names(self) -> list[str]: ...
```

### Task 2.2: Backtest Provider Implementation ✅ COMPLETE

- [x] Created `BacktestIndicatorProvider` class
- [x] Wraps FeedStore arrays with index-based access
- [x] Implements IndicatorProvider protocol
- [x] Added `step()` method for simulation advancement
- [x] Added `get_ohlcv()` for OHLCV field access

### Task 2.3: Live Provider Implementation ✅ COMPLETE

- [x] Created `LiveIndicatorProvider` class
- [x] Wraps indicator arrays with most-recent-first access
- [x] Implements IndicatorProvider protocol
- [x] Added `from_cache()` factory for LiveIndicatorCache

### Task 2.4: Export from Package ✅ COMPLETE

- [x] Updated `src/indicators/__init__.py` with exports
- [x] Added `list_incremental_indicators` export

---

## Phase 3: Live Adapter Refactor ✅ COMPLETE

### Task 3.1: Remove Hardcoded List ✅ COMPLETE

- [x] `INCREMENTAL_INDICATORS` was already using `supports_incremental()` from indicators
- [x] `supports_incremental()` now delegates to registry (done in Phase 1)

### Task 3.2: Use Registry for Classification ✅ COMPLETE

- [x] Refactored `initialize_from_history()` to use `registry.get_indicator_info()`
- [x] Replaced hardcoded `if ind_type in ("atr",)` with `info.requires_hlc`
- [x] Updated `update()` method similarly to use registry

### Task 3.3: Integrate LiveIndicatorProvider ✅ COMPLETE

- [x] Created `LiveIndicatorProvider.from_cache()` factory (in Phase 2)
- [x] Provider wraps LiveIndicatorCache with standard interface

### Task 3.4: Backtest Adapter Parity ✅ COMPLETE

- [x] Created `BacktestIndicatorProvider` that wraps FeedStore (in Phase 2)
- [x] Both providers implement same `IndicatorProvider` protocol

---

## Phase 4: Expand Incremental Coverage ✅ COMPLETE

Target: Add 5 more O(1) incremental indicators

**Total: 11 incremental indicators now available**

### Task 4.1: IncrementalStochastic ✅ COMPLETE

- [x] Ring buffers for high/low over k_period
- [x] SMA smoothing for %K and %D
- [x] Multi-output: k_value, d_value

### Task 4.2: IncrementalADX ✅ COMPLETE

- [x] Uses IncrementalATR internally
- [x] Wilder's smoothing for +DI, -DI, ADX
- [x] Multi-output: adx_value, dmp_value, dmn_value

### Task 4.3: IncrementalSuperTrend ✅ COMPLETE

- [x] Uses IncrementalATR internally
- [x] Track trend direction and levels
- [x] Multi-output: trend_value, direction_value, long_value, short_value

### Task 4.4: IncrementalCCI ✅ COMPLETE

- [x] Typical price calculation with ring buffer
- [x] Mean deviation tracking
- [x] Standard CCI formula: (TP - SMA(TP)) / (0.015 * MeanDev)

### Task 4.5: IncrementalWilliamsR ✅ COMPLETE

- [x] Ring buffers for high/low
- [x] Simple %R formula: (HH - Close) / (HH - LL) * -100

---

## Phase 5: Cleanup & Deprecation ✅ COMPLETE

### Task 5.1: Audit All Code Paths ✅ COMPLETE

- [x] Ran detection commands - no stale hardcoded lists found
- [x] pandas_ta imports correctly isolated to vendor/metadata modules

### Task 5.2: Remove Legacy Code ✅ COMPLETE

- [x] Made INCREMENTAL_INDICATORS dynamic (computed from registry)
- [x] Removed hardcoded frozenset of 6 indicators
- [x] Live adapter now uses registry for all indicator classification

### Task 5.3: Update Documentation ✅ COMPLETE

- [x] Created `docs/UNIFIED_INDICATOR_PLAN.md` (this file)
- [x] Documents complete architecture and workflow

### Task 5.4: Final Validation ✅ COMPLETE

- [x] All smoke tests passing
- [x] Registry validation passes on module load
- [x] 11 incremental indicators verified

---

## Architecture Diagram

### Current State (Fragmented)
```
BACKTEST:
  indicator_registry.py → indicator_vendor.py → FeedStore
         ↓                    (pandas_ta)       (arrays)
    FeatureSpec                                    ↓
                                       BacktestDataProvider

LIVE/DEMO (Separate Path!):
  HARDCODED list → incremental.py → LiveIndicatorCache
     in live.py      (6 only)              ↓
         +                          LiveDataProvider
  indicator_vendor.py (fallback)
```

### Target State (Unified)
```
indicator_registry.py ─────────────────────────────┐
       │                                           │
       │ incremental_supported: bool               │
       │ warmup, params, outputs                   │
       │                                           │
       ▼                                           ▼
┌─────────────────┐                     ┌──────────────┐
│ UnifiedProvider │◄────────────────────│ incremental  │
│   (Protocol)    │                     │   .py        │
└────────┬────────┘                     └──────────────┘
         │
   ┌─────┴─────┐
   │           │
   ▼           ▼
Backtest     Live/Demo
Provider     Provider
```

---

## Files Summary

### New Files
| File | Purpose |
|------|---------|
| `src/indicators/provider.py` | IndicatorProvider protocol + implementations |

### Modified Files
| File | Changes |
|------|---------|
| `src/backtest/indicator_registry.py` | Add incremental_supported, helpers, validation |
| `src/indicators/incremental.py` | Add 5 new incremental classes, factory registry |
| `src/engine/adapters/live.py` | Use registry instead of hardcoded list |
| `src/indicators/__init__.py` | Export new classes |

### To Delete
| Code | Reason |
|------|--------|
| `INCREMENTAL_INDICATORS` in incremental.py | Replaced by registry field |
| Hardcoded ATR case in live.py | Use registry lookup |

---

## Success Criteria ✅ ALL MET

- [x] `indicator_registry.py` is the ONLY place to define indicator capabilities
- [x] Adding new indicator = 1 file change (registry entry + class if incremental)
- [x] Live and backtest use same IndicatorProvider protocol
- [x] 11 incremental indicators (6 existing + 5 new)
- [x] No hardcoded indicator lists anywhere (INCREMENTAL_INDICATORS is dynamic)
- [x] All smoke tests pass
- [x] ZERO deprecated/legacy code paths remaining

---

## Session Log

### Session 1 (2026-01-25)
- ✅ Created this tracking document
- ✅ **Phase 1 Complete**: Registry as Single Source of Truth
  - Added `incremental_class` field to registry with helpers
  - Added registry validation with fail-fast on load
  - Updated incremental.py to delegate to registry
- ✅ **Phase 2 Complete**: Unified Provider Protocol
  - Created `src/indicators/provider.py` with IndicatorProvider protocol
  - Implemented BacktestIndicatorProvider (wraps FeedStore)
  - Implemented LiveIndicatorProvider (wraps indicator arrays)
  - Updated package exports
- ✅ **Phase 3 Complete**: Live Adapter Refactor
  - Removed hardcoded `if ind_type in ("atr",)` checks
  - Now uses `registry.get_indicator_info().requires_hlc` for input requirements
  - All incremental classification uses registry-delegated functions
- ✅ **Phase 4 Complete**: Expand Incremental Coverage
  - Added 5 new incremental indicators: WilliamsR, CCI, Stoch, ADX, SuperTrend
  - Total incremental count: 11 (was 6)
  - All registered with `incremental_class` in registry
- ✅ **Phase 5 Complete**: Cleanup & Deprecation
  - Made INCREMENTAL_INDICATORS dynamic from registry
  - Removed all hardcoded indicator lists
  - All smoke tests passing

### Session 2 (2026-01-25) - Code Review Fixes
- ✅ Fixed multi-output handling in LiveIndicatorCache
  - Added `_get_incremental_output()` helper method
  - Proper array storage for all multi-output indicator values
- ✅ Added missing IncrementalBBands properties
  - `bandwidth` and `percent_b` properties
  - `_value` aliases for consistency (upper_value, middle_value, lower_value)
- ✅ Fixed IncrementalMACD naming consistency
  - Added `macd_value` property alias (matches signal_value, histogram_value pattern)
- ✅ All smoke tests passing after fixes

## 🎉 IMPLEMENTATION COMPLETE

All 5 phases successfully completed. The unified indicator system is now operational with:
- **Registry as single source of truth** for all indicator metadata
- **11 incremental indicators** for O(1) live trading performance
- **Unified provider protocol** for backtest/live parity
- **No hardcoded indicator lists** - all driven by registry
