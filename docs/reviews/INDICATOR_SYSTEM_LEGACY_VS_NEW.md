# Indicator System: Legacy vs New Architecture

**Date:** 2024-12-19  
**Scope:** Explanation of the difference between legacy (removed) and new indicator systems  
**Related:** Phase 6.1 (removal of implicit indicator defaults)

## Overview

The TRADE backtest system has evolved from a legacy system with implicit/default indicators to a new three-layer architecture that provides explicit control over indicator computation. This document explains both systems and the key differences.

---

## Legacy System (Removed in Phase 6.1)

### What It Was

The legacy system used **implicit/default indicators** that were computed automatically:

- **`REQUIRED_INDICATOR_COLUMNS` constant** with hardcoded defaults like `['ema_fast', 'ema_slow', 'rsi', 'atr']`
- **`FeedStore.from_dataframe()`** had default indicator columns
- Indicators were **inferred**, not explicitly declared
- No control over which indicators were computed

### Problems with Legacy System

1. **No Control**: Couldn't choose which indicators to compute
2. **Silent Defaults**: Indicators computed without explicit declaration
3. **Confusion**: Hard to know what indicators were available
4. **Violated "Fail Loud" Principle**: Missing indicators would fail silently or use defaults

### Example (Legacy - NO LONGER EXISTS)

```python
# OLD WAY (removed)
REQUIRED_INDICATOR_COLUMNS = ["ema_fast", "ema_slow", "rsi", "atr"]

# FeedStore would automatically compute these
feed = FeedStore.from_dataframe(df)  # Would compute defaults
```

**Status:** ✅ **REMOVED** - This system no longer exists in the codebase.

---

## New System: Three-Layer Architecture

The new system provides explicit control through three distinct layers:

```
┌─────────────────────────────────────┐
│  IdeaCard (YAML)                    │  ← User Interface
│  Declares FeatureSpecs              │
└──────────────┬──────────────────────┘
               │
               ↓
┌─────────────────────────────────────┐
│  FeatureSpec System                  │  ← Declaration Layer
│  Maps IndicatorType → Parameters    │
└──────────────┬──────────────────────┘
               │
               ↓
┌─────────────────────────────────────┐
│  Indicator Library (indicator_vendor)│  ← Computation Layer
│  Actual math functions (pandas_ta)  │
└─────────────────────────────────────┘
```

---

### Layer 1: Indicator Library (`indicator_vendor.py`)

**What It Is:**
- The **computation layer** — actual math functions
- **ONLY module** that imports `pandas_ta`
- Provides wrapper functions that can be swapped to different backends (TA-Lib, custom, etc.)

**Available Functions:**

```python
# Single-output indicators
ema(close: pd.Series, length: int) -> pd.Series
sma(close: pd.Series, length: int) -> pd.Series
rsi(close: pd.Series, length: int) -> pd.Series
atr(high, low, close, length) -> pd.Series

# Multi-output indicators
macd(close, fast, slow, signal) -> Dict[str, pd.Series]  
    # Returns: {"macd": Series, "signal": Series, "histogram": Series}

bbands(close, length, std) -> Dict[str, pd.Series]  
    # Returns: {"upper": Series, "middle": Series, "lower": Series, 
    #           "bandwidth": Series, "percent_b": Series}

stoch(high, low, close, k, d, smooth_k) -> Dict[str, pd.Series]  
    # Returns: {"k": Series, "d": Series}

stochrsi(close, length, rsi_length, k, d) -> Dict[str, pd.Series]  
    # Returns: {"k": Series, "d": Series}
```

**Key Point:** This is the **available library** — all possible indicators you can use.

**Location:** `src/backtest/indicator_vendor.py`

---

### Layer 2: FeatureSpec System (`feature_spec.py`)

**What It Is:**
- **Declarative specification layer**
- Defines **what indicators to compute**, with parameters
- Maps to indicator library functions via `IndicatorType` enum

**How It Works:**

