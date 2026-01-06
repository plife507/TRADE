# Indicator Warmup Architecture

**STATUS:** CANONICAL
**PURPOSE:** Indicator warmup computation, variable requirements, adding new indicators
**LAST UPDATED:** January 4, 2026 (Terminology update)

---

## Terminology (2026-01-04)

This document uses the new trading hierarchy terminology:

| Term | Definition |
|------|------------|
| **Setup** | Reusable rule blocks, filters, entry/exit logic |
| **Play** | Complete strategy specification |
| **Playbook** | Collection of plays with regime routing |
| **System** | Full trading operation with risk/execution |
| **Forge** | Development/validation environment (src/forge/) |

See: `docs/architecture/LAYER_2_RATIONALIZATION_ARCHITECTURE.md` for complete architecture.

---

## Executive Summary

Indicator warmup requirements are **variable** and computed dynamically from indicator types and their parameters. Each indicator type has a specific warmup formula (EMA: 3xlength, RSI: length+1, etc.). The system uses a single source of truth: `compute_warmup_requirements()` aggregates warmup per TF role from Play declarations.

**Key Principles:**
- ✅ Warmup is **variable** based on indicator parameters
- ✅ Computed dynamically from indicator type + params
- ✅ Indicator registry is the **critical gate** - must be registered to be usable
- ✅ Warmup functions are **optional** but recommended for accuracy
- ✅ Preflight uses computed warmup to determine data fetch range

---

## Warmup Computation Flow

```
Play declares FeatureSpecs
    ↓
FeatureSpec.warmup_bars (type-specific formula)
    ↓
max across all specs per TF role
    ↓
compute_warmup_requirements() → WarmupRequirements
    ↓
Preflight uses warmup_by_role for data fetch range
```

### Code Locations

| Component | File | Purpose |
|-----------|------|---------|
| **Warmup Computation** | `src/backtest/execution_validation.py:421-461` | `compute_warmup_requirements()` - canonical aggregation |
| **Per-Indicator Warmup** | `src/backtest/features/feature_spec.py:450-513` | `FeatureSpec.warmup_bars` property |
| **Warmup Functions** | `src/backtest/indicator_vendor.py:716-771` | Type-specific formulas (EMA, RSI, MACD, etc.) |

---

## Variable Warmup Requirements

Warmup requirements are **not fixed** - they vary based on indicator parameters:

| Indicator | Parameters | Warmup Formula | Example |
|-----------|-----------|----------------|---------|
| **EMA** | `length=20` | `3 × length` | 60 bars |
| **EMA** | `length=50` | `3 × length` | **150 bars** (variable!) |
| **SMA** | `length=20` | `length` | 20 bars |
| **RSI** | `length=14` | `length + 1` | 15 bars |
| **MACD** | `fast=12, slow=26, signal=9` | `3 × slow + signal` | 87 bars |
| **STOCHRSI** | `length=14, rsi_length=14, k=3, d=3` | `rsi_length + length + max(k,d)` | 31 bars |

### Example: Variable Warmup in Practice

```yaml
tf_configs:
  exec:
    feature_specs:
      - indicator_type: EMA
        params: {length: 20}  # → 60 bars warmup
      - indicator_type: RSI
        params: {length: 14}  # → 15 bars warmup
  htf:
    feature_specs:
      - indicator_type: MACD
        params: {fast: 12, slow: 26, signal: 9}  # → 87 bars warmup
```

**Result:**
- `warmup_by_role['exec'] = max(60, 15) = 60 bars`
- `warmup_by_role['htf'] = 87 bars`

**Preflight fetches:**
- Exec TF: `window_start - (60 + safety_buffer) × tf_minutes`
- HTF TF: `window_start - (87 + safety_buffer) × tf_minutes`

---

## Indicator Warmup Formulas

**Location**: `src/backtest/indicator_vendor.py:716-771`

### Current Warmup Functions

