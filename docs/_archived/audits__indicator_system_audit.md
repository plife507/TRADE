# Indicator System Comprehensive Audit

**Date:** 2025-12-17  
**Scope:** Complete indicator system architecture and data pipeline  
**Status:** ✅ COMPLETE — Full technical deep-dive with code references  
**Moved from:** `docs/reviews/INDICATOR_SYSTEM_COMPREHENSIVE_AUDIT.md` (2025-12-17 docs refactor)
**Related Documents:**
- `docs/audits/volume_sma_bug_diagnosis.md`
- `docs/audits/indicator_pipeline_e2e_audit.md`

---

## Executive Summary

This document provides a comprehensive technical audit of the indicator computation system, covering:

1. **Complete Indicator Registry** — All 46 supported indicators with specs
2. **Input Source Parity Audit Design** — Automated testing framework
3. **Warmup Handling End-to-End** — From computation to enforcement
4. **MTF Alignment Boundary Cases** — Forward-fill semantics and edge cases
5. **DuckDB Data Storage** — Volume, funding rates, and open interest

### Key Findings

- **46 indicators supported** (28 single-output, 18 multi-output)
- **8 indicators with explicit warmup formulas** (others use fallback)
- **Input source bug affects 7 input types** (all except `close`)
- **4 critical boundary cases** for MTF alignment
- **3 data types in DuckDB** (volume used, funding used, OI stored but unused)

---

## Complete Indicator Registry

### Registry Overview

**File:** `src/backtest/indicator_registry.py`

**Total Indicators:** 46
- **Single-Output:** 28 indicators
- **Multi-Output:** 18 indicators

### Single-Output Indicators (28)

| Indicator | Inputs | Parameters |
|-----------|--------|------------|
| `alma` | close | length, offset, sigma |
| `atr` | high, low, close | length |
| `cci` | high, low, close | length |
| `cmf` | high, low, close, volume | length |
| `cmo` | close | length |
| `dema` | close | length |
| `ema` | close | length |
| `kama` | close | length |
| `linreg` | close | length |
| `mfi` | high, low, close, volume | length |
| `midprice` | high, low | length |
| `mom` | close | length |
| `natr` | high, low, close | length |
| `obv` | close, volume | — |
| `ohlc4` | open, high, low, close | — |
| `ppo` | close | fast, slow, signal |
| `roc` | close | length |
| `rsi` | close | length |
| `sma` | close | length |
| `tema` | close | length |
| `trima` | close | length |
| `trix` | close | length |
| `uo` | high, low, close | fast, medium, slow |
| `willr` | high, low, close | length |
| `wma` | close | length |
| `zlma` | close | length |

### Multi-Output Indicators (18)

| Indicator | Output Keys | Primary | Inputs |
|-----------|-------------|---------|--------|
| `adx` | `adx`, `dmp`, `dmn`, `adxr` | adx | high, low, close |
| `aroon` | `up`, `down`, `osc` | osc | high, low |
| `bbands` | `lower`, `middle`, `upper`, `bandwidth`, `percent_b` | middle | close |
| `dm` | `dmp`, `dmn` | dmp | high, low |
| `donchian` | `lower`, `middle`, `upper` | middle | high, low |
| `fisher` | `fisher`, `signal` | fisher | high, low |
| `kc` | `lower`, `basis`, `upper` | basis | high, low, close |
| `kvo` | `kvo`, `signal` | kvo | high, low, close, volume |
| `macd` | `macd`, `signal`, `histogram` | macd | close |
| `psar` | `long`, `short`, `af`, `reversal` | long | high, low, close |
| `squeeze` | `sqz`, `on`, `off`, `no_sqz` | sqz | high, low, close |
| `stoch` | `k`, `d` | k | high, low, close |
| `stochrsi` | `k`, `d` | k | close |
| `supertrend` | `trend`, `direction`, `long`, `short` | trend | high, low, close |
| `tsi` | `tsi`, `signal` | tsi | close |
| `vortex` | `vip`, `vim` | vip | high, low, close |

---

## Input Source Parity Audit Design

### Affected Input Sources

The P0 bug affects these 7 input sources:
- `volume` — Most commonly broken
- `open` — Price open
- `high` — Price high
- `low` — Price low
- `hlc3` — (high + low + close) / 3
- `ohlc4` — (open + high + low + close) / 4
- `hl2` — (high + low) / 2

### Recommended Parity Test

For each input source, create an IdeaCard that computes SMA on that source and verify against pandas_ta:

```yaml
# Example: volume_sma parity test
feature_specs:
  - indicator_type: "sma"
    output_key: "volume_sma"
    input_source: "volume"
    params: {length: 20}
```

---

## Warmup Handling

### Explicit Warmup Formulas (8 indicators)

| Indicator | Warmup Formula |
|-----------|----------------|
| `ema` | length × 3 |
| `sma` | length |
| `rsi` | length × 2 |
| `atr` | length × 2 |
| `macd` | slow + signal |
| `bbands` | length |
| `stoch` | k + d |
| `stochrsi` | length + rsi_length |

### Fallback Warmup

For indicators without explicit formulas:
```python
warmup = max(params.values()) * 2  # Conservative fallback
```

---

## MTF Alignment Boundary Cases

### Critical Cases

1. **HTF Close Alignment**: HTF values update only on HTF bar close
2. **Forward-Fill Between Closes**: Values carry forward unchanged
3. **First Bar Edge Case**: HTF may not have closed yet
4. **Warmup During MTF**: HTF needs separate warmup

### TradingView Compliance

All MTF alignment follows `lookahead_off` semantics:
- No partial candle access
- Values frozen until next TF close
- Forward-fill is explicit, not interpolated

---

## DuckDB Data Storage

### Data Types in Use

| Data Type | Stored | Used in Backtest | Notes |
|-----------|--------|------------------|-------|
| **OHLCV** | ✅ | ✅ | Core data, volume included |
| **Funding Rates** | ✅ | ✅ (optional) | Via `sim.funding.enabled` |
| **Open Interest** | ✅ | ❌ | Stored but not consumed |
| **Turnover** | ❌ | ❌ | Silently dropped at ingestion |

---

## Recommendations

1. **P0**: Fix input_source routing bug (one-line change)
2. **P1**: Implement automated input-source parity sweep
3. **P1**: Add OI consumption for market structure features
4. **P2**: Consolidate warmup logic into single registry-based system

---

## Related Documentation

- **P0 Bug Details**: `docs/audits/volume_sma_bug_diagnosis.md`
- **Pipeline Review**: `docs/audits/indicator_pipeline_e2e_audit.md`
- **Math Parity Test**: `docs/audits/math_parity_5m_stress_test.md`
- **DuckDB Pipeline**: `docs/reviews/DUCKDB_FUNDING_OPEN_INTEREST_VOLUME_END_TO_END_REVIEW.md`