```python
# Declare what you want
spec = FeatureSpec(
    indicator_type=IndicatorType.EMA,  # Maps to ema() in library
    output_key="ema_fast",              # Name in FeedStore
    params={"length": 20},              # Parameters
    input_source=InputSource.CLOSE      # What data to use
)

# FeatureFrameBuilder computes it
builder = FeatureFrameBuilder()
arrays = builder.build_features(spec_set, ohlcv_df)
# Result: arrays["ema_fast"] contains the computed values
```

**Available Indicator Types:**

```python
class IndicatorType(str, Enum):
    # Single-output indicators
    EMA = "ema"          # Exponential Moving Average
    SMA = "sma"          # Simple Moving Average
    RSI = "rsi"          # Relative Strength Index
    ATR = "atr"          # Average True Range
    
    # Multi-output indicators
    MACD = "macd"        # → macd, signal, histogram
    BBANDS = "bbands"    # → upper, middle, lower, bandwidth, percent_b
    STOCH = "stoch"      # → k, d
    STOCHRSI = "stochrsi"  # → k, d
```

**Key Point:** This is how you **declare which indicators from the library** you want to use.

**Location:** `src/backtest/features/feature_spec.py`

---

### Layer 3: IdeaCard Wrapper (`idea_card.py`)

**What It Is:**
- **YAML-based strategy specification**
- Declares FeatureSpecs per timeframe (exec, htf, mtf)
- Self-contained strategy definition

**How It Works:**

```yaml
# configs/idea_cards/my_strategy.yml
id: my_strategy
version: "1.0.0"
symbol_universe: ["BTCUSDT"]

tf_configs:
  exec:
    tf: 1h
    role: exec
    feature_specs:              # ← Declare indicators here
      - indicator_type: ema
        output_key: ema_fast
        params: { length: 9 }
        input_source: close
        
      - indicator_type: ema
        output_key: ema_slow
        params: { length: 21 }
        input_source: close
        
      - indicator_type: rsi
        output_key: rsi_14
        params: { length: 14 }
        input_source: close
```

**Engine Flow:**

```
IdeaCard (YAML)
    ↓
load_idea_card() → IdeaCard object
    ↓
IdeaCard.get_feature_spec_set("exec", "BTCUSDT") → FeatureSpecSet
    ↓
FeatureFrameBuilder.build_features() → FeatureArrays
    ↓
FeedStore.from_feature_arrays() → FeedStore (with indicators)
    ↓
RuntimeSnapshotView → Strategy can access indicators
```

**Key Point:** This is the **user-facing wrapper** — you declare indicators in YAML, and the system computes them.

**Location:** `src/backtest/idea_card.py`

---

## Key Differences Summary

| Aspect | Legacy (Removed) | New System |
|--------|------------------|------------|
| **Declaration** | Implicit defaults | Explicit via FeatureSpec/IdeaCard |
| **Control** | Hardcoded list | You choose what to compute |
| **Library** | Mixed with defaults | Separate: `indicator_vendor.py` |
| **Specification** | None | `FeatureSpec` objects |
| **User Interface** | Code constants | YAML IdeaCards |
| **Error Handling** | Silent defaults | Fail loud if not declared |
| **Flexibility** | Fixed set | Any indicator from library |

---

## Example: Using the New System

### Step 1: Check Available Library

```python
# See what's available in indicator_vendor.py
from src.backtest.indicator_vendor import ema, rsi, macd
# These are the computation functions
```

### Step 2: Declare What You Want (IdeaCard)

```yaml
# configs/idea_cards/my_strategy.yml
tf_configs:
  exec:
    feature_specs:
      - indicator_type: ema      # From IndicatorType enum
        output_key: ema_fast     # Your name
        params: { length: 9 }    # Parameters
        input_source: close
```

### Step 3: Engine Computes It

```python
# Engine reads IdeaCard → builds FeatureSpecs → computes via indicator_vendor
# Result available in snapshot:
snapshot.indicator_strict("ema_fast")  # ← Must match output_key
```

---

## Important Rules

### 1. No Implicit Defaults