```python
def get_ema_warmup(length: int, stabilization_factor: int = 3) -> int:
    """EMA needs 3×length for stabilization (97% of true value)."""
    return length * stabilization_factor

def get_sma_warmup(length: int) -> int:
    """SMA needs exactly length bars."""
    return length

def get_rsi_warmup(length: int) -> int:
    """RSI needs length+1 for first delta calculation."""
    return length + 1

def get_atr_warmup(length: int) -> int:
    """ATR needs length+1 for previous close reference."""
    return length + 1

def get_macd_warmup(fast: int, slow: int, signal: int) -> int:
    """MACD needs slow EMA stabilization + signal line."""
    return slow * 3 + signal

def get_bbands_warmup(length: int) -> int:
    """Bollinger Bands same as SMA."""
    return length

def get_stoch_warmup(k: int, d: int, smooth_k: int) -> int:
    """Stochastic needs %K smoothing + %D calculation."""
    return k + smooth_k + d

def get_stochrsi_warmup(length: int, rsi_length: int, k: int, d: int) -> int:
    """StochRSI needs RSI + Stochastic cascade."""
    return rsi_length + length + max(k, d)
```

### Special Cases

| Indicator | Formula | Reason |
|-----------|---------|--------|
| **EMA** | `3 × length` | Stabilization (97% of true value) |
| **MACD** | `3 × slow + signal` | Slow EMA stabilization + signal EMA |
| **STOCHRSI** | `rsi_length + length + max(k, d)` | RSI → STOCH cascade |
| **STOCH** | `k + smooth_k + d` | %K smoothing + %D |
| **ATR** | `length + 1` | Initial true range + smoothing |
| **RSI** | `length + 1` | Initial gain/loss + smoothing |

### Fallback Behavior

If an indicator type doesn't have a warmup function, `FeatureSpec.warmup_bars` falls back to:
```python
# From feature_spec.py:512-513
else:
    # Fallback for unknown types
    return self.length
```

This uses the `length` parameter (or 0 if not present), which works but may be inaccurate for complex indicators.

---

## Adding New Indicators

> **Registry Consolidation (2025-12-31):** Adding indicators now requires editing
> **only ONE file**: `src/backtest/indicator_registry.py`. The `IndicatorType` enum
> and `MULTI_OUTPUT_KEYS` dict have been removed.

### Step-by-Step Guide

To add a new pandas_ta indicator, edit `src/backtest/indicator_registry.py`:

#### Step 1: Add Warmup Function (if needed)

Add a named warmup function at the top of the file (lines 53-185):

```python
def _warmup_your_indicator(p: Dict[str, Any]) -> int:
    """YourIndicator needs X bars for stabilization."""
    return p.get("length", 14) * 2  # Your formula based on math requirements
```

**Warmup formula guidelines:**
- **EMA-based**: Use `3 × length` for stabilization
- **SMA-based**: Use `length` exactly
- **Delta-based** (RSI, ATR): Use `length + 1`
- **Cascade** (MACD, StochRSI): Sum of component warmups
- **Cumulative** (OBV): Use `_warmup_minimal` (returns 1)

If your indicator matches an existing pattern, reuse an existing function:
- `_warmup_ema` - For EMA-based indicators
- `_warmup_length` - For length-only indicators
- `_warmup_minimal` - For cumulative/instant indicators

#### Step 2: Add to SUPPORTED_INDICATORS Dict

Add entry to `SUPPORTED_INDICATORS` (lines 196-487):

```python
SUPPORTED_INDICATORS: Dict[str, Dict[str, Any]] = {
    # ... existing indicators ...

    # Single-output example:
    "your_indicator": {
        "inputs": {"close"},           # Required price series
        "params": {"length"},          # Accepted parameters
        "multi_output": False,         # Single output
        "warmup_formula": _warmup_your_indicator,
    },

    # Multi-output example:
    "your_multi_indicator": {
        "inputs": {"high", "low", "close"},
        "params": {"length", "multiplier"},
        "multi_output": True,
        "output_keys": ("upper", "middle", "lower"),  # Output suffixes
        "primary_output": "middle",                    # Default output
        "warmup_formula": _warmup_your_indicator,
    },
}
```

**Required fields:**
- `inputs`: Set of required price series (`{"close"}`, `{"high", "low", "close"}`, etc.)
- `params`: Set of accepted parameters
- `multi_output`: Boolean - does it produce multiple outputs?
- `warmup_formula`: Reference to warmup function

**Optional fields (for multi-output):**
- `output_keys`: Tuple of output suffixes
- `primary_output`: Default output for references

**Optional fields (for custom compute):**
- `sparse`: `True` if outputs need forward-fill (market structure)
- `compute_fn`: Custom compute function name (non-pandas_ta indicators)

#### Step 3: Verify with Audit

Run the audit to confirm registration:

```bash
python trade_cli.py backtest audit-toolkit
```

Should show your indicator in the count (e.g., "43/43 PASS").

### Adding New Indicators Checklist

- [ ] Add warmup function to `indicator_registry.py` (or reuse existing)
- [ ] Add entry to `SUPPORTED_INDICATORS` dict
- [ ] Run `python trade_cli.py backtest audit-toolkit` to verify
- [ ] (Optional) Add compute logic to `indicator_vendor.py` if not standard pandas_ta

### Example: Adding Chaikin Oscillator

```python
# Step 1: Warmup function (uses EMA-based calculation)
def _warmup_chaikin(p: Dict[str, Any]) -> int:
    """Chaikin needs fast + slow EMA stabilization."""
    fast = p.get("fast", 3)
    slow = p.get("slow", 10)
    return slow * 3  # Slow EMA dominates

# Step 2: Add to SUPPORTED_INDICATORS
"adosc": {  # pandas_ta name for Chaikin A/D Oscillator
    "inputs": {"high", "low", "close", "volume"},
    "params": {"fast", "slow"},
    "multi_output": False,
    "warmup_formula": _warmup_chaikin,
},
```

**That's it!** The indicator is now available for use in Plays.

---

## Architecture Overview

### Indicator Computation Flow (Post-Consolidation)

```
Play FeatureSpec (indicator_type as STRING)
    ↓
IndicatorRegistry.is_supported()  ← CRITICAL GATE
    ↓
compute_indicator() (dynamic pandas_ta call)
    ↓
registry.get_warmup_bars(type, params)  ← WARMUP FROM REGISTRY
    ↓
compute_warmup_requirements() (max across specs)
    ↓
Preflight data fetch (warmup + safety buffer)
```

### Single Source of Truth for Indicators

After Registry Consolidation (2025-12-31), ALL indicator metadata lives in one file:

| Metadata | Location in `indicator_registry.py` |
|----------|-------------------------------------|
| Supported indicators | `SUPPORTED_INDICATORS` dict keys |
| Warmup formulas | `warmup_formula` field (named functions) |
| Multi-output keys | `output_keys` field |
| Input requirements | `inputs` field |
| Parameter validation | `params` field |

**Deprecated (removed):**
- ~~`IndicatorType` enum~~ → Use strings
- ~~`MULTI_OUTPUT_KEYS` dict~~ → Use `registry.get_output_suffixes()`
- ~~`FeatureSpec.warmup_bars` switch statement~~ → Uses `registry.get_warmup_bars()`

### Critical Gates

1. **Registry Gate**: Indicator must be in `SUPPORTED_INDICATORS` or `FeatureSpec.__post_init__` raises `ValueError`
2. **Warmup Gate**: Uses `registry.get_warmup_bars()` - falls back to `length` param if no formula
3. **Preflight Gate**: Uses computed warmup to determine data fetch range

---

## Warmup System Integration

### Single Source of Truth

**Play -> `compute_warmup_requirements()` -> `SystemConfig.warmup_bars_by_role` -> Engine**

The engine **MUST NOT** recompute warmup from feature specs. It uses the canonical warmup from `SystemConfig.warmup_bars_by_role` or fails loud.

**Enforcement** (`src/backtest/engine.py:460-465`):
```python
warmup_bars_by_role = getattr(self.config, 'warmup_bars_by_role', {})
if not warmup_bars_by_role or 'exec' not in warmup_bars_by_role:
    raise ValueError(
        "MISSING_WARMUP_CONFIG: warmup_bars_by_role['exec'] not set. "
        "Ensure Play warmup is wired through compute_warmup_requirements()."
    )
warmup_bars = warmup_bars_by_role['exec']
```

**No silent defaults. No implicit computations. Fail loud.**

---

## References

| Component | Location |
|-----------|----------|
| **Indicator Registry** | `src/backtest/indicator_registry.py` |
| **Warmup Functions** | `src/backtest/indicator_registry.py:53-185` |
| **SUPPORTED_INDICATORS** | `src/backtest/indicator_registry.py:196-487` |
| **FeatureSpec** | `src/backtest/features/feature_spec.py` |
| **Warmup Aggregation** | `src/backtest/execution_validation.py:421-461` |
| **pandas_ta Reference** | `reference/pandas_ta_repo/` |

---

**See Also:**
- `ARCH_SNAPSHOT.md` - Overall system architecture
- `ARCH_DELAY_BARS.md` - Delay bars and market structure configuration
- `docs/todos/REGISTRY_CONSOLIDATION_PHASES.md` - Registry consolidation TODO (completed)