**Rule:** All indicators must be explicitly declared.

**Enforcement:**
- `FeedStore.from_dataframe()` with `indicator_columns=None` → empty dict, not default list
- `REQUIRED_INDICATOR_COLUMNS` constant was deleted
- Missing declarations raise errors, not infer behavior

**Example:**
```python
# ❌ OLD (removed)
feed = FeedStore.from_dataframe(df)  # Would compute defaults

# ✅ NEW (required)
feed = FeedStore.from_dataframe(df, indicator_columns=["ema_fast", "rsi_14"])
# OR via IdeaCard → FeatureSpec → automatic
```

### 2. Library is Separate from Declaration

**Rule:** `indicator_vendor.py` has functions, `FeatureSpec` declares usage.

**Separation:**
- **Library** (`indicator_vendor.py`): Computation functions
- **Specification** (`FeatureSpec`): What to compute
- **Interface** (`IdeaCard`): YAML declaration

### 3. IdeaCard is the User Interface

**Rule:** Declare indicators in YAML, not code.

**Canonical Location:** `configs/idea_cards/`

**Example:**
```yaml
tf_configs:
  exec:
    feature_specs:
      - indicator_type: ema
        output_key: ema_fast
        params: { length: 9 }
```

### 4. Fail Loud

**Rule:** If you request an undeclared indicator, you get a `KeyError`.

**Enforcement:**
- `snapshot.indicator_strict("unknown")` → `KeyError`
- `TFContext.get_indicator_strict("unknown")` → `KeyError`
- No silent fallbacks or defaults

**Example:**
```python
# ✅ Correct
snapshot.indicator_strict("ema_fast")  # Declared in IdeaCard

# ❌ Error
snapshot.indicator_strict("unknown")  # KeyError: Indicator 'unknown' not declared
```

---

## Migration Guide

### If You Have Legacy Code

**Before (Legacy - Removed):**
```python
# OLD: Implicit defaults
REQUIRED_INDICATOR_COLUMNS = ["ema_fast", "ema_slow"]
feed = FeedStore.from_dataframe(df)
```

**After (New System):**
```yaml
# NEW: Explicit declaration in IdeaCard
tf_configs:
  exec:
    feature_specs:
      - indicator_type: ema
        output_key: ema_fast
        params: { length: 9 }
      - indicator_type: ema
        output_key: ema_slow
        params: { length: 21 }
```

---

## Architecture Benefits

### 1. Explicit Control
- You choose exactly which indicators to compute
- No surprises from implicit defaults

### 2. Backend Swappable
- `indicator_vendor.py` can be swapped to TA-Lib, custom implementations, etc.
- Only one file needs to change

### 3. Declarative
- YAML IdeaCards are self-documenting
- Easy to version control and share

### 4. Type Safe
- `IndicatorType` enum ensures valid types
- `FeatureSpec` validates parameters

### 5. Fail Loud
- Missing indicators raise clear errors
- No silent failures or defaults

---

## Related Documentation

- [Current State Review: DuckDB Data + Indicators](./CURRENT_STATE_REVIEW_DUCKDB_DATA_AND_INDICATORS.md)
- [Feature Specification System](../architecture/BACKTEST_MODULE_OVERVIEW.md)
- [IdeaCard Format](../guides/WRITING_STRATEGIES.md)
- [Phase 6.1 TODO](../todos/archived/SNAPSHOT_HISTORY_MTF_ALIGNMENT_PHASES.md#phase-61--remove-implicit-indicator-defaults--complete)

---

## Summary

The new system provides **explicit control** through three layers:

1. **Indicator Library** (`indicator_vendor.py`): Available computation functions
2. **FeatureSpec System** (`feature_spec.py`): Declarative specification
3. **IdeaCard Wrapper** (`idea_card.py`): YAML user interface

**Key Principle:** No implicit defaults — all indicators must be explicitly declared via FeatureSpec/IdeaCard.

**Result:** Clear, maintainable, and flexible indicator system that follows the "fail loud" principle.

